"""单进程搜索快照：按 sid 短期保存本次结果源，供侧栏总结读取。

- TTL 默认 15 分钟，容量默认 64 条，超出按最近最少使用淘汰；
- 只保存通过安全过滤 + 去重 + 分档后的结果，避免把被拦截的链接喂给模型；
- 单进程内存实现，符合首版「本机单用户」定位。
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal


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
    def __init__(self, ttl_seconds: int = 900, capacity: int = 64) -> None:
        self._ttl = ttl_seconds
        self._capacity = max(1, capacity)
        self._items: "OrderedDict[str, Snapshot]" = OrderedDict()

    def put(
        self, sid: str, query: str, sources: list[Source], provider: str = "searxng"
    ) -> Snapshot:
        snapshot = Snapshot(sid=sid, query=query, sources=sources, provider=provider)
        self._items[sid] = snapshot
        self._items.move_to_end(sid)
        self._evict_expired()
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)
        return snapshot

    def get(self, sid: str) -> Snapshot | None:
        self._evict_expired()
        snapshot = self._items.get(sid)
        if snapshot is None:
            return None
        self._items.move_to_end(sid)
        return snapshot

    def _evict_expired(self) -> None:
        if self._ttl <= 0:
            return
        cutoff = time.time() - self._ttl
        for sid in [key for key, snap in self._items.items() if snap.created_at < cutoff]:
            self._items.pop(sid, None)

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._items)


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    from app.config import get_settings

    settings = get_settings()
    return SessionStore(ttl_seconds=settings.session_ttl, capacity=settings.session_capacity)
