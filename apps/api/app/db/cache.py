"""SQLite 缓存：搜索结果和单页总结，各自限制保留条数。

- 搜索缓存有 TTL（默认 900s），过期即视为未命中；
- 单页总结按正文与模型输入存，只缓存生成内容；
- 与书签共用同一个 DB 文件，独立表，互不影响。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_cache (
  qkey    TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  ts      INTEGER NOT NULL,
  ttl     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS summaries (
  content_hash TEXT PRIMARY KEY,
  url          TEXT,
  title        TEXT,
  payload      TEXT NOT NULL,
  model        TEXT,
  ts           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_summaries_ts ON summaries(ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_cache_ts ON search_cache(ts DESC);
"""


def search_key(
    q: str,
    engine: str = "default",
    region: str | None = None,
    page: int = 1,
    safe: bool = True,
    fixture: str | None = None,
    *,
    namespace: tuple[str, ...] = (),
) -> str:
    raw = json.dumps(
        ["search-v5", namespace, q, engine, region, page, safe, fixture],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def summary_key(*parts: str | int | None) -> str:
    raw = json.dumps(["page-summary-v2", *parts], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, db_path: Path, ttl: int = 900, max_entries: int = 512) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl
        self._max_entries = max(1, max_entries)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), timeout=0.15, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            # 单文件多连接：给写入排队，避免 database is locked
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
        except sqlite3.Error:
            self._conn.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- 搜索缓存 ----------
    def get_search(self, qkey: str) -> dict | None:
        return self._read(
            "SELECT payload FROM search_cache WHERE qkey = ? AND ts + ttl > ?", (qkey, int(time.time()))
        )

    def put_search(self, qkey: str, payload: dict, ttl: int | None = None) -> None:
        now = int(time.time())
        try:
            with self._lock, self._conn:
                self._conn.execute("DELETE FROM search_cache WHERE ts + ttl <= ?", (now,))
                self._conn.execute(
                    "INSERT OR REPLACE INTO search_cache (qkey, payload, ts, ttl) VALUES (?, ?, ?, ?)",
                    (qkey, json.dumps(payload, ensure_ascii=False), now, self._ttl if ttl is None else ttl),
                )
                self._trim("search_cache")
        except sqlite3.Error as exc:
            logger.debug("search cache write skipped: %s", exc)

    # ---------- 单页总结 ----------
    def get_summary(self, content_hash: str) -> dict | None:
        return self._read("SELECT payload FROM summaries WHERE content_hash = ?", (content_hash,))

    def put_summary(
        self, content_hash: str, url: str, title: str, payload: dict, model: str
    ) -> None:
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO summaries (content_hash, url, title, payload, model, ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (content_hash, url, title, json.dumps(payload, ensure_ascii=False), model, int(time.time())),
                )
                self._trim("summaries")
        except sqlite3.Error as exc:
            logger.debug("summary cache write skipped: %s", exc)

    def _read(self, sql: str, params: tuple) -> dict | None:
        try:
            with self._lock:
                row = self._conn.execute(sql, params).fetchone()
            payload = json.loads(row["payload"]) if row else None
            return payload if isinstance(payload, dict) else None
        except (sqlite3.Error, ValueError, TypeError) as exc:
            logger.debug("cache read skipped: %s", exc)
            return None

    def _trim(self, table: str) -> None:
        self._conn.execute(
            f"DELETE FROM {table} WHERE rowid IN ("
            f"SELECT rowid FROM {table} ORDER BY ts DESC, rowid DESC LIMIT -1 OFFSET ?)",
            (self._max_entries,),
        )

    # ---------- 维护 ----------
    def purge(self) -> int:
        cutoff = int(time.time())
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM search_cache WHERE ts + ttl <= ?", (cutoff,)
            )
            self._conn.commit()
        return cursor.rowcount

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM search_cache")
            self._conn.execute("DELETE FROM summaries")
            self._conn.commit()


@lru_cache(maxsize=1)
def _open_cache(path: Path, ttl: int, max_entries: int) -> Cache:
    return Cache(path, ttl, max_entries)


def get_cache() -> Cache | None:
    from app.config import get_settings

    settings = get_settings()
    if not settings.cache_enabled:
        return None
    try:
        return _open_cache(settings.db_path, settings.cache_ttl, settings.cache_max_entries)
    except (OSError, sqlite3.Error) as exc:
        logger.debug("cache unavailable: %s", exc)
        return None
