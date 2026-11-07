"""搜索快照：SQLite 版，跨进程/跨重启可用。

以前放进程内存，多 worker 时各存各的、重启即失效；
改存 SQLite（与书签同库），TTL 与容量淘汰逻辑保持不变。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_sessions (
  sid        TEXT PRIMARY KEY,
  query      TEXT NOT NULL,
  provider   TEXT NOT NULL,
  sources    TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON search_sessions(created_at);
"""


@dataclass(frozen=True)
class Source:
    result_id: str
    url: str
    title: str
    snippet: str
    domain: str
    material: Literal["snippet", "full", "truncated"] = "snippet"


@dataclass
class Snapshot:
    sid: str
    query: str
    sources: list[Source]
    provider: str
    created_at: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, db_path: Path, ttl_seconds: int = 900, capacity: int = 64) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put(self, sid: str, query: str, sources: list[Source], provider: str = "searxng") -> Snapshot:
        now = time.time()
        payload = json.dumps(
            [
                {
                    "result_id": s.result_id,
                    "url": s.url,
                    "title": s.title,
                    "snippet": s.snippet,
                    "domain": s.domain,
                    "material": s.material,
                }
                for s in sources
            ],
            ensure_ascii=False,
        )
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO search_sessions (sid, query, provider, sources, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sid, query, provider, payload, int(now)),
            )
            self._evict_locked(now)
            self._conn.commit()
        return Snapshot(sid=sid, query=query, sources=list(sources), provider=provider, created_at=now)

    def get(self, sid: str) -> Snapshot | None:
        now = time.time()
        with self._lock:
            self._evict_locked(now)
            row = self._conn.execute(
                "SELECT * FROM search_sessions WHERE sid = ?", (sid,)
            ).fetchone()
            self._conn.commit()
        if row is None:
            return None
        try:
            raw = json.loads(row["sources"])
        except json.JSONDecodeError:
            return None
        sources = [
            Source(
                result_id=item.get("result_id", ""),
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                domain=item.get("domain", ""),
                material=item.get("material", "snippet"),
            )
            for item in raw
        ]
        return Snapshot(
            sid=row["sid"],
            query=row["query"],
            sources=sources,
            provider=row["provider"],
            created_at=float(row["created_at"]),
        )

    def _evict_locked(self, now: float) -> None:
        if self._ttl > 0:
            self._conn.execute(
                "DELETE FROM search_sessions WHERE created_at < ?", (int(now - self._ttl),)
            )
        self._conn.execute(
            "DELETE FROM search_sessions WHERE sid NOT IN ("
            "SELECT sid FROM search_sessions ORDER BY created_at DESC LIMIT ?)",
            (self._capacity,),
        )

    def __len__(self) -> int:
        with self._lock:
            self._evict_locked(time.time())
            return int(self._conn.execute("SELECT COUNT(*) FROM search_sessions").fetchone()[0])


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    from app.config import get_settings

    settings = get_settings()
    return SessionStore(settings.db_path, ttl_seconds=settings.session_ttl, capacity=settings.session_capacity)
