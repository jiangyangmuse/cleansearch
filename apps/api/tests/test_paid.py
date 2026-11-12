"""商用兜底（Brave / Serper）契约测试：不联系真实接口，只用 MockTransport。"""

from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.config import get_settings
from app.core import aggregator as aggregator_module
from app.core.breaker import EngineHealthStore, UPSTREAM_KEY
from app.core.paid import PaidSearch, build_paid_search
from app.core.searxng import SearxngClient
from app.core.errors import SearchError


def brave_payload(urls: list[str]) -> dict:
    return {
        "web": {
            "results": [
                {"url": url, "title": f"标题 {index}", "description": "摘要"}
                for index, url in enumerate(urls)
            ]
        }
    }


def test_no_key_means_no_request() -> None:
    settings = replace(get_settings(), brave_api_key="", serper_api_key="")
    assert build_paid_search(settings) is None


def test_brave_results_are_normalised() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.headers["x-subscription-token"] == "test-key"
        return httpx.Response(200, json=brave_payload(["https://paid.test/a", "https://paid.test/b"]))

    settings = replace(get_settings(), brave_api_key="test-key", serper_api_key="")
    paid = PaidSearch(settings, transport=httpx.MockTransport(handler))
    result = __import__("asyncio").run(paid.search("HTTP"))

    assert result.error == ""
    assert result.engine == "brave"
    assert [item.url for item in result.results] == ["https://paid.test/a", "https://paid.test/b"]
    assert all(item.engine == ["brave"] for item in result.results)
    assert calls["n"] == 1


def test_serper_results_are_normalised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["q"] == "HTTP" and body["num"] == 10
        return httpx.Response(
            200,
            json={"organic": [{"link": "https://serper.test/x", "title": "X", "snippet": "S"}]},
        )

    settings = replace(get_settings(), brave_api_key="", serper_api_key="serper-key")
    paid = PaidSearch(settings, transport=httpx.MockTransport(handler))
    result = __import__("asyncio").run(paid.search("HTTP"))

    assert result.engine == "serper" and result.results[0].url == "https://serper.test/x"


def test_serper_scholar_route_is_used_for_scholar_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://google.serper.dev/scholar"
        body = json.loads(request.content)
        assert body["q"] == "RAG"
        return httpx.Response(
            200,
            json={"organic": [{"link": "https://paper.test/x", "title": "Paper", "snippet": "S"}]},
        )

    settings = replace(get_settings(), brave_api_key="", serper_api_key="serper-key")
    paid = PaidSearch(settings, transport=httpx.MockTransport(handler))
    result = __import__("asyncio").run(paid.search_for_engine("scholar", "RAG"))

    assert result is not None and result.engine == "serper"
    assert result.results[0].url == "https://paper.test/x"


def test_paid_route_returns_none_for_engines_without_paid_endpoint() -> None:
    settings = replace(get_settings(), brave_api_key="", serper_api_key="serper-key")
    paid = PaidSearch(settings, transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert __import__("asyncio").run(paid.search_for_engine("bing", "HTTP")) is None


def test_http_error_is_reported_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    settings = replace(get_settings(), brave_api_key="test-key", serper_api_key="")
    paid = PaidSearch(settings, transport=httpx.MockTransport(handler))
    result = __import__("asyncio").run(paid.search("HTTP"))

    assert result.results == []
    assert "429" in result.error


def test_aggregator_uses_paid_only_after_default_failure() -> None:
    settings = replace(get_settings(), provider="searxng", brave_api_key="test-key", serper_api_key="")
    aggregator = aggregator_module.Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(503)
    ))
    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=brave_payload(["https://paid.test/only", "https://example.com/dup"]),
        )
    ))

    result = __import__("asyncio").run(aggregator.search("HTTP"))
    urls = [item.url for item in result.results]

    assert "brave" in result.engines
    assert "https://paid.test/only" in urls
    # 同一 URL 只保留主上游那一条
    assert urls.count("https://example.com/dup") <= 1


