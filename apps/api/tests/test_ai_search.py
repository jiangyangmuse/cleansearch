import json

import httpx
import pytest

from app.core.ai_search import DeepSeekSearch, get_ai_search_provider
from app.core.normalize import normalise_result
from app.db.cache import Cache, get_cache
from app.main import app


def test_ai_search_uses_web_api_and_caches_without_changing_main_search(client, monkeypatch, tmp_path):
    calls = []
    rows = [
        {"url": "https://zh.wikipedia.org/wiki/Arknights", "title": "明日方舟"},
        {"url": "https://apps.apple.com/cn/app/arknights/id1454663939", "title": "明日方舟 App"},
        {"url": "https://www.bilibili.com/video/BV123", "title": "明日方舟视频"},
        {"url": "https://zh.wikipedia.org/wiki/Arknights?utm_source=duplicate", "title": "重复条目"},
        {"url": "https://unknown.example/", "title": "明日方舟官网"},
        {"url": "javascript:alert(1)", "title": "无效网址"},
    ]

    def upstream(request):
        assert str(request.url) == "https://api.deepseek.com/v1/tools/search"
        assert request.headers["Authorization"] == "Bearer test-key"
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"results": rows})

    provider = DeepSeekSearch("test-key", httpx.MockTransport(upstream))
    cache = Cache(tmp_path / "search.db")
    monkeypatch.setitem(app.dependency_overrides, get_ai_search_provider, lambda: provider)
    monkeypatch.setitem(app.dependency_overrides, get_cache, lambda: cache)
    try:
        main = client.post("/api/search", json={"q": "明日方舟 ds"}).json()
        assert main["parsed"]["q"] == "明日方舟"
        assert main["official"]["entries"][0]["url"] == "https://ak.hypergryph.com/"
        assert not calls
        first = client.post("/api/ai-search", json={"q": "明日方舟 ds"}).json()
        second = client.post("/api/ai-search", json={"q": "明日方舟 !ds"}).json()
        assert calls == [{"query": "明日方舟", "count": 10, "need_content": False}]
        assert not first["cached"] and second["cached"]
        assert first["results"] == second["results"]
        assert [item["category"] for item in first["results"]] == ["encyclopedia", "download", "video"]
        assert all(item["id"].startswith("ai_") for item in first["results"])
    finally:
        cache.close()


def test_ai_search_reports_insufficient_balance_separately(client, monkeypatch):
    provider = DeepSeekSearch("test-key", httpx.MockTransport(lambda _: httpx.Response(402)))
    monkeypatch.setitem(app.dependency_overrides, get_ai_search_provider, lambda: provider)
    ai = client.post("/api/ai-search", json={"q": "nexon ds"})
    assert ai.status_code == 503
    assert "余额" in ai.json()["error"]["message"]
    ordinary = client.post("/api/search", json={"q": "nexon ds"}).json()
    assert ordinary["official"]["entries"][0]["url"] == "https://www.nexon.com/main/en"


def test_literal_query_preserves_translated_suffix_in_both_routes(client, monkeypatch):
    received = []

    def upstream(request):
        received.append(json.loads(request.content)["query"])
        return httpx.Response(200, json={"results": []})

    provider = DeepSeekSearch("test-key", httpx.MockTransport(upstream))
    monkeypatch.setitem(app.dependency_overrides, get_ai_search_provider, lambda: provider)
    query = {"q": "Nintendo ds", "opts": {"literal": True}}
    main = client.post("/api/search", json=query)
    assert main.status_code == 200
    parsed = main.json()["parsed"]
    assert (parsed["q"], parsed["engine"], parsed["router"]) == ("Nintendo ds", "default", "default")
    assert client.post("/api/ai-search", json=query).status_code == 200
    assert received == ["Nintendo ds"]


@pytest.mark.parametrize("url", [
    "https://youtube.com.example.org/watch?v=123",
    "https://www.bilibili.com/read/cv123",
    "https://play.google.com/books/details",
    "https://github.com/project/wiki",
])
def test_category_keeps_similar_pages_in_web_results(url):
    assert normalise_result({"title": "搜索结果", "url": url}, 1).category is None
