"""M1 打分与三档分组：特征映射、绝对阈值、容量上限。"""

from __future__ import annotations

from app.core.scoring import (
    RELATED_THRESHOLD,
    STRONG_THRESHOLD,
    authority_score,
    bm25_scores,
    consensus_score,
    coverage,
    group_results,
    has_time_intent,
    score_results,
    spam_score,
    tokenize,
)
from app.schemas import Result


def make_result(url: str, title: str, snippet: str = "", engines: list[str] | None = None,
                published: str | None = None, score: float = 0.5) -> Result:
    return Result(
        id="r_1",
        url=url,
        display_url=url,
        title=title,
        snippet=snippet,
        engine=engines or ["google"],
        score=score,
        published=published,
        reasons=[],
    )


def test_tokenizer_splits_cjk_bigrams_and_latin_words() -> None:
    tokens = tokenize("Python 异步编程 asyncio")
    assert "python" in tokens and "asyncio" in tokens
    assert "异步" in tokens and "步编" in tokens


def test_coverage_counts_query_terms() -> None:
    query = tokenize("python 文档")
    full = tokenize("Python 官方文档")
    half = tokenize("Python 教程")
    assert coverage(query, full) == 1.0
    assert coverage(query, half) == 0.5


def test_bm25_ranks_matching_document_first() -> None:
    query = tokenize("asyncio")
    docs = [tokenize("asyncio 异步库"), tokenize("前端构建工具")]
    scores = bm25_scores(query, docs)
    assert scores[0] > scores[1] == 0.0


def test_consensus_is_stepwise() -> None:
    assert consensus_score(0) == 0.0
    assert consensus_score(1) < consensus_score(2) < consensus_score(3)
    assert consensus_score(5) == 1.0


def test_authority_tiers() -> None:
    assert authority_score("docs.python.org") == 1.0
    assert authority_score("www.gov.cn") == 1.0
    assert authority_score("docs.some-random-project.io") == 0.9
    assert authority_score("random-shop.top") == 0.0


def test_spam_flags_marketing_text_without_intent() -> None:
    result = make_result(
        "https://spam.example/a",
        "代理加盟 一手货源",
        "加微信 咨询，限时优惠，免费领取课程",
    )
    assert spam_score(result, "数据分析") >= 0.6
    # 查询本身带商业意图时不惩罚
    assert spam_score(result, "代理 价格") < 0.6


def test_time_intent_detection() -> None:
    assert has_time_intent("2026 年 前端 趋势")
    assert has_time_intent("latest react release")
    assert not has_time_intent("python asyncio")


def test_score_rewards_authority_and_consensus() -> None:
    strong = make_result(
        "https://docs.python.org/3/library/asyncio.html",
        "asyncio 异步编程",
        "asyncio 是异步并发库，提供事件循环与任务调度。",
        engines=["google", "brave"],
    )
    weak = make_result(
        "https://unknown-shop.example/x",
        "随便写写的页面",
        "一些与查询无关的内容。",
        engines=["google"],
    )
    score_results("asyncio", [strong])
    score_results("asyncio", [weak])
    assert strong.score > weak.score
    assert strong.score >= STRONG_THRESHOLD
    assert weak.score < RELATED_THRESHOLD


def test_low_quality_set_yields_empty_strong_group() -> None:
    """全弱结果：公式不允许把垃圾集拉出强相关。"""
    junk = [
        make_result(f"https://junk{i}.example/x", "无关页面 " + str(i), "内容与查询无关", engines=["google"])
        for i in range(5)
    ]
    score_results("量子力学 教程", junk)
    assert all(r.score < RELATED_THRESHOLD for r in junk)
    strong, related, weak = group_results(junk)
    assert strong == [] and related == []
    assert len(weak) == 5


def test_group_caps_and_order() -> None:
    results = [
        make_result(f"https://ex{i}.example/a", f"标题 {i}", "内容", engines=["google", "bing"])
        for i in range(30)
    ]
    for index, item in enumerate(results):
        item.score = 0.9 - index * 0.001
    strong, related, weak = group_results(results)
    assert len(strong) == 10
    assert [r.score for r in strong] == sorted([r.score for r in strong], reverse=True)
    assert related == [] and weak == []


def test_group_thresholds_are_absolute() -> None:
    above = make_result("https://a.example/x", "a", "b")
    above.score = STRONG_THRESHOLD
    at_related = make_result("https://b.example/x", "b", "c")
    at_related.score = RELATED_THRESHOLD
    below = make_result("https://c.example/x", "c", "d")
    below.score = RELATED_THRESHOLD - 0.01
    strong, related, weak = group_results([above, at_related, below])
    assert [r.id for r in strong] == ["r_1"]
    assert at_related in related and below in weak
