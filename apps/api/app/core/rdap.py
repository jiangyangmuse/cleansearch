"""RDAP 域名年龄。缓存和网络查询都受整个批次预算约束。"""

from __future__ import annotations

import asyncio
from datetime import datetime
import ipaddress
import json
from pathlib import Path
import sqlite3
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

from tld import get_fld

from app.core.fetch import FetchError, SafeFetcher
from app.core.normalize import is_renderable_url

BOOTSTRAP = "https://rdap.org/domain/"
FRESH_DAYS = 30
AGE_PENALTY = 0.15
AGE_REASON = "域名新注册（<30 天）"
MAX_DOMAINS = 8
CONCURRENCY = 4
BUDGET_SECONDS = 4.0
MAX_CACHE_ENTRIES = 4096

SCHEMA = """
CREATE TABLE IF NOT EXISTS domain_age (
  domain        TEXT PRIMARY KEY,
  registered_at INTEGER,
  checked_at    INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class AgeInfo:
    domain: str
    registered_at: int | None
    fresh: bool


def registered_domain(host: str) -> str | None:
    """用包内 PSL 归一化到注册域名，不在请求路径下载后缀表。"""
    try:
        host = host.strip().rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    url = f"https://{host}"
    if not is_renderable_url(url) or urlsplit(url).netloc != host:
        return None
    return get_fld(url, fail_silently=True, search_private=False)


class DomainAgeStore:
    def __init__(self, db_path: Path, ttl_days: int = 30, negative_ttl_hours: int = 24) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = max(1, ttl_days) * 86400
        self._negative_ttl = max(1, negative_ttl_hours) * 3600
        self._lock = threading.Lock()
        # 应用共享 store，同一事件循环的不同搜索也共享网络许可。
        # 测试/嵌入客户端可使用不同循环，不能复用已绑定旧循环的信号量。
        self._network_limits = WeakKeyDictionary()
        self._conn = sqlite3.connect(str(self.path), timeout=0.15, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=150")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        except sqlite3.Error:
            self._conn.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def network_limit(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        with self._lock:
            if loop not in self._network_limits:
                self._network_limits[loop] = asyncio.Semaphore(CONCURRENCY)
            return self._network_limits[loop]

    def get(self, domain: str) -> tuple[bool, int | None]:
        now = int(time.time())
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT registered_at, checked_at FROM domain_age WHERE domain = ?", (domain,)
                ).fetchone()
        except sqlite3.Error:
            return False, None
        if row is None:
            return False, None
        registered = row["registered_at"]
        if registered is not None and (not isinstance(registered, int) or not 0 <= registered <= now):
            return False, None
        ttl = self._ttl if row["registered_at"] is not None else self._negative_ttl
        if not 0 <= now - row["checked_at"] < ttl:
            return False, None
        return True, registered

    def put(self, domain: str, registered_at: int | None) -> None:
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO domain_age (domain, registered_at, checked_at) VALUES (?, ?, ?)",
                    (domain, registered_at, int(time.time())),
                )
                self._conn.execute(
                    "DELETE FROM domain_age WHERE domain NOT IN "
                    "(SELECT domain FROM domain_age ORDER BY checked_at DESC, domain LIMIT ?)",
                    (MAX_CACHE_ENTRIES,),
                )
        except sqlite3.Error:
            return  # 派生缓存不可用时，搜索继续。


def _registered_at(payload: object) -> int | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return None
    for event in payload["events"]:
        if not isinstance(event, dict) or str(event.get("eventAction", "")).lower() != "registration":
            continue
        raw = event.get("eventDate")
        if not isinstance(raw, str):
            continue
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if date.tzinfo is None:
                continue
            registered = int(date.timestamp())
        except (ValueError, OverflowError, OSError):
            continue
        if 0 <= registered <= time.time():
            return registered
    return None


def _age_info(domain: str, registered: int | None) -> AgeInfo | None:
    if registered is None or not 0 <= time.time() - registered:
        return None
    return AgeInfo(domain, registered, time.time() - registered < FRESH_DAYS * 86400)


def cached_age(host: str, store: DomainAgeStore) -> AgeInfo | None:
    domain = registered_domain(host)
    if domain is None:
        return None
    hit, registered = store.get(domain)
    return _age_info(domain, registered) if hit else None


async def lookup(domain: str, store: DomainAgeStore, fetcher: SafeFetcher) -> AgeInfo | None:
    domain = registered_domain(domain)
    if domain is None:
        return None
    hit, registered = await asyncio.to_thread(store.get, domain)
    if hit:
        return _age_info(domain, registered)
    async with store.network_limit():
        # 排队时其他请求可能已填好缓存；缓存命中始终绕过网络排队。
        hit, registered = await asyncio.to_thread(store.get, domain)
        if hit:
            return _age_info(domain, registered)
        try:
            page = await fetcher.fetch(
                f"{BOOTSTRAP}{domain}", allowed_types={"application/rdap+json", "application/json"}
            )
            payload = json.loads(page.text)
        except FetchError as exc:
            if exc.status in (404, 410):
                await asyncio.to_thread(store.put, domain, None)
            return None
        except ValueError:
            return None
        registered = _registered_at(payload)
        await asyncio.to_thread(store.put, domain, registered)
        return _age_info(domain, registered)


async def enrich(results, store: DomainAgeStore, fetcher: SafeFetcher, *, cache_only: bool = False) -> int:
    domains: list[str] = []
    for item in results:
        if item.risk <= 0:
            continue
        try:
            host = urlsplit(item.url).hostname or ""
        except ValueError:
            continue
        domain = registered_domain(host)
        if domain is not None and domain not in domains:
            domains.append(domain)
        if len(domains) >= MAX_DOMAINS:
            break
    if not domains:
        return 0

    infos = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)
    rdap_fetcher = fetcher.clone_with_timeout(BUDGET_SECONDS)

    async def one(domain: str) -> None:
        async with semaphore:
            try:
                if cache_only:
                    info = await asyncio.to_thread(cached_age, domain, store)
                else:
                    info = await lookup(domain, store, rdap_fetcher)
            except Exception:
                return
            if info is not None:
                infos[domain] = info

    try:
        async with asyncio.timeout(BUDGET_SECONDS):
            await asyncio.gather(*(one(domain) for domain in domains))
    except TimeoutError:
        pass

    fresh = {domain for domain, info in infos.items() if info.fresh}
    bumped = 0
    for item in results:
        if item.risk <= 0:
            continue
        try:
            domain = registered_domain(urlsplit(item.url).hostname or "")
        except ValueError:
            continue
        if domain in fresh and AGE_REASON not in item.reasons:
            item.risk = round(min(1.0, item.risk + AGE_PENALTY), 3)
            item.reasons.append(AGE_REASON)
            bumped += 1
    return bumped
