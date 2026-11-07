"""引擎健康与熔断（构建方案 §7.2）。

SearXNG 自己会并发多个引擎，但它不会替你跳过「已经连续失败的引擎」。
这里做两层：

1. **上游层**：整个 SearXNG 实例连续失败 → 熔断，快速 503，避免每次查询都等超时；
2. **引擎层**：从响应的 unresponsive_engines 记录失败，显式指定引擎且该引擎在熔断期时直接给出可读错误。

状态落在 SQLite 的 engine_health 表（与书签同库），重启后仍记得冷却期。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS engine_health (
  engine      TEXT PRIMARY KEY,
  fails       INTEGER NOT NULL DEFAULT 0,
  open_until  INTEGER NOT NULL DEFAULT 0,
  last_ok     INTEGER,
  avg_ms      INTEGER,
  last_error  TEXT
);
"""

UPSTREAM_KEY = "upstream"


@dataclass(frozen=True)
class HealthRow:
    engine: str
    fails: int
    open_until: int
    last_ok: int | None
    avg_ms: int | None
    last_error: str | None

    @property
    def open(self) -> bool:
        return self.open_until > int(time.time())


def engine_name(raw: str) -> str:
    """把 "google(timeout)" 还原成 "google"。"""
    return raw.split("(", 1)[0].strip()


class EngineHealthStore:
    def __init__(self, db_path: Path, fail_threshold: int = 3, cooldown: int = 3600) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._threshold = max(1, fail_threshold)
        self._cooldown = max(1, cooldown)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- 查询 ----------
    def row(self, engine: str) -> HealthRow:
        found = self._conn.execute(
            "SELECT * FROM engine_health WHERE engine = ?", (engine,)
        ).fetchone()
        if found is None:
            return HealthRow(engine, 0, 0, None, None, None)
        return HealthRow(
            engine=found["engine"],
            fails=found["fails"],
            open_until=found["open_until"],
            last_ok=found["last_ok"],
            avg_ms=found["avg_ms"],
            last_error=found["last_error"],
        )

    def is_open(self, engine: str) -> bool:
        return self.row(engine).open

    def remaining(self, engine: str) -> int:
        return max(0, self.row(engine).open_until - int(time.time()))

    def snapshot(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM engine_health ORDER BY engine"
        ).fetchall()
        now = int(time.time())
        return [
            {
                "engine": row["engine"],
                "fails": row["fails"],
                "open": row["open_until"] > now,
                "remaining_seconds": max(0, row["open_until"] - now),
                "avg_ms": row["avg_ms"],
                "last_error": row["last_error"],
            }
            for row in rows
        ]

    # ---------- 记录 ----------
    def record_success(self, engine: str, latency_ms: int | None = None) -> None:
        now = int(time.time())
        with self._lock:
            existing = self._conn.execute(
                "SELECT avg_ms FROM engine_health WHERE engine = ?", (engine,)
            ).fetchone()
            avg = existing["avg_ms"] if existing else None
            if latency_ms is not None:
                # 简单指数平滑，避免一次抖动污染长期均值
                avg = latency_ms if avg is None else int(avg * 0.7 + latency_ms * 0.3)
            self._conn.execute(
                "INSERT INTO engine_health (engine, fails, open_until, last_ok, avg_ms, last_error) "
                "VALUES (?, 0, 0, ?, ?, NULL) "
                "ON CONFLICT(engine) DO UPDATE SET fails = 0, open_until = 0, last_ok = ?, avg_ms = ?, last_error = NULL",
                (engine, now, avg, now, avg),
            )
            self._conn.commit()

    def record_failure(self, engine: str, error: str = "") -> HealthRow:
        now = int(time.time())
        with self._lock:
            current = self._conn.execute(
                "SELECT fails FROM engine_health WHERE engine = ?", (engine,)
            ).fetchone()
            fails = (current["fails"] if current else 0) + 1
            open_until = now + self._cooldown if fails >= self._threshold else 0
            self._conn.execute(
                "INSERT INTO engine_health (engine, fails, open_until, last_error) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(engine) DO UPDATE SET fails = ?, open_until = ?, last_error = ?",
                (engine, fails, open_until, error[:200], fails, open_until, error[:200]),
            )
            self._conn.commit()
        return self.row(engine)


@lru_cache(maxsize=1)
def get_health_store() -> EngineHealthStore:
    settings = get_settings()
    return EngineHealthStore(
        settings.db_path,
        fail_threshold=settings.breaker_fails,
        cooldown=settings.breaker_cooldown,
    )
