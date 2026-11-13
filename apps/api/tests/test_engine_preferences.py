from dataclasses import replace

import httpx
import pytest

from app.config import get_settings
from app.core.aggregator import Aggregator, get_aggregator
from app.core.engine_preferences import EnginePreferencesStore, get_engine_preferences_store, read_engine_preferences
from app.core.searxng import SearxngClient
from app.db.cache import Cache, get_cache
from app.main import app
from app.routers import search as search_router


def entry(code, kind, target):
    return {"code": code, "label": code, "kind": kind, "target": target}


@pytest.fixture
def engine_setup(monkeypatch, tmp_path):
    calls = []

    def upstream(request):
        if request.url.path == "/config":
            return httpx.Response(200, json={"engines": [
                {"name": name, "enabled": name == "bing", "categories": ["general"]}
                for name in ("bing", "360search", "bilibili")
            ]})
        params = dict(request.url.params)
        calls.append(params)
        names = params.get("engines", "bing").split(",")
        return httpx.Response(200, json={"results": [
            {
                "title": f"测试结果 {index} {name}", "url": f"https://result{index}.example.test/",
                "content": "示例搜索结果", "engines": [name, "unselected"],
            }
            for index, name in enumerate(names, 1)
        ]})

    settings = replace(get_settings(), provider="searxng", searxng_url="http://searx.test", cache_enabled=True,
                       paid_fallback=False, breaker_enabled=False)
    aggregator = Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, httpx.MockTransport(upstream))
    store = EnginePreferencesStore(tmp_path / "settings.db")
    cache = Cache(tmp_path / "cache.db")
    monkeypatch.setattr(search_router, "get_settings", lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_engine_preferences_store, lambda: store)
    monkeypatch.setitem(app.dependency_overrides, read_engine_preferences, store.read)
    monkeypatch.setitem(app.dependency_overrides, get_aggregator, lambda: aggregator)
    monkeypatch.setitem(app.dependency_overrides, get_cache, lambda: cache)
    yield calls
    cache.close()


def test_selection_is_exact_isolates_cache_and_leaves_manual_bang_available(client, engine_setup):
    settings = "/api/settings/engines"
    initial = client.get(settings).json()
    assert initial["preferences"]["default_engines"] is None
    assert initial["sources"] == {"bing": True, "360search": False, "bilibili": False}
    assert {row["code"] for row in initial["builtins"] if row["section"] == "mainland"} == {"b", "sg", "so", "bd"}

    assert client.put(settings, json={"default_engines": ["b", "so"]}).status_code == 200
    first = client.post("/api/search", json={"q": "!g 示例搜索"})
    assert first.status_code == 200
    assert engine_setup[-1]["engines"] == "360search,bing"
    assert engine_setup[-1]["q"].startswith("！g ")
    assert set(first.json()["meta"]["engines"]) == {"bing", "360search"}
    assert all("unselected" not in row["engine"] for group in first.json()["groups"].values() for row in group)

    assert client.put(settings, json={"revision": 1, "default_engines": ["so"]}).status_code == 200
    second = client.post("/api/search", json={"q": "!g 示例搜索"}).json()
    assert not second["meta"]["cached"] and second["meta"]["engines"] == ["360search"]
    assert engine_setup[-1]["engines"] == "360search"
    assert client.post("/api/search", json={"q": "!g 示例搜索"}).json()["meta"]["cached"]

    assert client.put(settings, json={"revision": 2, "default_engines": []}).status_code == 200
    count = len(engine_setup)
    blocked = client.post("/api/search", json={"q": "示例搜索"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "SEARCH_ENGINES_DISABLED"
    assert len(engine_setup) == count
    explicit = client.post("/api/search", json={"q": "示例搜索 !b"})
    assert explicit.status_code == 200 and explicit.json()["parsed"]["engine"] == "bing"
    assert engine_setup[-1]["engines"] == "bing"


def test_custom_engine_region_and_website_routes(client, engine_setup):
    settings = "/api/settings/engines"
    custom = [
        entry("video2", "engine", "bilibili"),
        entry("fr2", "region", "fr-FR"),
        entry("portal", "website", "https://example.test/find?q={q}"),
    ]
    assert client.put(settings, json={"custom": custom, "default_engines": ["video2"]}).status_code == 200
    assert client.put(settings, json={"custom": custom}).status_code == 409
    for query in ("示例搜索", "示例搜索 video2", "示例搜索 !VIDEO2", "示例搜索 fr2"):
        result = client.post("/api/search", json={"q": query})
        assert result.status_code == 200
        assert result.json()["meta"]["engines"] == ["bilibili"]
    assert engine_setup[-1]["language"] == "fr-FR"
    count = len(engine_setup)
    external = client.post("/api/search", json={"q": "机器 学习 + C++ portal"}).json()
    assert external["parsed"]["open_url"] == "https://example.test/find?q=%E6%9C%BA%E5%99%A8+%E5%AD%A6%E4%B9%A0+%2B+C%2B%2B"
    assert client.post("/api/ai-search", json={"q": "机器学习 portal"}).json()["results"] == []
    assert len(engine_setup) == count
    ordinary = client.post("/api/search", json={"q": "机器学习 portal", "opts": {"literal": True}}).json()
    assert ordinary["parsed"]["q"] == "机器学习 portal" and "open_url" not in ordinary["parsed"]
    assert {row["code"] for row in client.get("/api/engines").json()["engines"] if row["section"] == "custom"} == {
        "portal", "fr2", "video2",
    }


def test_missing_selection_does_not_trigger_upstream_defaults(client, engine_setup):
    settings = "/api/settings/engines"
    unknown = [entry("site7", "engine", "absent")]
    assert client.put(settings, json={"custom": unknown, "default_engines": ["site7"]}).status_code == 200
    assert client.post("/api/search", json={"q": "示例搜索"}).status_code == 503
    assert engine_setup == []
    assert client.put(settings, json={"revision": 1, "custom": unknown, "default_engines": ["site7", "b"]}).status_code == 200
    result = client.post("/api/search", json={"q": "示例搜索"}).json()
    assert result["meta"]["unresponsive"] == ["absent(上游未加载)"]
    assert engine_setup[-1]["engines"] == "bing"


@pytest.mark.parametrize(("code", "target"), [
    ("b", "https://example.test/?q={q}"),
    ("ds", "https://example.test/?q={q}"),
    ("portal", "javascript:{q}"),
    ("portal", "https://{q}.example.test/"),
    ("portal", "https://example.test/#{q}"),
])
def test_rejects_reserved_suffixes_and_unsafe_website_templates(client, engine_setup, code, target):
    result = client.put("/api/settings/engines", json={"custom": [entry(code, "website", target)]})
    assert result.status_code == 422
    assert client.get("/api/settings/engines").json()["preferences"]["revision"] == 0
