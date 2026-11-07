"""共享依赖：抓取器单例，测试可通过 dependency_overrides 替换。"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.fetch import SafeFetcher


@lru_cache(maxsize=1)
def get_fetcher() -> SafeFetcher:
    settings = get_settings()
    return SafeFetcher(
        timeout=settings.fetch_timeout,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
        extra_cidrs=settings.fetch_extra_cidrs,
    )
