"""Resolve and execute a feature's primary and explicitly enabled backup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from typing import TypeVar

import httpx

from app.config import get_settings
from app.core.errors import SearchError
from app.core.fetch import SafeFetcher
from app.core.llm import LLMBadResponse, LLMError, LLMTimeout, OpenAICompatibleClient
from app.core.model_settings import Feature, LOOPBACK, ModelEntry, ModelSettings


T = TypeVar("T")
FALLBACK_DISABLED = "当前模型不可用，备选模型未开启此功能"


class ModelRouteError(LLMError):
    retryable = False

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ModelActionError(SearchError):
    def __init__(self, error: LLMError):
        self.code = error.code
        self.retryable = error.retryable
        self.http_status = 504 if isinstance(error, LLMTimeout) else 503
        super().__init__(error.message)


def imported_client(model: ModelEntry) -> OpenAICompatibleClient:
    settings = get_settings()
    url = httpx.URL(model.base_url)
    local = url.host in LOOPBACK
    return OpenAICompatibleClient(
        model.base_url, model.api_key.get_secret_value() if model.api_key else "", model.model,
        settings.llm_timeout, reasoning_effort="none" if local and url.port == 11434 else None,
        endpoint_guard=None if local else SafeFetcher(extra_cidrs=settings.fetch_extra_cidrs),
        trust_env=False,
    )


def configured_client() -> OpenAICompatibleClient | None:
    settings = get_settings()
    if settings.llm_provider != "openai" or not settings.llm_base_url:
        return None
    return OpenAICompatibleClient(
        settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout,
        reasoning_effort=settings.llm_reasoning_effort,
    )


async def collect_text(stream: AsyncGenerator[str, None], *, limit: int = 32000) -> str:
    parts: list[str] = []
    size = 0
    try:
        async with asyncio.timeout(get_settings().llm_timeout + 30), aclosing(stream):
            async for part in stream:
                parts.append(part)
                size += len(part)
                if size > limit:
                    raise LLMBadResponse("模型输出超过长度上限")
    except TimeoutError as exc:
        raise LLMTimeout("生成内容超时") from exc
    text = "".join(parts).strip()
    if not text:
        raise LLMBadResponse("模型没有生成可显示的内容")
    return text


async def route_model(
    config: ModelSettings,
    feature: Feature,
    run: Callable[[ModelEntry], Awaitable[T]],
    builtin: Callable[[], Awaitable[tuple[T, str]]],
) -> tuple[T, str]:
    route = config.assignment(feature)
    models = {model.id: model for model in config.models}
    try:
        if route.primary is None:
            return await builtin()
        primary = models[route.primary]
        if feature not in primary.features:
            raise ModelRouteError("MODEL_FEATURE_DISABLED", "当前模型未开启此功能")
        return await run(primary), primary.label
    except (LLMError, SearchError) as exc:
        if route.fallback is None:
            raise
        fallback = models[route.fallback]
        if feature not in fallback.features:
            raise ModelRouteError("MODEL_FALLBACK_DISABLED", FALLBACK_DISABLED) from exc
        return await run(fallback), fallback.label
