"""真实 SearXNG 客户端：一次聚合请求，超时 / 连接失败 / 坏响应分类抛出。

响应契约（M0 验收后收紧）：
- 响应必须是 JSON 对象，且必须带 results 字段；
- results 必须是列表；缺失或类型错误一律 UPSTREAM_BAD_RESPONSE，
  既不当成「零结果」，也不允许异常结构冒成 HTTP 500；
- results 非空但没有任何一条能解析出标题 + 合法 http(s) URL，同样判坏响应。
"""

from __future__ import annotations

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

    async def search(
        self,
        q: str,
        page: int,
        region: str | None,
        safe: bool,
        engine: str = "default",
        fixture: str | None = None,
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
        routed_engine = searx_engine_name(engine) if engine and engine != "default" else None
        if routed_engine:
            params["engines"] = routed_engine

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

        results, engines, unresponsive = self.parse_payload(payload)
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
