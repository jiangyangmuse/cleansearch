"""打磨轮：搜索缓存与单页总结缓存。"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.aggregator import Aggregated, get_aggregator
from app.core.fetch import SafeFetcher
from app.core.safety import Blocklist, SafetyScorer
from app.core.summarize import get_summarizer
from app.db.cache import Cache, search_key
from app.deps import get_fetcher
from app.main import app
from app.db.cache import get_cache
import app.routers.page as page_router
import app.routers.search as search_router

ARTICLE = """<html><head><title>缓存测试页</title></head><body><article>
<p>正文第一段，说明事件循环如何调度协程与回调。</p>
<p>正文第二段，强调不要在协程里做同步阻塞调用，否则会拖慢整个循环。</p>
<p>正文第三段，给出一个最小可运行的示例与常见错误。</p>
</article></body></html>"""


@pytest.fixture()
def cache(tmp_path) -> Cache:
    instance = Cache(tmp_path / "cache.db", ttl=60)
    yield instance
    instance.close()


def test_search_key_is_stable_and_sensitive() -> None:
    base = search_key("python", "google", "cn", 1, True, None)
    assert base == search_key("python", "google", "cn", 1, True, None)
    assert base != search_key("python", "google", "cn", 2, True, None)
    assert base != search_key("python", "bing", "cn", 1, True, None)
    assert len(base) == 32


def test_cache_hit_miss_and_ttl(cache: Cache, monkeypatch) -> None:
    key = search_key("q")
    assert cache.get_search(key) is None

    cache.put_search(key, {"total": 1}, ttl=1)
    assert cache.get_search(key) == {"total": 1}

    # 时间前进 2 秒后过期
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 2)
    assert cache.get_search(key) is None


def test_summary_cache_roundtrip(cache: Cache) -> None:
    assert cache.get_summary("sha1:abc") is None
    cache.put_summary("sha1:abc", "https://e.test/a", "标题", {"summary_text": "内容"}, "stub")
    assert cache.get_summary("sha1:abc")["summary_text"] == "内容"


def test_cache_retains_only_latest_entries_in_each_table(tmp_path) -> None:
    cache = Cache(tmp_path / "limited.db", max_entries=2)
    try:
        for key in ("old", "recent", "new"):
            cache.put_search(key, {"key": key})
            cache.put_summary(key, "https://e.test/", "", {"key": key}, "stub")
        assert cache.get_search("old") is None and cache.get_summary("old") is None
        assert cache.get_search("recent") == {"key": "recent"}
        assert cache.get_summary("new") == {"key": "new"}
    finally:
        cache.close()


@pytest.fixture()
def cached_client(client: TestClient, cache: Cache, monkeypatch):
    monkeypatch.setattr(
        search_router, "get_settings", lambda: replace(get_settings(), cache_enabled=True)
    )
    monkeypatch.setattr(
        page_router, "get_settings", lambda: replace(get_settings(), cache_enabled=True)
    )
    app.dependency_overrides[get_cache] = lambda: cache
    yield client
    app.dependency_overrides.pop(get_cache, None)


def test_search_uses_cache_on_repeat(cached_client: TestClient) -> None:
    first = cached_client.post("/api/search", json={"q": "python 文档"}).json()
    second = cached_client.post("/api/search", json={"q": "python 文档"}).json()

    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert second["meta"]["sid"] != first["meta"]["sid"]
    assert [r["url"] for r in second["groups"]["strong"]] == [
        r["url"] for r in first["groups"]["strong"]
    ]
    assert second["meta"]["filtered"] == first["meta"]["filtered"]
    assert second["meta"]["total"] == first["meta"]["total"]

    # 命中缓存后仍能生成总结（快照按新 sid 重新登记）
    sid = second["meta"]["sid"]
    with cached_client.stream("GET", "/api/summarize", params={"sid": sid}) as response:
        body = "".join(response.iter_text())
    assert "event: cite" in body and "event: done" in body


def test_different_query_misses_cache(cached_client: TestClient) -> None:
    cached_client.post("/api/search", json={"q": "python 文档"})
    other = cached_client.post("/api/search", json={"q": "asyncio"}).json()
    assert other["meta"]["cached"] is False


def test_cached_risk_links_use_current_token(cached_client: TestClient, tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "api-token.txt"
    monkeypatch.setenv("API_TOKEN_PATH", str(token_path))
    get_settings.cache_clear()

    def search_risky():
        body = cached_client.post(
            "/api/search", json={"q": "账号验证", "opts": {"fixture": "risky"}}
        ).json()
        paths = [item["go_url"] for group in body["groups"].values() for item in group if item["go_url"]]
        return body["meta"]["cached"], paths[0]

    try:
        cached, old_path = search_risky()
        assert not cached and cached_client.get(old_path).status_code == 200
        token_path.write_text("rotated-test-token", encoding="utf-8")
        cached, new_path = search_risky()
        assert cached and new_path != old_path
        assert cached_client.get(new_path).status_code == 200
        assert cached_client.get(old_path).status_code == 403
    finally:
        get_settings.cache_clear()


def test_new_blocklist_invalidates_cached_result_and_snapshot(cached_client: TestClient, tmp_path) -> None:
    rules = tmp_path / "blocklist.txt"
    rules.write_text("", encoding="utf-8")
    scorer = SafetyScorer(Blocklist(rules))
    app.dependency_overrides[search_router.get_safety] = lambda: scorer
    try:
        query = {"q": "python 文档"}
        first = cached_client.post("/api/search", json=query).json()
        host = "fastapi.tiangolo.com"
        assert any(host in row["url"] for group in first["groups"].values() for row in group)
        assert cached_client.post("/api/search", json=query).json()["meta"]["cached"]
        rules.write_text(host + "\n", encoding="utf-8")
        fresh = cached_client.post("/api/search", json=query).json()
        warm = cached_client.post("/api/search", json=query).json()
        assert not fresh["meta"]["cached"] and warm["meta"]["cached"]
        assert warm["meta"]["filtered"]["risk"] == 1
        assert all(host not in row["url"] for group in warm["groups"].values() for row in group)
        stream = cached_client.get("/api/summarize", params={"sid": warm["meta"]["sid"]})
        assert "event: done" in stream.text and host not in stream.text
    finally:
        app.dependency_overrides.pop(search_router.get_safety, None)


def test_search_does_not_reuse_fixture_or_partial_results(cached_client: TestClient) -> None:
    class Upstream:
        provider_name = "searxng"

        async def search(self, **kwargs):
            return Aggregated([], unresponsive=["google"], provider=self.provider_name)

    query = {"q": "python 文档"}
    assert cached_client.post("/api/search", json=query).json()["meta"]["provider"] == "fixture"
    app.dependency_overrides[get_aggregator] = Upstream
    try:
        for _ in range(2):
            response = cached_client.post("/api/search", json=query).json()
            assert response["meta"]["provider"] == "searxng"
            assert response["meta"]["cached"] is False
    finally:
        app.dependency_overrides.pop(get_aggregator, None)


def test_search_succeeds_when_sqlite_cache_is_busy(cached_client: TestClient, cache: Cache) -> None:
    writer = sqlite3.connect(cache.path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        response = cached_client.post("/api/search", json={"q": "python 文档"})
        assert response.status_code == 200 and response.json()["meta"]["cached"] is False
    finally:
        writer.close()
    assert not cached_client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["cached"]
    assert cached_client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["cached"]


def test_paid_setting_changes_do_not_reuse_search_cache(cached_client: TestClient) -> None:
    from app.core.aggregator import Aggregator
    from app.core.paid import PaidSearch
    from app.core.searxng import SearxngClient

    holder = {}
    app.dependency_overrides[get_aggregator] = lambda: holder["aggregator"]
    try:
        for enabled in (False, True, False):
            settings = replace(get_settings(), provider="searxng", brave_api_key="", serper_api_key="test", paid_fallback=enabled)
            aggregator = Aggregator(settings)
            aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"results": []})
            ))
            if enabled:
                aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={
                        "organic": [{"link": "https://paid.test/a", "title": "HTTP"}]
                    })
                ))
            holder["aggregator"] = aggregator
            body = cached_client.post("/api/search", json={"q": "HTTP"}).json()
            assert bool(body["meta"]["total"]) is enabled
            assert body["meta"]["cached"] is False
    finally:
        app.dependency_overrides.pop(get_aggregator, None)


def test_page_summary_cache_hit(cached_client: TestClient, cache: Cache) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    fetcher = SafeFetcher(
        timeout=0.5, transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"]
    )
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    try:
        first = cached_client.post("/api/page/summarize", json={"url": "https://e.test/a"})
        second = cached_client.post("/api/page/summarize", json={"url": "https://e.test/a"})
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert first.status_code == 200, first.text
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["content_hash"] == first.json()["content_hash"]
    assert calls["n"] == 2  # 缓存命中也要先抓页面拿正文哈希，省的是模型调用


def test_explicit_paid_capability_change_invalidates_cache_with_same_preferred_provider(cached_client):
    from app.core.aggregator import Aggregator
    from app.core.paid import PaidSearch
    from app.core.searxng import SearxngClient

    holder = {}
    app.dependency_overrides[get_aggregator] = lambda: holder["aggregator"]
    try:
        for serper in ("", "test"):
            settings = replace(get_settings(), provider="searxng", brave_api_key="test",
                               serper_api_key=serper, paid_fallback=True)
            aggregator = Aggregator(settings)
            assert aggregator.paid_provider == "brave"
            aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={
                    "results": [{"url": "https://example.com/a", "title": "HTTP", "engine": "bing"}]
                })
            ))
            # 正常显式结果不应触发付费；测试只验证配置切换后的缓存隔离。
            aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(
                lambda request: pytest.fail("healthy explicit search must not spend")
            ))
            holder["aggregator"] = aggregator
            first = cached_client.post("/api/search", json={"q": "HTTP b"}).json()
            assert first["meta"]["cached"] is False
            assert cached_client.post("/api/search", json={"q": "HTTP b"}).json()["meta"]["cached"]
    finally:
        app.dependency_overrides.pop(get_aggregator, None)


def test_page_cache_respects_model_limit_and_current_url(cached_client: TestClient) -> None:
    model_calls = []

    class Model:
        model = "test-a"

        async def stream(self, snapshot):
            model_calls.append(self.model)
            yield f"{self.model} 的结论。"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/alias":
            return httpx.Response(302, headers={"location": "/a"})
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    fetcher = SafeFetcher(
        transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"]
    )
    model = Model()
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    app.dependency_overrides[get_summarizer] = lambda: model
    try:
        def fetch(url, max_chars=None):
            response = cached_client.post("/api/page/summarize", json={"url": url, "max_chars": max_chars})
            assert response.status_code == 200, response.text
            return response.json()

        assert not fetch("https://e.test/a")["cached"]
        alias = fetch("https://e.test/alias")
        assert alias["cached"] and alias["url"] == "https://e.test/alias" and alias["final_url"] == "https://e.test/a"
        mirror = fetch("https://e.test/mirror")
        assert not mirror["cached"] and mirror["final_url"] == "https://e.test/mirror"
        assert not fetch("https://e.test/a", 200)["cached"]
        model.model = "test-b"
        updated = fetch("https://e.test/a")
        assert not updated["cached"] and updated["summary"]["one_liner"] == "test-b 的结论。"
        assert model_calls == ["test-a", "test-a", "test-a", "test-b"]
    finally:
        app.dependency_overrides.pop(get_fetcher, None)
        app.dependency_overrides.pop(get_summarizer, None)


def test_partial_engine_failure_is_still_cached(cached_client: TestClient, cache: Cache) -> None:
    """真实上游几乎每次都有引擎 CAPTCHA；这类结果也要缓存，否则缓存永远不生效。"""
    from dataclasses import replace

    import httpx

    import app.core.aggregator as aggregator_module
    from app.config import get_settings

    payload = {
        "results": [
            {
                "url": "https://partial.test/a",
                "title": "部分成功的结果",
                "content": "这条结果来自可用的引擎，另一个引擎 CAPTCHA 了。",
                "engine": "google cse",
            }
        ],
        "unresponsive_engines": [["duckduckgo", "CAPTCHA"]],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    from app.core.searxng import SearxngClient

    settings = replace(get_settings(), provider="searxng", searxng_url="http://upstream.test")
    aggregator = aggregator_module.Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(handler))

    from app.core.aggregator import get_aggregator
    from app.main import app

    app.dependency_overrides[get_aggregator] = lambda: aggregator
    try:
        first = cached_client.post("/api/search", json={"q": "partial engine"}).json()
        second = cached_client.post("/api/search", json={"q": "partial engine"}).json()
    finally:
        app.dependency_overrides.pop(get_aggregator, None)

    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert second["meta"]["unresponsive"] == ["duckduckgo(CAPTCHA)"]
