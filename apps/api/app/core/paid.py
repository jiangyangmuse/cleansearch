"""商用搜索兜底：Brave Search API / Serper.dev。

没有 key 就完全不发请求；有 key 时默认聚合的第 1 页会补一路结果；
显式引擎（g/gc/sc/br）仅在第 1 页、主引擎与回退链全部失败后走对应接口。
按 canonical URL 去重，来源写进 meta.engines，失败只记该引擎，不影响主链路。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings
from app.core.engine_catalog import paid_route
from app.core.normalize import normalise_result
from app.schemas import Result

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
SERPER_ENDPOINT = "https://google.serper.dev/search"
SERPER_SCHOLAR_ENDPOINT = "https://google.serper.dev/scholar"
TIMEOUT = 6.0


@dataclass
class PaidResult:
    results: list[Result]
    engine: str
    error: str = ""


def _parse_items(items: object, engine: str, url_field: str, snippet_field: str) -> PaidResult:
    if not isinstance(items, list):
        return PaidResult([], engine, "响应缺少结果列表")
    results = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        url = item.get(url_field)
        parsed = normalise_result({
            "url": url, "title": item.get("title") or url,
            "content": item.get(snippet_field), "engine": engine,
        }, index)
        if parsed is not None:
            results.append(parsed)
    if items and not results:
        return PaidResult([], engine, "返回条目均无法解析为有效结果")
    return PaidResult(results, engine)


class PaidSearch:
    """按配置选择 Brave 或 Serper；两者都没有 key 时 build_paid_search 返回 None。"""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._brave_key = (settings.brave_api_key or "").strip()
        self._serper_key = (settings.serper_api_key or "").strip()
        self._transport = transport

    @property
    def engine(self) -> str:
        if self._brave_key:
            return "brave"
        if self._serper_key:
            return "serper"
        return ""

    @property
    def engines(self) -> tuple[str, ...]:
        """可用提供商标识，用于缓存隔离，不包含凭据。"""
        return tuple(name for name, key in (("brave", self._brave_key), ("serper", self._serper_key)) if key)

    def provider_for_engine(self, engine: str) -> str:
        route = paid_route(engine)
        if route in {"search", "scholar"} and self._serper_key:
            return "serper"
        if route == "brave" and self._brave_key:
            return "brave"
        return ""

    async def search(self, q: str, page: int = 1, region: str | None = None) -> PaidResult:
        if self._brave_key:
            return await self._brave(q, page, region)
        if self._serper_key:
            return await self._serper(q, page, region)
        return PaidResult(results=[], engine="", error="未配置商用检索 key")

    async def search_for_engine(
        self, engine: str, q: str, page: int = 1, region: str | None = None
    ) -> PaidResult | None:
        """显式引擎失败后的定向兜底；该引擎没有对应接口时返回 None。"""
        route = paid_route(engine)
        if route == "search" and self._serper_key:
            return await self._serper(q, page, region)
        if route == "scholar" and self._serper_key:
            return await self._serper_scholar(q, page, region)
        if route == "brave" and self._brave_key:
            return await self._brave(q, page, region)
        return None

    async def _brave(self, q: str, page: int, region: str | None) -> PaidResult:
        params = {"q": q, "count": 10, "offset": max(0, (page - 1) * 10), "safesearch": "moderate"}
        if region:
            params["country"] = region.upper()
        headers = {"X-Subscription-Token": self._brave_key, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, transport=self._transport, follow_redirects=False, trust_env=True
            ) as client:
                response = await client.get(BRAVE_ENDPOINT, params=params, headers=headers)
        except httpx.HTTPError as exc:
            return PaidResult([], "brave", f"连接失败：{exc.__class__.__name__}")
        if response.status_code != 200:
            return PaidResult([], "brave", f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            return PaidResult([], "brave", "返回不是 JSON")

        web = payload.get("web") if isinstance(payload, dict) else None
        items = web.get("results") if isinstance(web, dict) else None
        return _parse_items(items, "brave", "url", "description")

    async def _serper(self, q: str, page: int, region: str | None) -> PaidResult:
        headers = {"X-API-KEY": self._serper_key, "Content-Type": "application/json"}
        body: dict = {"q": q, "num": 10, "page": max(1, page)}
        if region:
            body["gl"] = region.lower()
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, transport=self._transport, follow_redirects=False, trust_env=True
            ) as client:
                response = await client.post(SERPER_ENDPOINT, json=body, headers=headers)
        except httpx.HTTPError as exc:
            return PaidResult([], "serper", f"连接失败：{exc.__class__.__name__}")
        if response.status_code != 200:
            return PaidResult([], "serper", f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            return PaidResult([], "serper", "返回不是 JSON")

        items = payload.get("organic") if isinstance(payload, dict) else None
        return _parse_items(items, "serper", "link", "snippet")

    async def _serper_scholar(self, q: str, page: int, region: str | None) -> PaidResult:
        headers = {"X-API-KEY": self._serper_key, "Content-Type": "application/json"}
        body: dict = {"q": q, "num": 10, "page": max(1, page)}
        if region:
            body["gl"] = region.lower()
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, transport=self._transport, follow_redirects=False, trust_env=True
            ) as client:
                response = await client.post(SERPER_SCHOLAR_ENDPOINT, json=body, headers=headers)
        except httpx.HTTPError as exc:
            return PaidResult([], "serper", f"连接失败：{exc.__class__.__name__}")
        if response.status_code != 200:
            return PaidResult([], "serper", f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            return PaidResult([], "serper", "返回不是 JSON")

        items = payload.get("organic") if isinstance(payload, dict) else None
        return _parse_items(items, "serper", "link", "snippet")


def build_paid_search(settings: Settings, transport=None) -> PaidSearch | None:
    if not (settings.brave_api_key or settings.serper_api_key):
        return None
    if not settings.paid_fallback:
        return None
    return PaidSearch(settings, transport=transport)
