"""POST /api/page/summarize —— 单页正文总结（M4）。

抓取走受控入口（SSRF 白名单 + 大小/耗时上限），提取后复用总结管线。
"""

from __future__ import annotations

import asyncio
import re
from contextlib import aclosing
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.extract import Article, extract_article
from app.core.fetch import FetchedPage, FetchBlocked, FetchError, FetchTimeout, SafeFetcher
from app.core.llm import LLMError, LLMTimeout
from app.core.model_routing import ModelActionError
from app.core.model_settings import ModelSettings, read_model_settings
from app.core.session_store import Snapshot, Source
from app.config import get_settings
from app.core.summarize import FULL_CHARS_PER_SOURCE, Summarizer, get_summarizer, summarize_with_models
from app.db.cache import Cache, get_cache, summary_key
from app.deps import get_fetcher

router = APIRouter(prefix="/api", tags=["page"])

MIN_CONTENT_CHARS = 80
PAGE_TEXT_LIMIT = 6000
BULLET_PREFIX = re.compile(r"^\s*(?:[-*·]\s+|\d+[.)、]\s*)")
DIVERGENCE = re.compile(r"^\s*(分歧|分歧点)[:：]")
SENTENCE_END = re.compile(r"(?<=[。！？!?])\s*(?!\[\d+\])|(?<=\.)\s+")


class PageRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    max_chars: int | None = Field(default=None, ge=200, le=20000)


class PagesRequest(BaseModel):
    urls: list[Annotated[str, Field(min_length=1, max_length=2048)]] = Field(min_length=1, max_length=5)


def _structure(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullets = [BULLET_PREFIX.sub("", line) for line in lines if BULLET_PREFIX.match(line)]
    caveats = [DIVERGENCE.sub("", line).strip() for line in lines if DIVERGENCE.match(line)]
    prose = [line for line in lines if not BULLET_PREFIX.match(line) and not DIVERGENCE.match(line)]
    one_liner = (prose or bullets or lines or [""])[0]
    if not bullets and prose:
        sentences = [s.strip() for line in prose for s in SENTENCE_END.split(line) if s.strip()]
        if sentences:
            one_liner, *bullets = sentences[:4]
    return {"one_liner": one_liner, "bullets": bullets, "key_data": [], "caveats": caveats}


KEY_DATA = re.compile(
    r"(?<![\w.])(\d[\d,.]*\s*(?:%|个百分点|倍|GB|MB|KB|TB|ms|毫秒|秒|分钟|小时|万|亿|元|美元|条|台|人))"
)
SENTENCE_SPLIT = re.compile(r"[。！？\n]|(?<=\.)\s")


def _key_data(text: str, limit: int = 8) -> list[dict]:
    """从原文抽「数字 + 单位」的关键数据；启发式，不做语义判断。"""
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for sentence in SENTENCE_SPLIT.split(text):
        sentence = (sentence or "").strip()
        if not sentence:
            continue
        for match in KEY_DATA.finditer(sentence):
            value = match.group(1).strip()
            label = sentence[max(0, match.start() - 24): match.start()].strip() or "原文数据"
            key = (label, value)
            if key in seen:
                continue
            seen.add(key)
            found.append({"label": label[-40:], "value": value})
            if len(found) >= limit:
                return found
    return found


def _anchors(text: str, limit: int = 5) -> list[dict]:
    """原文段落锚点：段落序号 + 首句，供人工回原文定位（不是 DOM 锚点）。"""
    paragraphs = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20]
    return [{"i": index, "text": paragraph[:80]} for index, paragraph in enumerate(paragraphs[:limit], 1)]


async def _load_article(url: str, fetcher: SafeFetcher) -> tuple[FetchedPage, Article]:
    try:
        page = await fetcher.fetch(url)
    except FetchBlocked as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except FetchTimeout as exc:
        raise HTTPException(status_code=504, detail=exc.message) from exc
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    article = await run_in_threadpool(extract_article, page.text, page.url)
    if len(article.text.strip()) < MIN_CONTENT_CHARS:
        raise HTTPException(
            status_code=422,
            detail="正文过短或需要登录，无法总结（可能是付费墙、反爬或纯图片页面）",
        )
    return page, article