def test_paid_failure_does_not_break_search() -> None:
    settings = replace(get_settings(), provider="searxng", brave_api_key="test-key", serper_api_key="")
    aggregator = aggregator_module.Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "results": [{"url": "https://main.test/a", "title": "主上游", "engine": "google"}]
        })
    ))
    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(500, json={})
    ))

    result = __import__("asyncio").run(aggregator.search("HTTP"))
    assert result.results, "主上游结果必须保留"
    assert not result.unresponsive, "健康免费检索不触发付费或记录付费故障"


@pytest.mark.parametrize("failure", ["connection", "engines", "circuit"])
async def test_paid_recovers_failed_primary(failure, tmp_path) -> None:
    settings = replace(get_settings(), provider="searxng", brave_api_key="", serper_api_key="test", breaker_enabled=True)
    health = EngineHealthStore(tmp_path / "health.db", fail_threshold=3, cooldown=60)
    aggregator = aggregator_module.Aggregator(settings, health=health)
    calls = []

    def primary(request):
        calls.append("primary")
        if failure == "engines":
            return httpx.Response(200, json={"results": [], "unresponsive_engines": [["google", "timeout"]]})
        raise httpx.ConnectError("offline", request=request)

    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(primary))
    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"organic": [{"link": "https://serper.test/a", "title": "paid"}]})
    ))
    if failure == "circuit":
        for _ in range(3):
            health.record_failure(UPSTREAM_KEY, "offline")
    try:
        result = await aggregator.search("HTTP")
        assert result.results and result.engines == ["serper"] and result.unresponsive
        assert calls == ([] if failure == "circuit" else ["primary"])
        assert health.row("serper").fails == 0
        if failure == "circuit":
            assert health.is_open(UPSTREAM_KEY)
    finally:
        health.close()


async def test_fixture_never_spends_paid_requests() -> None:
    settings = replace(get_settings(), provider="fixture", brave_api_key="test-key", serper_api_key="")
    aggregator = aggregator_module.Aggregator(settings)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(handler))
    assert (await aggregator.search("HTTP")).results
    assert not calls


@pytest.mark.parametrize("payload", [[], {"organic": {}}, {"organic": [None, {"link": "https://[broken", "title": "bad"}]}])
async def test_malformed_paid_response_is_reported(payload) -> None:
    settings = replace(get_settings(), brave_api_key="", serper_api_key="test")
    paid = PaidSearch(settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    outcome = await paid.search("HTTP")
    assert outcome.error and not outcome.results


async def test_paid_circuit_records_each_failure_once(tmp_path) -> None:
    settings = replace(get_settings(), provider="searxng", brave_api_key="", serper_api_key="test", breaker_enabled=True)
    health = EngineHealthStore(tmp_path / "paid-health.db", fail_threshold=3, cooldown=60)
    aggregator = aggregator_module.Aggregator(settings, health=health)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(503)
    ))
    calls = []

    def paid_failure(request):
        calls.append(request)
        return httpx.Response(429)

    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(paid_failure))
    try:
        for _ in range(4):
            with pytest.raises(SearchError):
                await aggregator.search("HTTP")
        assert len(calls) == 3 and health.row("serper").fails == 3
    finally:
        health.close()


@pytest.mark.parametrize(("page", "engine"), [(2, "default"), (1, "google")])
async def test_explicit_engine_and_later_pages_skip_paid(page, engine) -> None:
    settings = replace(get_settings(), provider="searxng", brave_api_key="", serper_api_key="test")
    aggregator = aggregator_module.Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    ))

    calls = []

    def paid_handler(request):
        # 翻页和显式引擎正常零结果都不应触发付费。
        calls.append(request)
        return httpx.Response(200, json={"organic": []})

    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(paid_handler))
    assert not (await aggregator.search("HTTP", page=page, engine=engine)).results
    assert calls == []


def test_canonical_duplicate_retains_both_sources() -> None:
    from app.core.normalize import normalise_result, dedupe_results
    # 去重仍保留已有来源；不以额外付费调用制造同 URL 共识。
    results, count = dedupe_results([
        normalise_result({"url": "https://example.com/a?utm_source=primary", "title": "HTTP", "engine": "google"}, 1),
        normalise_result({"url": "https://example.com/a", "title": "HTTP", "engine": "serper"}, 2),
    ])
    assert count == 1 and len(results) == 1 and set(results[0].engine) == {"google", "serper"}
