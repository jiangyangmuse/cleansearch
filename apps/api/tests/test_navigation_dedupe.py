"""A shared brand title does not make different destinations the same page."""
from __future__ import annotations

import hashlib
import json

import pytest

from app.core.aggregator import get_aggregator
from app.core.normalize import dedupe_results, dedupe_similar_titles, normalise_result
from app.db.cache import search_key


def result(url, title, engine="google", snippet=""):
    item = normalise_result({"url": url, "title": title, "engine": engine, "content": snippet}, 1)
    assert item is not None
    return item


@pytest.mark.parametrize("reverse", [False, True])
def test_brand_home_chat_and_reference_are_not_title_duplicates(reverse):
    items = [
        result("https://huggingface.co/deepseek-ai", "deepseek-ai (DeepSeek)"),
        result("https://chat.deepseek.com/", "DeepSeek"),
        result("https://www.deepseek.com/", "DeepSeek"),
        result("https://en.wikipedia.org/wiki/DeepSeek", "DeepSeek"),
    ]
    if reverse:
        items.reverse()
    kept, removed = dedupe_similar_titles(items)
    assert removed == 0 and {r.url for r in kept} == {r.url for r in items}


@pytest.mark.parametrize("path", ["/", "/en/", "/zh-CN/", "/index.html"])
def test_landing_page_with_long_shared_title_survives_article(path):
    title = "Acme Analytics Platform Developer Tools and Documentation"
    article = result("https://reference.example/posts/acme", title)
    landing = result("https://acme.example" + path, title)
    kept, removed = dedupe_similar_titles([article, landing])
    assert kept == [article, landing] and removed == 0
    assert article.engine == ["google"]


def test_short_generic_titles_do_not_collapse_different_documents():
    items = [result("https://alpha.example/docs/intro", "Getting started"),
             result("https://beta.example/guide/setup", "Getting started")]
    kept, removed = dedupe_similar_titles(items)
    assert len(kept) == 2 and removed == 0


def test_syndicated_article_title_still_merges_provenance():
    title = "Python asynchronous programming event loop practical examples"
    first = result("https://news.example/articles/python-async", title, "google")
    mirror = result("https://mirror.example/posts/python-async", title, "bing")
    kept, removed = dedupe_similar_titles([first, mirror])
    assert kept == [first] and removed == 1
    assert first.engine == ["google", "bing"]


def test_same_landing_url_tracking_variants_still_deduplicate():
    items = [result("https://www.deepseek.com/", "DeepSeek", "google"),
             result("https://www.deepseek.com/?utm_source=search", "DeepSeek", "serper")]
    kept, removed = dedupe_results(items)
    assert len(kept) == 1 and removed == 1
    assert kept[0].engine == ["google", "serper"]


def test_brand_search_keeps_official_destinations_end_to_end(client, monkeypatch):
    # Reproduce the reported ordering: an earlier reference with the same title
    # used to consume the homepage and chat URLs before ranking could see them.
    monkeypatch.setattr(get_aggregator()._fixture, "_hit", {"results": [
        {"url": "https://en.wikipedia.org/wiki/DeepSeek", "title": "DeepSeek", "engine": "google"},
        {"url": "https://www.deepseek.com/", "title": "DeepSeek", "engine": "serper"},
        {"url": "https://chat.deepseek.com/", "title": "DeepSeek", "engine": "yahoo"},
        {"url": "https://www.deepseek.com/?utm_source=test", "title": "DeepSeek", "engine": "bing"},
    ]})
    body = client.post("/api/search", json={"q": "deepseek"}).json()
    items = [r for group in body["groups"].values() for r in group]
    urls = {item["url"] for item in items}
    assert urls == {"https://en.wikipedia.org/wiki/DeepSeek", "https://www.deepseek.com/", "https://chat.deepseek.com/"}
    assert body["meta"]["filtered"]["dup"] == 1
    home = next(item for item in items if item["url"] == "https://www.deepseek.com/")
    assert set(home["engine"]) == {"serper", "bing"}
    reference = next(item for item in items if "wikipedia.org" in item["url"])
    assert reference["engine"] == ["google"]
    assert len({item["id"] for item in items}) == 3


def test_search_key_does_not_reuse_prior_title_dedupe_policy():
    old_raw = json.dumps(["search-v4", (), "deepseek", "default", None, 1, True, None], ensure_ascii=False, sort_keys=True)
    old_key = hashlib.sha256(old_raw.encode()).hexdigest()[:32]
    assert search_key("deepseek") != old_key
