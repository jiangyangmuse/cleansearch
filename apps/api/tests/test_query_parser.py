"""M1 查询解析：40 条回归集 + 护栏断言。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.query_parser import ENGINE_SUFFIXES, REGION_SUFFIXES, parse_query

CASES_PATH = Path(__file__).resolve().parent / "regression" / "m1_queries.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def test_regression_set_size_is_in_planned_range() -> None:
    assert 30 <= len(CASES) <= 50, f"回归集应有 30–50 条，实际 {len(CASES)}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_regression_case(case: dict) -> None:
    parsed = parse_query(case["raw"])
    expected = case["expect"]
    assert parsed.q == expected["q"], f"{case['raw']!r} 正文解析错误"
    assert parsed.engine == expected["engine"], f"{case['raw']!r} 引擎解析错误"
    assert parsed.region == expected["region"], f"{case['raw']!r} 地区解析错误"
    assert parsed.router == expected["router"], f"{case['raw']!r} 路由类型错误"


def test_single_letter_guard_keeps_plain_query() -> None:
    # C g 是「C 语言 + g」的常见输入，不能被当成 Google 后缀
    for raw in ("C g", "c g", "1 g", "x b"):
        assert parse_query(raw).router == "default"
        assert parse_query(raw).q == raw


def test_quoted_text_is_not_parsed() -> None:
    assert parse_query('"sort g"').router == "default"
    assert parse_query('说明 "a g"').router == "default"


def test_unbalanced_quote_disables_routing() -> None:
    parsed = parse_query('"未闭合 g')
    assert parsed.router == "default" and parsed.engine == "default"


def test_fullwidth_space_and_padding() -> None:
    assert parse_query("数分知识点　g").engine == "google"
    assert parse_query("  数分知识点 g  ").q == "数分知识点"


def test_bang_without_space() -> None:
    parsed = parse_query("test!g")
    assert parsed.q == "test" and parsed.engine == "google" and parsed.router == "bang"


def test_unknown_suffix_is_plain_query() -> None:
    for raw in ("数据 zz", "数据 1a", "数据 g gg"):
        assert parse_query(raw).router == "default"


def test_empty_input() -> None:
    assert parse_query("   ").q == ""
    assert parse_query("").router == "default"


def test_suffix_maps_are_disjoint() -> None:
    assert not (set(ENGINE_SUFFIXES) & set(REGION_SUFFIXES))
