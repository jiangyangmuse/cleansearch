"""M0 验收：三种状态可区分、结果稳定、去重生效、契约字段齐全。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.aggregator import get_aggregator


def _search(client: TestClient, **body):
    return client.post("/api/search", json=body)


def flatten(body: dict) -> list[dict]:
    """M1 起结果分三档，按强相关 → 相关 → 弱相关展开。"""
    groups = body["groups"]
    return groups["strong"] + groups["related"] + groups["weak"]


def test_hit_returns_stable_ten_results(client: TestClient) -> None:
    first = _search(client, q="python 文档")
    second = _search(client, q="python 文档")
    assert first.status_code == 200, first.text
    body = first.json()

    assert body["meta"]["status"] == "ok"
    assert body["meta"]["upstream_total"] == 11
    assert len(flatten(body)) == body["meta"]["total"] == 10
    assert body["parsed"]["q"] == "python 文档"
    assert body["parsed"]["router"] == "default"

    # 固定样本：URL 集合与总数在两次请求间完全一致
    assert sorted(r["url"] for r in flatten(body)) == sorted(
        r["url"] for r in flatten(second.json())
    )
    assert [r["score"] for r in flatten(body)] == [r["score"] for r in flatten(second.json())]


def test_result_contract_fields(client: TestClient) -> None:
    body = _search(client, q="test").json()
    result = flatten(body)[0]
    for key in ("id", "url", "display_url", "title", "snippet", "engine", "score", "risk"):
        assert key in result
    assert result["display_url"].startswith("docs.python.org")
    assert result["favicon"] == "https://docs.python.org/favicon.ico"
    assert body["meta"]["provider"] == "fixture"
    assert body["meta"]["sid"].startswith("s_")


def test_dedupe_removes_tracking_variant(client: TestClient) -> None:
    body = _search(client, q="test").json()
    urls = [r["url"] for r in flatten(body)]
    assert not any("utm_source" in u for u in urls)
    assert body["meta"]["filtered"]["dup"] == 1
    mdn = [r for r in flatten(body) if "developer.mozilla.org" in r["url"]]
    assert len(mdn) == 1
    # 合并后的引擎列表包含被去重那条的来源
    assert sorted(mdn[0]["engine"]) == ["brave", "duckduckgo"]


def test_grouping_keeps_ids_unique(client: TestClient) -> None:
    body = _search(client, q="python 文档").json()
    results = flatten(body)
    assert results, "固定样本应至少有一条结果"
    ids = [r["id"] for r in results]
    assert len(ids) == len(set(ids))
    assert body["meta"]["total"] == len(results)
    # 强相关按分数降序；弱相关一定低于相关阈值
    assert [r["score"] for r in body["groups"]["strong"]] == sorted(
        [r["score"] for r in body["groups"]["strong"]], reverse=True
    )
    assert all(r["score"] < 0.30 for r in body["groups"]["weak"])


def test_zero_results_state(client: TestClient) -> None:
    body = _search(client, q="test", opts={"fixture": "empty"}).json()
    assert body["meta"]["status"] == "empty"
    assert body["meta"]["total"] == 0
    assert body["meta"]["upstream_total"] == 0
    assert body["groups"] == {"strong": [], "related": [], "weak": []}


def test_zero_results_by_query_prefix(client: TestClient) -> None:
    body = _search(client, q="__empty 一个不会命中的词").json()
    assert body["meta"]["status"] == "empty"


def test_upstream_unavailable_state(client: TestClient) -> None:
    response = _search(client, q="__fail 上游挂了")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "UPSTREAM_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["message"]


def test_upstream_unavailable_by_opt(client: TestClient) -> None:
    response = _search(client, q="test", opts={"fixture": "error"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_page_two_is_empty(client: TestClient) -> None:
    body = _search(client, q="test", page=2).json()
    assert body["meta"]["status"] == "empty"
    assert body["meta"]["total"] == 0


def test_blank_query_rejected(client: TestClient) -> None:
    assert client.post("/api/search", json={"q": "   "}).status_code == 422
    assert client.post("/api/search", json={}).status_code == 422


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["provider"] == "fixture"
    assert body["web_built"] is True


def test_same_origin_spa(client: TestClient) -> None:
    assert "spa-index" in client.get("/").text
    assert "spa-index" in client.get("/r").text  # 前端路由刷新不 404
    assert client.get("/assets/app.js").status_code == 200
    missing = client.get("/api/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_normalize_helpers() -> None:
    from app.core.normalize import canonical_url, dedupe_results
    from app.schemas import Result

    assert canonical_url("HTTPS://Example.COM/a/?utm_source=x&b=2&a=1#frag") == (
        "https://example.com/a?a=1&b=2"
    )
    dup = [
        Result(id="r_1", url="https://a.com/x", display_url="a.com › x", title="A"),
        Result(id="r_2", url="https://a.com/x?utm_medium=social", display_url="a.com › x", title="A2"),
    ]
    kept, removed = dedupe_results(dup)
    assert removed == 1 and len(kept) == 1 and kept[0].id == "r_1"


def test_unresponsive_formatting() -> None:
    from app.core.normalize import format_unresponsive

    assert format_unresponsive([["google", "timeout"], "bing"]) == ["google(timeout)", "bing"]
    assert format_unresponsive(None) == []


def test_distinct_titles_without_fingerprint_are_kept() -> None:
    from app.core.normalize import dedupe_similar_titles, normalise_result

    first = normalise_result({"title": "ひらがな", "url": "https://example.jp/a"}, 1)
    second = normalise_result({"title": "カタカナ", "url": "https://example.jp/b"}, 2)
    assert first is not None and second is not None

    kept, removed = dedupe_similar_titles([first, second])

    assert kept == [first, second] and removed == 0


def test_fixture_matches_searxng_shape() -> None:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "searxng_hit.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload["results"], list)
    assert all({"url", "title", "content", "engine"} <= set(item) for item in payload["results"])


def test_suffix_route_is_applied_end_to_end(client: TestClient) -> None:
    body = _search(client, q="python 文档 g").json()
    assert body["parsed"] == {
        "q": "python 文档",
        "engine": "google",
        "region": None,
        "router": "suffix",
        "expanded": [],
    }
    assert body["meta"]["status"] == "ok"

    bang = _search(client, q="python !b").json()
    assert bang["parsed"]["engine"] == "bing" and bang["parsed"]["router"] == "bang"

    guarded = _search(client, q="C g").json()
    assert guarded["parsed"] == {
        "q": "C g",
        "engine": "default",
        "region": None,
        "router": "default",
        "expanded": [],
    }


def test_region_suffix_sets_region(client: TestClient) -> None:
    body = _search(client, q="天气预报 zh", region="jp").json()
    assert body["parsed"]["region"] == "cn"
    assert body["parsed"]["q"] == "天气预报"


def test_request_region_preserved_when_using_engine_suffix(client: TestClient) -> None:
    body = _search(client, q="python g", region="jp").json()
    assert body["parsed"] == {
        "q": "python",
        "engine": "google",
        "region": "jp",
        "router": "suffix",
        "expanded": [],
    }


def test_blacklist_filters_each_candidate_before_title_merge(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    title = "Python 官方参考手册"
    safe_url = "https://docs.python.org/3/"
    monkeypatch.setattr(get_aggregator()._fixture, "_risky", {"results": [
        {"url": "https://evil-phish.test/doc", "title": title, "engine": "brave"},
        {"url": safe_url, "title": title, "engine": "google"},
        {"url": "https://malware-top.xyz/doc", "title": title, "engine": "bing"},
    ]})

    body = _search(client, q="Python 官方参考手册", opts={"fixture": "risky"}).json()

    assert [(r["url"], r["engine"]) for r in flatten(body)] == [(safe_url, ["google"])]
    assert body["meta"]["filtered"] == {"dup": 0, "risk": 2}
    assert body["meta"]["upstream_total"] == 3


def test_blocklist_drops_known_malicious_result(client: TestClient) -> None:
    body = _search(client, q="账号验证", opts={"fixture": "risky"}).json()
    urls = [r["url"] for r in flatten(body)]
    assert body["meta"]["upstream_total"] == 5
    assert body["meta"]["filtered"]["risk"] == 1
    assert not any("evil-phish.test" in url for url in urls)
    assert all("tracker.example.test" not in url for url in urls)


def test_suspicious_url_survives_with_risk_score(client: TestClient) -> None:
    body = _search(client, q="账号验证", opts={"fixture": "risky"}).json()
    suspicious = [r for r in flatten(body) if "xn--" in r["url"]]
    assert len(suspicious) == 1
    assert suspicious[0]["risk"] >= 0.35
    assert any("风险分" in reason for reason in suspicious[0]["reasons"])


def test_risky_fixture_prefix(client: TestClient) -> None:
    body = _search(client, q="__risky 账号验证").json()
    assert body["meta"]["filtered"]["risk"] == 1


def test_health_reports_blocklist_rules(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["blocklist_rules"] == 3


def test_display_count_never_exceeds_upstream(client: TestClient) -> None:
    body = _search(client, q="test").json()
    assert body["meta"]["total"] <= body["meta"]["upstream_total"]
    assert body["meta"]["total"] == len(flatten(body))
