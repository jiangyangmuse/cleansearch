"""查询扩展（词典版）。"""

from __future__ import annotations

from app.core.expand import expand_aliases
from app.core.scoring import score_results
from app.schemas import Result


def make_result(url: str, title: str, snippet: str = "") -> Result:
    return Result(id="r_1", url=url, display_url=url, title=title, snippet=snippet, engine=["google"])


def test_expand_hits_known_aliases() -> None:
    assert "数据分析" in expand_aliases("数分 知识点")
    assert "机器学习" in expand_aliases("ML 入门")
    assert expand_aliases("完全无关的词") == []


def test_alias_lifts_recall_without_overriding() -> None:
    alias_doc = make_result("https://a.test/x", "数据分析入门", "讲数据分析的基本方法。")
    unrelated = make_result("https://b.test/x", "园艺指南", "讲怎么种花。")
    score_results("数分", [alias_doc, unrelated], expand_aliases("数分"))
    assert alias_doc.score > unrelated.score
    assert alias_doc.reasons  # 至少给出可解释的理由

    direct = make_result("https://c.test/x", "数分入门", "数分的基本方法。")
    score_results("数分", [direct], expand_aliases("数分"))
    assert direct.score >= alias_doc.score  # 原词命中不该弱于别名命中


def test_parsed_reports_expansion(client) -> None:
    body = client.post("/api/search", json={"q": "数分 知识点"}).json()
    assert "数据分析" in body["parsed"]["expanded"]
    plain = client.post("/api/search", json={"q": "python 文档"}).json()
    assert plain["parsed"]["expanded"] == []
