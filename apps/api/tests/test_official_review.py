"""官方入口复核：身份边界、查询意图、缓存和引用闭环。"""

from dataclasses import asdict, replace
import json

import pytest

from app.config import get_settings
from app.core.aggregator import get_aggregator
from app.core.normalize import normalise_result
from app.core.official import BRANDS, brand_for_query, collect_official
from app.core.session_store import get_session_store
from app.db.cache import Cache, get_cache
from app.main import app
import app.routers.search as search_router


@pytest.mark.parametrize("query", [
    "deepseek API 怎么用", "deepseek how to use", "deepseek benchmark",
    "deepseek openai", "苹果派", "微信小程序开发", "python list comprehension",
])
def test_content_and_ambiguous_queries_are_not_navigation(query):
    assert brand_for_query(query) is None


@pytest.mark.parametrize("query,key", [
    ("deepseek documentation", "deepseek"), ("deepseek API 文档", "deepseek"),
    ("微信官网", "wechat"), ("ＤｅｅｐＳｅｅｋ 登录", "deepseek"),
])
def test_explicit_navigation_still_matches(query, key):
    assert brand_for_query(query).key == key


@pytest.mark.parametrize("url", [
    "https://github.com/python/../other-org", "https://github.com/python/%2e%2e/other-org",
    "https://github.com/python/%252e%252e/other-org", "https://github.com/python/%2f../other-org",
    "https://github.com:8443/python", "http://github.com/python",
])
def test_ambiguous_or_unverified_origin_is_not_official(url):
    result = normalise_result({"url": url, "title": "Python"}, 1)
    assert result is not None
    brand = next(b for b in BRANDS if b.key == "python")
    section, used = collect_official(brand, [result])
    assert section is None and not used


@pytest.fixture()
def cache_client(client, tmp_path, monkeypatch):
    cache = Cache(tmp_path / "review.db", ttl=60)
    monkeypatch.setattr(search_router, "get_settings", lambda: replace(get_settings(), cache_enabled=True))
    app.dependency_overrides[get_cache] = lambda: cache
    yield client
    app.dependency_overrides.pop(get_cache, None)
    cache.close()


def seed(monkeypatch, results):
    monkeypatch.setattr(get_aggregator()._fixture, "_hit", {"results": results})


def test_official_sources_remain_identical_and_citable_on_cache(cache_client, monkeypatch):
    seed(monkeypatch, [
        {"url": f"https://example.org/{i}", "title": f"DeepSeek {i}", "content": "普通搜索摘要",
         "engines": ["google", "bing", "yahoo"]}
        for i in range(12)
    ] + [{"url": "https://www.deepseek.com/", "title": "DeepSeek", "content": "官网原始摘要"}])
    cold = cache_client.post("/api/search", json={"q": "deepseek"}).json()
    warm = cache_client.post("/api/search", json={"q": "deepseek"}).json()
    assert warm["meta"]["cached"]
    cold_sources = get_session_store().get(cold["meta"]["sid"]).sources
    warm_sources = get_session_store().get(warm["meta"]["sid"]).sources
    assert [asdict(s) for s in cold_sources] == [asdict(s) for s in warm_sources]
    entry = warm["official"]["entries"][0]
    assert entry["id"] == warm_sources[0].result_id
    assert entry["snippet"] == warm_sources[0].snippet == "官网原始摘要"
    for body in (cold, warm):
        response = cache_client.get("/api/summarize", params={"sid": body["meta"]["sid"]})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        cites = [event for event in events if "result_id" in event]
        assert cites[0]["url"] == entry["url"]
        assert cites[0]["result_id"] == entry["id"]


def test_official_candidate_survives_title_similarity(client, monkeypatch):
    title = "Vercel documentation getting started deployment reference"
    seed(monkeypatch, [
        {"url": "https://example.org/tutorial", "title": title},
        {"url": "https://vercel.com/docs", "title": title},
    ])
    body = client.post("/api/search", json={"q": "vercel docs"}).json()
    assert any(entry["url"] == "https://vercel.com/docs" and entry["origin"] == "search" for entry in body["official"]["entries"])


def test_official_retains_risk_confirmation(cache_client, monkeypatch):
    from app.core.safety import SafetyReport
    safety = search_router.get_safety()
    monkeypatch.setattr(safety, "evaluate", lambda url: SafetyReport(False, .4, ("测试风险",)))
    seed(monkeypatch, [{"url": "https://www.deepseek.com/", "title": "DeepSeek"}])
    for _ in range(2):
        body = cache_client.post("/api/search", json={"q": "deepseek"}).json()
        entry = body["official"]["entries"][0]
        assert entry["risk"] == .4
        assert entry["go_url"].startswith("/go?u=")


def test_catalog_change_invalidates_cached_identity(cache_client, monkeypatch):
    import app.core.official as catalog
    seed(monkeypatch, [{"url": "https://www.deepseek.com/", "title": "DeepSeek"}])
    first = cache_client.post("/api/search", json={"q": "deepseek"}).json()
    assert first["official"]
    monkeypatch.setattr(catalog, "BRANDS", tuple(b for b in catalog.BRANDS if b.key != "deepseek"))
    second = cache_client.post("/api/search", json={"q": "deepseek"}).json()
    assert not second["meta"]["cached"] and second["official"] is None


@pytest.mark.parametrize("url,status,expected", [
    ("https://example.org/", 403, "fail"), ("https://example.org/", 429, "fail"),
    ("http://github.com/", 200, "fail"), ("https://github.com:8443/", 200, "fail"),
    ("https://github.com/", 302, "fail"), ("https://github.com/", 200, "ok"),
    ("https://github.com/", 403, "blocked"), ("https://github.com/", 0, "blocked"),
])
def test_verifier_does_not_hide_redirect_mismatch(url, status, expected):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("official_verifier", Path(__file__).resolve().parents[3] / "scripts/verify-official.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.classify({"final_url": url, "status": status}, {"github.com"})[0] == expected