@router.post("/page/summarize")
async def page_summarize(
    payload: PageRequest,
    fetcher: SafeFetcher = Depends(get_fetcher),
    summarizer: Summarizer = Depends(get_summarizer),
    cache: Cache | None = Depends(get_cache),
    model_settings: ModelSettings = Depends(read_model_settings),
) -> dict:
    url = payload.url.strip()
    page, article = await _load_article(url, fetcher.clone_with_timeout(max(10.0, fetcher.timeout)))
    limit = payload.max_chars or PAGE_TEXT_LIMIT
    settings = get_settings()
    key = None
    text = None
    used_model = summarizer.model
    routed = model_settings.routed("summary")
    if cache is not None and settings.cache_enabled and not routed:
        key = summary_key(
            article.content_hash, page.url, article.title, limit, summarizer.model,
            settings.llm_provider, settings.llm_base_url, settings.llm_reasoning_effort,
        )
        cached = await run_in_threadpool(cache.get_summary, key)
        cached_text = cached.get("summary_text") if cached else None
        if isinstance(cached_text, str) and cached_text.strip():
            text = cached_text

    reused = text is not None
    if not reused:
        snapshot = _page_snapshot(page.url, article.title, article.text[:limit])
        if routed:
            try:
                text, used_model = await summarize_with_models(snapshot, model_settings, summarizer)
            except LLMError as exc:
                raise ModelActionError(exc) from exc
        else:
            text = await _generate_summary(snapshot, summarizer)
        if cache is not None and key and text.strip():
            await run_in_threadpool(
                cache.put_summary, key, page.url, article.title or "", {"summary_text": text}, summarizer.model,
            )

    return {
        "url": url,
        "final_url": page.url,
        "title": article.title,
        "byline": article.byline,
        "published": article.published,
        "word_count": article.word_count,
        "read_minutes": article.read_minutes,
        "content_hash": article.content_hash,
        "extractor": article.extractor,
        "truncated": page.truncated,
        "summary": _structure(text),
        # 数据与锚点直接从原文抽，避免模型编数字；模型输出只负责结论与要点
        "key_data": _key_data(article.text),
        "anchors": _anchors(article.text),
        "summary_text": text,
        "model": used_model,
        "cached": reused,
    }


def _page_snapshot(url: str, title: str, excerpt: str) -> Snapshot:
    host = urlsplit(url).netloc
    return Snapshot(
        sid="page",
        query=title or host,
        sources=[
            Source(
                result_id="r_1",
                url=url,
                title=title or host,
                snippet=excerpt,
                domain=host,
            )
        ],
        provider="page",
    )


async def _generate_summary(snapshot: Snapshot, summarizer: Summarizer) -> str:
    collected: list[str] = []
    try:
        async with aclosing(summarizer.stream(snapshot)) as stream:
            async for token in stream:
                collected.append(token)
    except LLMTimeout as exc:
        raise HTTPException(status_code=504, detail=exc.message) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    return "".join(collected)


@router.post("/pages/summarize")
async def pages_summarize(
    payload: PagesRequest,
    fetcher: SafeFetcher = Depends(get_fetcher),
    summarizer: Summarizer = Depends(get_summarizer),
    model_settings: ModelSettings = Depends(read_model_settings),
) -> dict:
    urls = list(dict.fromkeys(url.strip() for url in payload.urls if url.strip()))
    if not urls:
        raise HTTPException(422, "请填写至少一个网址")
    page_fetcher = fetcher.clone_with_timeout(max(10.0, fetcher.timeout))

    async def one(url: str) -> tuple[dict, Source | None]:
        try:
            page, article = await _load_article(url, page_fetcher)
        except HTTPException as exc:
            return {"url": url, "error": exc.detail}, None
        truncated = page.truncated or len(article.text) > FULL_CHARS_PER_SOURCE
        return {"url": url, "final_url": page.url, "title": article.title, "truncated": truncated}, Source(
            result_id="page", url=page.url, title=article.title, domain=urlsplit(page.url).netloc,
            snippet=article.text[:FULL_CHARS_PER_SOURCE], material="truncated" if truncated else "full",
        )

    fetched = await asyncio.gather(*(one(url) for url in urls))
    outcomes = [outcome for outcome, _ in fetched]
    sources = [source for _, source in fetched if source is not None]
    if not sources:
        return {"pages": outcomes, "summary": "", "model": None}
    snapshot = Snapshot(
        sid="pages", query="逐篇概括各网页的主要内容，并以编号标注来源；有多篇时补充共同点与差异。",
        sources=sources, provider="pages",
    )
    try:
        text, model = await summarize_with_models(snapshot, model_settings, summarizer)
    except LLMError as exc:
        raise ModelActionError(exc) from exc
    return {"pages": outcomes, "summary": text, "model": model}
