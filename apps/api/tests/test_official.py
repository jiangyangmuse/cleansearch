"""官方入口表：精确主机/路径、未知品牌、伪装域名与缓存契约。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import get_settings
from app.core.aggregator import get_aggregator
from app.core.normalize import normalise_result
from app.core.official import (
    BRANDS,
    LATIN_TOKEN,
    ROLE_ORDER,
    brand_for_query,
    collect_official,
    path_matches,
    table_snapshot,
)
from app.db.cache import Cache, get_cache
from app.main import app
import app.routers.search as search_router


def build(url: str, title: str = "示例页面", engine: str = "google"):
    item = normalise_result(
        {"url": url, "title": title, "engine": engine, "content": "这是用于入口匹配的摘要文本"}, 1
    )
    assert item is not None
    return item


def brand(key: str):
    return next(entry for entry in BRANDS if entry.key == key)


def hit(monkeypatch, results: list[dict]) -> None:
    monkeypatch.setattr(get_aggregator()._fixture, "_hit", {"results": results})


def groups_of(body: dict) -> list[dict]:
    return [item for group in body["groups"].values() for item in group]


def test_table_entries_are_exact_and_unique() -> None:
    rows = table_snapshot()
    assert len(rows) >= 80
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        assert row["host"] == row["host"].lower().strip(".")
        assert "." in row["host"] and "*" not in row["host"]
        assert row["path"].startswith("/")
        assert row["role"] in ROLE_ORDER
        assert row["source"].startswith("https://")
        assert row["verified"].count("-") == 2
        key = (row["brand"], row["host"], row["path"], row["role"])
        assert key not in seen
        seen.add(key)
    for entry in BRANDS:
        assert entry.aliases, entry.key
        for alias in entry.aliases:
            assert alias == alias.strip().lower()
            assert len(alias) >= (3 if LATIN_TOKEN.fullmatch(alias) else 2)
    assert len({entry.key for entry in BRANDS}) == len(BRANDS)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("deepseek", "deepseek"),
        ("DeepSeek 官网", "deepseek"),
        ("深度求索", "deepseek"),
        ("chatgpt", "openai"),
        ("Claude", "anthropic"),
        ("微信 官网", "wechat"),
        ("github 文档", "github"),
    ],
)
def test_brand_alias_matching(query: str, expected: str) -> None:
    matched = brand_for_query(query)
    assert matched is not None and matched.key == expected


@pytest.mark.parametrize(
    "query",
    ["deepseek 教程", "deepseek tutorial", "rust 新闻", "openai 招聘", "unknown brand", "", "   "],
)
def test_research_intent_and_unknown_brand_stay_normal(query: str) -> None:
    assert brand_for_query(query) is None


@pytest.mark.parametrize(
    ("spec", "actual", "expected"),
    [
        ("/", "/", True),
        ("/", "/en/", True),
        ("/", "/zh-CN/", True),
        ("/", "/news", False),
        ("/", "/en/docs", False),
        ("/docs", "/docs", True),
        ("/docs", "/docs/", True),
        ("/docs", "/docs/intro", True),
        ("/docs", "/docsomething", False),
        ("/docs", "/en/docs", False),
    ],
)
def test_path_semantics(spec: str, actual: str, expected: bool) -> None:
    assert path_matches(spec, actual) is expected


def test_exact_host_only_and_one_entry_per_role() -> None:
    results = [
        build("https://www.deepseek.com/", "DeepSeek"),
        build("https://www.deepseek.com/en/", "DeepSeek"),
        build("https://chat.deepseek.com/", "DeepSeek"),
        build("https://www.deepseek.com.example.org/", "DeepSeek"),
        build("https://deepseek.com/", "DeepSeek"),
        build("https://chat.deepseek.com.login.example.net/", "DeepSeek"),
    ]
    section, used = collect_official(brand("deepseek"), results)
    assert section is not None
    roles = {link.role: link.url for link in section.entries}
    assert roles == {
        "home": "https://www.deepseek.com/",
        "chat": "https://chat.deepseek.com/",
    }
    assert [link.role for link in section.entries] == ["home", "chat"]
    assert len(used) == 2
    assert all("example.org" not in item.url and "example.net" not in item.url for item in used)


def test_shared_host_requires_org_path() -> None:
    section, used = collect_official(
        brand("python"),
        [build("https://github.com/python"), build("https://github.com/other-org")],
    )
    assert section is not None and [link.role for link in section.entries] == ["code"]
    assert section.entries[0].url == "https://github.com/python"
    assert [item.url for item in used] == ["https://github.com/python"]


def test_path_scoped_official_docs() -> None:
    section, _ = collect_official(
        brand("openai"),
        [
            build("https://developers.openai.com/", "OpenAI Developers"),
            build("https://developers.openai.com/api/docs", "API"),
            build("https://platform.openai.com/", "OpenAI Platform"),
        ],
    )
    assert section is not None
    roles = {link.role: link.url for link in section.entries}
    assert roles["docs"] == "https://developers.openai.com/"
    assert roles["console"] == "https://platform.openai.com/"


def test_missing_candidates_are_not_invented() -> None:
    section, used = collect_official(
        brand("deepseek"), [build("https://en.wikipedia.org/wiki/DeepSeek", "DeepSeek")]
    )
    assert section is None and used == []


def test_brand_query_gets_its_own_section(client, monkeypatch) -> None:
    hit(
        monkeypatch,
        [
            {"url": "https://en.wikipedia.org/wiki/DeepSeek", "title": "DeepSeek", "engine": "google"},
            {"url": "https://www.deepseek.com/", "title": "DeepSeek", "engine": "serper"},
            {"url": "https://chat.deepseek.com/", "title": "DeepSeek", "engine": "yahoo"},
            {"url": "https://www.deepseek.com.example.org/", "title": "DeepSeek 官网", "engine": "bing"},
        ],
    )
    body = client.post("/api/search", json={"q": "deepseek"}).json()

    assert body["official"]["key"] == "deepseek"
    entries = [entry for entry in body["official"]["entries"] if entry["origin"] == "search"]
    assert [entry["role"] for entry in entries] == ["home", "chat"]
    assert {entry["host"] for entry in entries} == {"www.deepseek.com", "chat.deepseek.com"}
    assert all(entry["source"].startswith("https://") and entry["verified"] for entry in entries)

    urls = {item["url"] for item in groups_of(body)}
    assert urls == {
        "https://en.wikipedia.org/wiki/DeepSeek",
        "https://www.deepseek.com.example.org/",
    }
    assert body["meta"]["official"] - body["meta"]["directory"] == 2
    assert body["meta"]["total"] == 2
    assert len({item["id"] for item in groups_of(body)}) == 2


def test_tutorial_query_keeps_every_result_in_groups(client, monkeypatch) -> None:
    hit(
        monkeypatch,
        [
            {"url": "https://www.deepseek.com/", "title": "DeepSeek", "engine": "google"},
            {"url": "https://chat.deepseek.com/", "title": "DeepSeek", "engine": "bing"},
        ],
    )
    body = client.post("/api/search", json={"q": "deepseek 教程"}).json()
    assert body["official"] is None
    assert body["meta"]["official"] == 0
    assert {item["url"] for item in groups_of(body)} == {
        "https://www.deepseek.com/",
        "https://chat.deepseek.com/",
    }


def test_unknown_brand_has_no_section(client, monkeypatch) -> None:
    hit(monkeypatch, [{"url": "https://www.example.com/", "title": "Example", "engine": "google"}])
    body = client.post("/api/search", json={"q": "example brand"}).json()
    assert body["official"] is None and body["meta"]["total"] == 1


@pytest.fixture()
def cached_client(client, tmp_path, monkeypatch):
    cache = Cache(tmp_path / "official-cache.db", ttl=60)
    monkeypatch.setattr(
        search_router, "get_settings", lambda: replace(get_settings(), cache_enabled=True)
    )
    app.dependency_overrides[get_cache] = lambda: cache
    yield client
    app.dependency_overrides.pop(get_cache, None)
    cache.close()


def test_official_section_survives_cache(cached_client, monkeypatch) -> None:
    hit(
        monkeypatch,
        [
            {"url": "https://www.deepseek.com/", "title": "DeepSeek", "engine": "serper"},
            {"url": "https://chat.deepseek.com/", "title": "DeepSeek", "engine": "yahoo"},
            {"url": "https://en.wikipedia.org/wiki/DeepSeek", "title": "DeepSeek", "engine": "google"},
        ],
    )
    first = cached_client.post("/api/search", json={"q": "deepseek"}).json()
    second = cached_client.post("/api/search", json={"q": "deepseek"}).json()

    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert second["official"] == first["official"]
    assert second["meta"]["official"] - second["meta"]["directory"] == 2
    assert second["meta"]["total"] == first["meta"]["total"] == 1
