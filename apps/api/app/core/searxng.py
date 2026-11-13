"""真实 SearXNG 客户端：一次聚合请求，超时 / 连接失败 / 坏响应分类抛出。

响应契约（M0 验收后收紧）：
- 响应必须是 JSON 对象，且必须带 results 字段；
- results 必须是列表；缺失或类型错误一律 UPSTREAM_BAD_RESPONSE，
  既不当成「零结果」，也不允许异常结构冒成 HTTP 500；
- results 非空但没有任何一条能解析出标题 + 合法 http(s) URL，同样判坏响应。
"""

from __future__ import annotations

import re
import time

import httpx

from app.config import Settings
from app.core.engine_catalog import searx_engine_name
from app.core.errors import (
    EngineUnavailable,
    EnginesUnresponsive,
    UpstreamBadResponse,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from app.core.normalize import format_unresponsive, normalise_result
from app.schemas import Result

USER_AGENT = "CleanSearch/0.1 (+local; M0)"
REGION_LANGUAGES = {"cn": "zh-CN", "jp": "ja-JP", "us": "en-US"}
_QUERY_DIRECTIVE = re.compile(r"(^|\s)([!:])(?=\S)")


def restrict_results(results: list[Result], selected: tuple[str, ...]) -> tuple[list[Result], list[str]]:
    kept = []
    for result in results:
        sources = [name for name in result.engine if name in selected]
        if sources:
            kept.append(result.model_copy(update={"engine": sources}))
    return kept, list(dict.fromkeys(name for result in kept for name in result.engine))


class SearxngClient:
    name = "searxng"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        # 测试注入 mock transport；生产保持 None 走默认网络栈
        self._transport = transport
        self._catalog_cache: tuple[float, dict[str, bool]] | None = None

    async def configured_engines(self) -> dict[str, bool]:
        if self._catalog_cache is not None and time.monotonic() < self._catalog_cache[0]:
            return self._catalog_cache[1]
        try:
            async with httpx.AsyncClient(timeout=min(3.0, self._settings.search_timeout), transport=self._transport) as client:
                response = await client.get(f"{self._settings.searxng_url}/config")
                response.raise_for_status()
                data = response.json()
            rows = data.get("engines") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ValueError
            engines = {
                row["name"]: row.get("enabled") is True and "general" in (row.get("categories") or [])
                for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)
                and row["name"] and "," not in row["name"]
            }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EngineUnavailable("无法核对 SearXNG 的已加载引擎，请检查上游的 /config") from exc
        self._catalog_cache = (time.monotonic() + 30, engines)
        return engines

    async def search(
        self,
        q: str,
        page: int,
        region: str | None,
        safe: bool,
        engine: str = "default",
        fixture: str | None = None,
        selected_engines: tuple[str, ...] | None = None,
        time_range: str | None = None,
        language: str | None = None,
        site: str | None = None,
    ) -> tuple[list[Result], list[str], list[str]]:
        base = self._settings.searxng_url
        if not base:
            raise UpstreamUnavailable("SEARXNG_URL 未配置")
        params = {
            "q": q,
            "format": "json",
            "pageno": page,
            "safesearch": 1 if safe else 0,
        }
        if region:
            params["language"] = REGION_LANGUAGES.get(region.lower(), region)
        # 显式语言优先于地区推导；时间范围透传给 SearXNG
        if language:
            params["language"] = language
        if time_range:
            params["time_range"] = time_range
        routed_engine = searx_engine_name(engine) if engine and engine != "default" else None
        missing = []
        if selected_engines is not None:
            loaded = await self.configured_engines()
            missing = [f"{name}(上游未加载)" for name in selected_engines if name not in loaded]
            selected_engines = tuple(name for name in selected_engines if name in loaded)
            if not selected_engines:
                raise EngineUnavailable("所选引擎均未在 SearXNG 加载", engines=missing)
            params["engines"] = ",".join(selected_engines)
            # SearXNG 自身的 !引擎 / :语言 优先于请求参数。保留词面并禁止其改路由。
            params["q"] = _QUERY_DIRECTIVE.sub(
                lambda match: match[1] + ("！" if match[2] == "!" else "："), q
            )
        elif routed_engine:
            params["engines"] = routed_engine
        if site:
            params["q"] = f"{params['q']} site:{site}".strip()

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.search_timeout, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{base}/search",
                    params=params,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout(
                f"SearXNG 在 {self._settings.search_timeout:g}s 内未响应（{base}）"
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"无法连接 SearXNG（{base}）：{exc.__class__.__name__}") from exc

        if response.status_code >= 500:
            raise UpstreamUnavailable(f"SearXNG 返回 {response.status_code}")
        if response.status_code != 200:
            raise UpstreamBadResponse(
                f"SearXNG 返回 {response.status_code}，请确认 settings.yml 的 search.formats 含 json"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamBadResponse("SearXNG 返回的不是 JSON，检查 formats 是否开启 json") from exc

        try:
            results, engines, unresponsive = self.parse_payload(payload)
        except EnginesUnresponsive as exc:
            if selected_engines is None:
                raise
            raise EngineUnavailable(
                "所选引擎暂未返回结果", engines=[*missing, *exc.engines],
            ) from exc
        if selected_engines is not None:
            kept, actual = restrict_results(results, selected_engines)
            if results and not kept:
                raise EngineUnavailable("SearXNG 响应未包含所选引擎的结果", engines=missing)
            return kept, actual, [*missing, *unresponsive]
        if routed_engine and results:
            results = [item for item in results if routed_engine in item.engine]
            if not results:
                raise EngineUnavailable(
                    f"指定引擎 {routed_engine} 未返回结果。请检查上游配置，或移除引擎后缀重试。",
                    engines=[f"{routed_engine}(路由未生效)"],
                )
            for item in results:
                item.engine = [routed_engine]
            engines = [routed_engine]
        return results, engines, unresponsive

    @staticmethod
    def parse_payload(payload: object) -> tuple[list[Result], list[str], list[str]]:
        if not isinstance(payload, dict):
            raise UpstreamBadResponse(
                f"响应结构异常：期望 JSON 对象，实际 {type(payload).__name__}"
            )
        if "results" not in payload:
            raise UpstreamBadResponse("响应缺少 results 字段，无法区分零结果与坏响应")
        raw_results = payload["results"]
        if not isinstance(raw_results, list):
            raise UpstreamBadResponse(
                f"results 字段类型异常：期望 list，实际 {type(raw_results).__name__}"
            )

        results: list[Result] = []
        for index, item in enumerate(raw_results, 1):
            if not isinstance(item, dict):
                continue
            parsed = normalise_result(item, index)
            if parsed is not None:
                results.append(parsed)

        if raw_results and not results:
            raise UpstreamBadResponse(
                f"results 有 {len(raw_results)} 条记录但没有一条能解析出合法 http(s) 链接"
            )

        unresponsive = format_unresponsive(payload.get("unresponsive_engines"))

        if not results and unresponsive:
            raise EnginesUnresponsive(
                "所有上游引擎均未返回结果：" + "，".join(unresponsive[:6]),
                engines=unresponsive,
            )
        engines = list(dict.fromkeys(engine for item in results for engine in item.engine))
        return results, engines, unresponsive
