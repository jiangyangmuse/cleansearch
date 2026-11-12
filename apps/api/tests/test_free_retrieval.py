"""免费检索：计费边界、官网直达来源、品牌声明及真实词元命中。"""
from dataclasses import replace

import httpx
import pytest

from app.config import get_settings
from app.core.aggregator import Aggregator, get_aggregator
from app.core.paid import PaidSearch
from app.core.searxng import SearxngClient
from app.core.scoring import RELATED_THRESHOLD, score_results, tokenize, spam_score
from app.core.normalize import normalise_result
from app.core.session_store import get_session_store
from app.db.cache import Cache, get_cache
from app.main import app
import app.routers.search as search_router


@pytest.mark.parametrize("results,unresponsive", [
    ([], []), ([{"url": "https://example.org/", "title": "ok", "engine": "bing"}], []),
    ([{"url": "https://example.org/", "title": "ok", "engine": "bing"}], [["yahoo", "timeout"]]),
])
async def test_successful_free_default_never_spends(results, unresponsive):
    settings = replace(get_settings(), provider="searxng", serper_api_key="test", brave_api_key="")
    aggregator = Aggregator(settings)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"results": results, "unresponsive_engines": unresponsive})))
    calls = []
    def paid(request):
        calls.append(request)
        return httpx.Response(200, json={"organic": []})
    aggregator._paid = PaidSearch(settings, transport=httpx.MockTransport(paid))
    outcome = await aggregator.search("test")
    assert calls == []
    assert len(outcome.results) == len(results)


def seed(monkeypatch, rows):
    monkeypatch.setattr(get_aggregator()._fixture, "_hit", {"results": rows})


def all_results(body):
    return [item for group in body["groups"].values() for item in group]


def test_bing_missing_home_has_distinct_directory_and_search_entries(client, monkeypatch):
    seed(monkeypatch, [
        {"url": "https://www.deepseek.com/en/platform/", "title": "DeepSeek API Platform", "engine": "bing"},
        {"url": "https://download.deepseek.com/", "title": "DeepSeek App", "engine": "bing"},
        {"url": "https://github.com/deepseek-ai", "title": "DeepSeek", "engine": "bing"},
    ])
    body = client.post("/api/search", json={"q": "deepseek !b"}).json()
    entries = body["official"]["entries"]
    home = next(x for x in entries if x["role"] == "home")
    assert home["url"] == "https://www.deepseek.com/" and home["origin"] == "directory"
    assert home["engine"] == [] and home["snippet"] == ""
    assert any(x["role"] == "console" and x["origin"] == "search" for x in entries)
    assert any(x["role"] == "download" and x["origin"] == "search" for x in entries)
    assert body["meta"]["directory"] == sum(x["origin"] == "directory" for x in entries)
    snapshot = get_session_store().get(body["meta"]["sid"])
    assert snapshot and all(x.result_id not in {x["id"] for x in entries if x["origin"] == "directory"} for x in snapshot.sources)


@pytest.mark.parametrize("query,page", [("unknown brand", 1), ("deepseek 教程", 1), ("deepseek", 2)])
def test_directory_does_not_spread_to_content_unknown_or_later_page(client, monkeypatch, query, page):
    seed(monkeypatch, [{"url": "https://example.org/", "title": "example"}])
    body = client.post("/api/search", json={"q": query, "page": page}).json()
    assert not [x for x in (body.get("official") or {}).get("entries", []) if x["origin"] == "directory"]


def test_unverified_home_claim_is_warned_and_not_used_by_summary(client, monkeypatch):
    seed(monkeypatch, [{"url": "https://deepseek-unverified.example/", "title": "DeepSeek 官网", "content": "DeepSeek 官方网站"}])
    body = client.post("/api/search", json={"q": "deepseek 官网"}).json()
    item = all_results(body)[0]
    assert item["brand_warning"] and item["score"] < RELATED_THRESHOLD
    assert item in body["groups"]["weak"]
    assert item["risk"] == 0  # 身份未核验不等于已确认恶意
    assert get_session_store().get(body["meta"]["sid"]) is None
    assert body["meta"]["directory"] > 0


