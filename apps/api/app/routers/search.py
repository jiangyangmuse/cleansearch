"""POST /api/search —— 检索主链路。

查询解析 → 缓存查找 → 上游聚合 → 安全过滤 → 去重 → 打分与三档分组 → 回填缓存。
"""

from __future__ import annotations

import secrets
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.core.aggregator import Aggregator, get_aggregator
from app.core.normalize import dedupe_results, dedupe_similar_titles
from app.core.expand import expand_aliases
from app.core.query_parser import parse_query
from app.core.redirect import build_go_path
from app.core.safety import Blocklist, SafetyScorer
from app.core.scoring import group_results, score_results
from app.core.session_store import SessionStore, Source, get_session_store
from app.core.tokens import get_api_token
from app.db.cache import Cache, get_cache, search_key
from app.schemas import (
    FilteredCounts,
    Groups,
    ParsedQuery,
    Result,
    SearchMeta,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/api", tags=["search"])


def _sid() -> str:
    return "s_" + secrets.token_hex(16)


@lru_cache(maxsize=1)
def get_safety() -> SafetyScorer:
    settings = get_settings()
    return SafetyScorer(
        Blocklist(settings.blocklist_path, extra_paths=(settings.feed_output_path,))
    )


def _register_snapshot(
    store: SessionStore, sid: str, query: str, results: list[Result], provider: str
) -> None:
    if not results:
        return
    store.put(
        sid,
        query,
        [
            Source(
                result_id=item.id,
                url=item.url,
                title=item.title,
                snippet=item.snippet,
                domain=(item.display_url.split(" › ")[0] if item.display_url else ""),
            )
            for item in results
        ],
        provider=provider,
    )


def _serialise_groups(strong, related, weak) -> dict:
    return {
        "strong": [item.model_dump() for item in strong],
        "related": [item.model_dump() for item in related],
        "weak": [item.model_dump() for item in weak],
    }


async def _attach_go_links(results: list[Result], token_path: Path) -> None:
    suspicious = [item for item in results if 0.35 <= item.risk < 0.6]
    if not suspicious:
        return
    secret = await run_in_threadpool(get_api_token, token_path)
    for item in suspicious:
        item.go_url = build_go_path(item.url, secret)


@router.post("/search", response_model=SearchResponse, response_model_exclude_none=False)
async def search(
    payload: SearchRequest,
    aggregator: Aggregator = Depends(get_aggregator),
    safety: SafetyScorer = Depends(get_safety),
    store: SessionStore = Depends(get_session_store),
    cache: Cache | None = Depends(get_cache),
) -> SearchResponse:
    settings = get_settings()
    started = time.perf_counter()
    parsed = parse_query(payload.q)
    region = parsed.region or (payload.region or "").strip() or None
    aliases = expand_aliases(parsed.q)
    parsed_response = ParsedQuery(
        q=parsed.q,
        engine=parsed.engine,
        region=region,
        router=parsed.router,
        expanded=aliases,
    )
    provider = aggregator.provider_name

    qkey = None
    revision = ""
    if cache is not None and settings.cache_enabled:
        revision = safety.blocklist.revision
        qkey = search_key(
            parsed.q,
            parsed.engine,
            region,
            payload.page,
            payload.opts.safe,
            payload.opts.fixture,
            namespace=(provider, settings.searxng_url if provider == "searxng" else "", revision),
        )
        cached = await run_in_threadpool(cache.get_search, qkey)
        if cached and cached.get("provider") == provider and safety.blocklist.revision == revision:
            try:
                groups = Groups.model_validate(cached["groups"])
                results = groups.strong + groups.related + groups.weak
                meta = SearchMeta(
                    status="ok" if results else "empty",
                    engines=cached["engines"], unresponsive=cached["unresponsive"], provider=provider,
                    cached=True, ms=int((time.perf_counter() - started) * 1000), total=len(results),
                    upstream_total=cached["upstream_total"], filtered=cached["filtered"], sid=_sid(),
                )
            except (KeyError, ValidationError):
                pass  # 可丢弃的缓存，损坏时重新检索
            else:
                await _attach_go_links(results, settings.api_token_path)
                _register_snapshot(store, meta.sid, parsed.q, results, provider)
                return SearchResponse(parsed=parsed_response, groups=groups, meta=meta)

    outcome = await aggregator.search(
        q=parsed.q,
        page=payload.page,
        region=region,
        safe=payload.opts.safe,
        engine=parsed.engine,
        fixture=payload.opts.fixture,
    )

    kept = []
    blocked = 0
    for item in outcome.results:
        report = safety.evaluate(item.url)
        item.risk = report.risk
        if report.blocked:
            blocked += 1
            continue
        kept.append(item)

    deduped, url_duplicates = dedupe_results(kept)
    deduped, title_duplicates = dedupe_similar_titles(deduped)
    score_results(parsed.q, deduped, aliases)

    strong, related, weak = group_results(deduped)
    results = strong + related + weak
    total = len(results)

    sid = _sid()
    _register_snapshot(store, sid, parsed.q, results, outcome.provider)

    filtered = FilteredCounts(dup=url_duplicates + title_duplicates, risk=blocked)
    # 部分引擎失败是常态（CAPTCHA / 限流），只要拿到了结果就缓存；
    # 「本次哪些引擎没给结果」仍写进 payload，命中时可原样展示。
    if cache is not None and qkey and results and safety.blocklist.revision == revision:
        await run_in_threadpool(
            cache.put_search,
            qkey,
            {
                "groups": _serialise_groups(strong, related, weak),
                "engines": outcome.engines,
                "unresponsive": outcome.unresponsive,
                "provider": outcome.provider,
                "total": total,
                "upstream_total": len(outcome.results),
                "filtered": filtered.model_dump(),
            },
        )

    # 签名随响应生成，避免把与本地 token 绑定的链接写进持久化缓存。
    await _attach_go_links(results, settings.api_token_path)
    return SearchResponse(
        parsed=parsed_response,
        groups=Groups(strong=strong, related=related, weak=weak),
        meta=SearchMeta(
            status="ok" if total else "empty",
            engines=outcome.engines,
            unresponsive=outcome.unresponsive,
            provider=outcome.provider,
            cached=False,
            ms=outcome.ms,
            total=total,
            upstream_total=len(outcome.results),
            filtered=filtered,
            sid=sid,
        ),
    )
