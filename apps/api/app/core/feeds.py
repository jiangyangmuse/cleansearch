"""黑名单 feed：解析、合并与刷新。

只做「能自己做」的部分：OpenPhish 这类无 key 的纯文本列表，以及本地文件。
GSB / URLhaus 需要 API key，未接入（见 docs/进展与欠账.md）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.fetch import FetchError, SafeFetcher

MAX_FEED_BYTES = 10 * 1024 * 1024
URL_LIKE = re.compile(r"^https?://", re.IGNORECASE)
COMMENT = re.compile(r"^\s*(#|//|;)")


@dataclass
class FeedResult:
    url: str
    ok: bool
    entries: int
    message: str = ""


def parse_feed(text: str) -> set[str]:
    """一行一条：完整 URL 或域名；忽略注释与空行，去掉明显的 HTML 噪声。"""
    entries: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or COMMENT.match(line) or "<" in line:
            continue
        if URL_LIKE.match(line):
            entries.add(line.split()[0].rstrip("/"))
        else:
            host = line.split()[0].lower().strip(".")
            if host and "." in host and len(host) < 254:
                entries.add(host)
    return entries


def merge_into(path: Path, entries: set[str]) -> int:
    existing = set()
    if path.is_file():
        existing = parse_feed(path.read_text(encoding="utf-8", errors="replace"))
    merged = existing | entries
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# 由 scripts/refresh-feeds 或 POST /api/tools/refresh-feeds 生成，勿手改\n"
    path.write_text(header + "\n".join(sorted(merged)) + "\n", encoding="utf-8")
    return len(merged)


async def refresh(urls: list[str], output: Path, fetcher: SafeFetcher) -> list[FeedResult]:
    results: list[FeedResult] = []
    collected: set[str] = set()
    for url in urls:
        try:
            page = await fetcher.fetch(url, max_bytes=MAX_FEED_BYTES)
        except FetchError as exc:
            results.append(FeedResult(url=url, ok=False, entries=0, message=exc.message))
            continue
        entries = parse_feed(page.text)
        collected |= entries
        results.append(FeedResult(url=url, ok=True, entries=len(entries)))
    if collected:
        merge_into(output, collected)
    return results