def test_reference_article_is_not_accused_and_real_host_path_is_not_warned(client, monkeypatch):
    seed(monkeypatch, [
        {"url": "https://example.org/news/deepseek", "title": "DeepSeek 官网识别指南"},
        {"url": "https://www.deepseek.com/harness/", "title": "DeepSeek 官网产品"},
    ])
    body = client.post("/api/search", json={"q": "deepseek"}).json()
    assert all(not x.get("brand_warning") for x in all_results(body))


def test_compound_name_matches_brand_without_substring_false_positives():
    assert "deepseek" in tokenize("deepseek-ai/DeepSeek-V4-Pro-0813")
    good = normalise_result({"url": "https://huggingface.co/deepseek-ai/model", "title": "deepseek-ai/DeepSeek-V4-Pro-0813", "engine": "bing"}, 1)
    other = normalise_result({"url": "https://example.org/", "title": "Deepseekish unrelated", "engine": "bing"}, 2)
    score_results("deepseek", [good, other])
    assert good.score >= RELATED_THRESHOLD and other.score < RELATED_THRESHOLD


def test_directory_obeys_existing_blocklist(client, monkeypatch):
    import app.routers.search as router
    from app.core.safety import SafetyReport
    safety = router.get_safety()
    evaluate = safety.evaluate
    monkeypatch.setattr(safety, "evaluate", lambda url: SafetyReport(True, 1., ("blocked",)) if url == "https://www.deepseek.com/" else evaluate(url))
    seed(monkeypatch, [{"url": "https://example.org/", "title": "DeepSeek"}])
    body = client.post("/api/search", json={"q": "deepseek"}).json()
    assert all(x["url"] != "https://www.deepseek.com/" for x in body["official"]["entries"])


def test_legitimate_brand_title_is_not_keyword_stuffing():
    normal = normalise_result({"url": "https://example.org/a", "title": "DeepSeek AI API Platform", "content": "A normal documentation excerpt long enough to read."}, 1)
    stuffed = normalise_result({"url": "https://example.org/b", "title": "DeepSeek DeepSeek DeepSeek DeepSeek", "content": "A normal documentation excerpt long enough to read."}, 2)
    assert spam_score(normal, "deepseek") == 0
    assert spam_score(stuffed, "deepseek") > spam_score(normal, "deepseek")


def test_brand_lookalike_home_is_demoted_without_accusing_third_party_hosts(client, monkeypatch):
    seed(monkeypatch, [
        {"url": "https://deepseek-unverified.example/", "title": "DeepSeek | Answers and AI", "engine": "bing"},
        {"url": "https://openrouter.ai/deepseek/model", "title": "DeepSeek API", "engine": "bing"},
    ])
    body = client.post("/api/search", json={"q": "deepseek"}).json()
    rows = {item["url"]: item for item in all_results(body)}
    assert rows["https://deepseek-unverified.example/"]["brand_warning"]
    assert rows["https://deepseek-unverified.example/"]["score"] < RELATED_THRESHOLD
    assert not rows["https://openrouter.ai/deepseek/model"]["brand_warning"]


def test_warm_cache_preserves_origin_and_excludes_claims_from_sources(client, monkeypatch, tmp_path):
    cache = Cache(tmp_path / "cache.db", ttl=60)
    monkeypatch.setattr(search_router, "get_settings", lambda: replace(get_settings(), cache_enabled=True))
    monkeypatch.setitem(app.dependency_overrides, get_cache, lambda: cache)
    seed(monkeypatch, [
        {"url": "https://www.deepseek.com/en/platform/", "title": "DeepSeek API Platform", "engine": "bing"},
        {"url": "https://unverified.example/", "title": "DeepSeek 官网", "engine": "bing"},
    ])
    try:
        cold = client.post("/api/search", json={"q": "deepseek !b"}).json()
        warm = client.post("/api/search", json={"q": "deepseek !b"}).json()
        assert not cold["meta"]["cached"] and warm["meta"]["cached"]
        assert cold["official"] == warm["official"]
        assert any(x["brand_warning"] for x in warm["groups"]["weak"])
        for body in (cold, warm):
            sources = get_session_store().get(body["meta"]["sid"]).sources
            assert [x.url for x in sources] == ["https://www.deepseek.com/en/platform/"]
    finally:
        cache.close()
