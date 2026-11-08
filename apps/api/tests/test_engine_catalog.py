"""引擎目录与后缀表的契约测试。"""

from __future__ import annotations

from app.core.engine_catalog import (
    ENGINE_SPECS,
    ENGINE_SUFFIXES,
    catalog_rows,
    engine_candidates,
    paid_route,
    searx_engine_name,
)
from app.core.query_parser import parse_query


def test_suffix_table_includes_the_repaired_engines() -> None:
    assert ENGINE_SUFFIXES["g"] == "google"
    assert ENGINE_SUFFIXES["b"] == "bing"
    assert ENGINE_SUFFIXES["ddg"] == "duckduckgo"
    assert ENGINE_SUFFIXES["sc"] == "scholar"
    assert ENGINE_SUFFIXES["n"] == "naver"
    assert ENGINE_SUFFIXES["yd"] == "yandex"
    assert ENGINE_SUFFIXES["sw"] == "swisscows"


def test_parse_query_uses_catalog_codes() -> None:
    assert parse_query("python 文档 g").engine == "google"
    assert parse_query("python 文档 b").engine == "bing"
    assert parse_query("python 文档 n").engine == "naver"
    assert parse_query("python 文档 yd").engine == "yandex"
    assert parse_query("python 文档 sw").engine == "swisscows"


def test_candidate_chain_is_deduplicated_and_ordered() -> None:
    assert engine_candidates("google") == ["google", "google cse"]
    assert engine_candidates("sogou") == ["sogou", "360search"]
    assert engine_candidates("bing") == ["bing"]
    assert engine_candidates("default") == ["default"]


def test_scholar_maps_to_searxng_name() -> None:
    assert searx_engine_name("scholar") == "google scholar"
    assert searx_engine_name("google cse") == "google cse"


def test_paid_routes_are_declared_only_where_supported() -> None:
    assert paid_route("google") == "search"
    assert paid_route("google cse") == "search"
    assert paid_route("scholar") == "scholar"
    assert paid_route("brave") == "brave"
    assert paid_route("bing") == ""


def test_catalog_rows_are_consistent() -> None:
    rows = catalog_rows()
    codes = [row["code"] for row in rows]
    assert len(codes) == len(set(codes))
    engines = {row["engine"] for row in rows}
    for row in rows:
        for fallback in row["fallbacks"]:
            assert fallback in engines
    assert {"g", "b", "w", "sc", "n", "yd", "sw"} <= set(codes)
    assert all(spec.code in ENGINE_SUFFIXES for spec in ENGINE_SPECS)
