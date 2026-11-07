"""favicon 本地缓存。

结果卡与书签卡不再直接引用目标站图标：由后端拉一次、落盘、按 host 缓存，
避免离线裂图、也避免每次渲染都向目标站发请求（顺带少一个跟踪面）。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app.core.fetch import FetchBlocked, FetchError, SafeFetcher

MAX_BYTES = 200 * 1024
TTL = 7 * 24 * 3600
NEGATIVE_TTL = 3600
ICON_TYPES = {
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}


class FaviconCache:
    def __init__(self, directory: Path, fetcher: SafeFetcher) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fetcher = fetcher

    def _base(self, host: str) -> Path:
        digest = hashlib.sha1(host.lower().encode("utf-8")).hexdigest()[:24]
        return self.dir / digest

    def cached(self, host: str) -> tuple[Path, str] | None:
        base = self._base(host)
        meta_path = base.with_suffix(".json")
        file_path = base.with_suffix(".bin")
        if not meta_path.is_file() or not file_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(meta, dict):
            return None
        timestamp = meta.get("ts")
        content_type = meta.get("content_type")
        if not isinstance(timestamp, (int, float)) or not isinstance(content_type, str):
            return None
        if time.time() - timestamp > TTL or content_type not in ICON_TYPES:
            return None
        return file_path, content_type

    def is_negative(self, host: str) -> bool:
        marker = self._base(host).with_suffix(".miss")
        if not marker.is_file():
            return False
        try:
            return time.time() - float(marker.read_text(encoding="utf-8")) < NEGATIVE_TTL
        except (OSError, ValueError):
            return False

    async def fetch(self, host: str) -> tuple[Path | None, str]:
        """返回 (文件路径, content_type)；失败时写负缓存并返回 (None, "")。"""
        url = f"https://{host}/favicon.ico"
        try:
            page = await self._fetcher.fetch(url, max_bytes=MAX_BYTES, allowed_types=ICON_TYPES)
        except FetchError as exc:
            if isinstance(exc, FetchBlocked):
                return None, ""
            self._write_miss(host)
            return None, ""
        content_type = page.content_type or ""
        if content_type not in ICON_TYPES or page.truncated:
            self._write_miss(host)
            return None, ""

        base = self._base(host)
        file_path = base.with_suffix(".bin")
        file_path.write_bytes(page.raw or page.text.encode("utf-8", "ignore"))
        base.with_suffix(".json").write_text(
            json.dumps({"host": host, "content_type": content_type, "ts": int(time.time())}),
            encoding="utf-8",
        )
        return file_path, content_type

    def _write_miss(self, host: str) -> None:
        try:
            self._base(host).with_suffix(".miss").write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass
