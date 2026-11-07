"""SearXNG 适配器契约测试：用 MockTransport 注入受控响应，不碰网络。

覆盖 M0 验收报告点名的四类缺陷：
- results 缺失被当成零结果
- results 类型错误（{"results": 7}）冒成 TypeError / HTTP 500
- file:// 等非 http(s) 链接通过归一化
- 超时 / 连接失败 / 5xx / 非 JSON 的错误分类
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.config import Settings, get_settings
from app.core.errors import UpstreamBadResponse, UpstreamTimeout, UpstreamUnavailable
from app.core.searxng import SearxngClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HIT = json.loads((FIXTURES / "searxng_hit.json").read_text(encoding="utf-8"))
EMPTY = json.loads((FIXTURES / "searxng_empty.json").read_text(encoding="utf-8"))


def make_settings(**overrides: object) -> Settings:
    base = replace(
        get_settings(),
        provider="searxng",
        searxng_url="http://upstream.test",
        search_timeout=0.5,
        llm_provider="stub",
        llm_base_url="",
        llm_timeout=1.0,
        llm_stub_delay=0.0,
    )
    return replace(base, **overrides) if overrides else base



def make_client(handler, **overrides: object) -> SearxngClient:
    return SearxngClient(make_settings(**overrides), transport=httpx.MockTransport(handler))


async def test_client_hit_keeps_candidates_for_safety_filter() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(200, json=HIT)

    client = make_client(handler)
    results, engines, unresponsive = await client.search("test", 1, None, True)

    assert len(results) == 11
    assert any("utm_source" in result.url for result in results)
    assert unresponsive == []
    assert {"google", "brave", "bing", "duckduckgo"} <= set(engines)
    assert "format=json" in str(seen["url"])
    assert seen["accept"] == "application/json"


async def test_client_empty_results_are_zero_not_error() -> None:
    client = make_client(lambda request: httpx.Response(200, json=EMPTY))
    results, engines, unresponsive = await client.search("nothing", 1, None, True)
    assert results == [] and engines == [] and unresponsive == []


@pytest.mark.parametrize(("region", "language"), [("cn", "zh-CN"), ("jp", "ja-JP"), ("us", "en-US"), ("en-GB", "en-GB")])
async def test_client_uses_searxng_route_names(region: str, language: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["language"] == language
        assert request.url.params["engines"] == "google scholar"
        return httpx.Response(200, json=EMPTY)

    await make_client(handler).search("paper", 1, region, True, engine="scholar")


async def test_client_all_engines_unresponsive() -> None:
    payload = dict(EMPTY, unresponsive_engines=[["google", "timeout"], ["bing", "CAPTCHA"]])
    client = make_client(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(UpstreamUnavailable) as excinfo:
        await client.search("test", 1, None, True)
    assert "google(timeout)" in excinfo.value.message


async def test_client_missing_results_field_is_bad_response() -> None:
    client = make_client(lambda request: httpx.Response(200, json={"query": "test"}))
    with pytest.raises(UpstreamBadResponse) as excinfo:
        await client.search("test", 1, None, True)
    assert "results" in excinfo.value.message


async def test_client_results_wrong_type_is_bad_response() -> None:
    client = make_client(lambda request: httpx.Response(200, json={"results": 7}))
    with pytest.raises(UpstreamBadResponse):
        await client.search("test", 1, None, True)


async def test_client_all_entries_unparseable_is_bad_response() -> None:
    payload = {"results": ["not-a-dict", 42, {"url": "file:///etc/passwd", "title": "本地文件"}]}
    client = make_client(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(UpstreamBadResponse):
        await client.search("test", 1, None, True)


async def test_client_partial_garbage_entries_are_skipped() -> None:
    payload = {
        "results": [
            "junk",
            {"url": "file:///etc/passwd", "title": "本地文件"},
            {"url": "https://user:pass@example.com/", "title": "带凭证的链接"},
            {
                "url": "https://example.com/ok",
                "title": "正常结果",
                "content": "ok",
                "engine": "google",
                "score": 10**400,
            },
        ]
    }
    client = make_client(lambda request: httpx.Response(200, json=payload))
    results, *_ = await client.search("test", 1, None, True)
    assert [r.url for r in results] == ["https://example.com/ok"]
    assert results[0].score == 0.0


async def test_client_non_json_body_is_bad_response() -> None:
    client = make_client(
        lambda request: httpx.Response(
            200, content=b"<html>captcha</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(UpstreamBadResponse) as excinfo:
        await client.search("test", 1, None, True)
    assert "json" in excinfo.value.message.lower()


async def test_client_5xx_is_unavailable() -> None:
    client = make_client(lambda request: httpx.Response(503, text="upstream down"))
    with pytest.raises(UpstreamUnavailable):
        await client.search("test", 1, None, True)


async def test_client_4xx_is_bad_response() -> None:
    client = make_client(lambda request: httpx.Response(403, text="limiter"))
    with pytest.raises(UpstreamBadResponse):
        await client.search("test", 1, None, True)


async def test_client_connect_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = make_client(handler)
    with pytest.raises(UpstreamUnavailable):
        await client.search("test", 1, None, True)


async def test_client_timeout_is_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(UpstreamTimeout):
        await client.search("test", 1, None, True)


async def test_client_without_base_url_is_unavailable() -> None:
    client = make_client(lambda request: httpx.Response(200, json=EMPTY), searxng_url="")
    with pytest.raises(UpstreamUnavailable):
        await client.search("test", 1, None, True)