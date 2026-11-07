"""静态资源代理：favicon 本地缓存。"""

from __future__ import annotations

import re
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.favicon import FaviconCache
from app.core.fetch import SafeFetcher
from app.deps import get_fetcher

router = APIRouter(prefix="/api")
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
ICON_HEADERS = {
    "Cache-Control": "public, max-age=604800",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
}


@lru_cache(maxsize=1)
def get_favicon_cache() -> FaviconCache:
    settings = get_settings()
    return FaviconCache(settings.favicon_dir, SafeFetcher(timeout=5.0, max_bytes=200 * 1024))


@router.get("/favicon")
async def favicon(
    host: str,
    fetcher: SafeFetcher = Depends(get_fetcher),
) -> FileResponse:
    host = (host or "").strip().lower().rstrip(".")
    if not HOST_RE.fullmatch(host):
        raise HTTPException(status_code=400, detail="host 参数不合法")

    cache = get_favicon_cache()
    cache._fetcher = fetcher
    icon = cache.cached(host)
    if icon is None:
        if cache.is_negative(host):
            raise HTTPException(status_code=404, detail="没有可用的 favicon")
        icon = await cache.fetch(host)
    path, content_type = icon
    if path is None:
        raise HTTPException(status_code=404, detail="没有可用的 favicon")
    return FileResponse(path, media_type=content_type, headers=ICON_HEADERS)
