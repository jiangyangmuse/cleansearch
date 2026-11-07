"""P2 评估：词典查询扩展对排序与召回的影响。

三种条件对比（同一批标注查询）：
  baseline   —— 原查询，排序不用别名
  ranking    —— 原查询，排序用别名词（只改排序，不改上游召回）
  rewrite    —— 把别名并入查询再发上游（改召回）

指标：期望域名在 Top10 的命中率、进入强相关的命中率、首个命中排名。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.expand import expand_aliases  # noqa: E402
from app.core.scoring import score_results  # noqa: E402
from app.schemas import Result  # noqa: E402

LABELS = Path(__file__).resolve().parents[1] / "apps" / "api" / "tests" / "regression" / "p2_labeled_queries.json"


def search(base: str, q: str) -> dict:
    body = json.dumps({"q": q}).encode()
    req = urllib.request.Request(base + "/api/search", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def to_results(payload: dict) -> list[Result]:
    items = [item for group in payload["groups"].values() for item in group]
    return [Result(**item) for item in items]


def rank(results: list[Result], query: str, aliases: list[str]) -> list[Result]:
    copies = [item.model_copy(deep=True) for item in results]
    score_results(query, copies, aliases)
    return sorted(copies, key=lambda r: r.score, reverse=True)


def domain(url: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def metrics(ranked: list[Result], expected: list[str]) -> dict:
    wanted = set(expected)
    first_rank = math.inf
    hit10 = False
    for index, item in enumerate(ranked[:10], 1):
        if domain(item.url) in wanted:
            hit10 = True
            first_rank = min(first_rank, index)
    strong_hit = any(
        domain(item.url) in wanted for item in ranked if item.score >= 0.55
    )
    return {
        "hit10": hit10,
        "strong": strong_hit,
        "first_rank": None if math.isinf(first_rank) else first_rank,
    }


def summarize(rows: list[dict], key: str, *, expanded_only: bool = True) -> dict:
    selected = [row for row in rows if row["has_expansion"] or not expanded_only]
    # No-alias cases use the unchanged baseline for the rewrite policy.
    values = [row[key] if row.get(key) is not None else row["baseline"] for row in selected]
    ranks = [value["first_rank"] for value in values if value["first_rank"] is not None]
    recorded = [value for value in values if "ok" in value]
    return {
        "cases": len(values),
        "hit10": sum(bool(v["hit10"]) for v in values),
        "strong": sum(bool(v["strong"]) for v in values),
        "mean_first_rank": round(statistics.mean(ranks), 2) if ranks else None,
        "mrr10": round(sum(1 / v["first_rank"] if v["first_rank"] else 0 for v in values) / len(values), 4) if values else None,
        "success": sum(v["ok"] for v in recorded) if len(recorded) == len(values) else None,
        "request_status_unrecorded": len(values) - len(recorded),
    }


def evaluation(rows: list[dict], source: dict) -> dict:
    keys = ("baseline", "ranking", "rewrite")
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "returned-candidate reranking; weak expected-domain labels; exact hostname matching",
        "source": source,
        "rows": rows,
        "summary": {key: summarize(rows, key) for key in keys},
        "all_summary": {key: summarize(rows, key, expanded_only=False) for key in keys},
        "controls_summary": {key: summarize([r for r in rows if not r["has_expansion"]], key, expanded_only=False) for key in keys},
        "notes": ["summary is the alias subset; all_summary includes every query",
                  "rewrite uses baseline for queries without aliases",
                  "mean rank is conditional on hits; mrr10 includes misses as zero",
                  "old artifacts without request status retain unknown status"],
    }


def save_output(path: str, result: dict) -> None:
    if path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compare_paid(base_url: str, paid_url: str, cases: list[dict]) -> dict:
    """同一标注集交替请求关闭/开启兜底的实例，计入失败样本。"""
    rows = []
    endpoints = (("off", base_url), ("on", paid_url))
    for index, case in enumerate(cases):
        row = {"q": case["q"]}
        order = endpoints if index % 2 == 0 else endpoints[::-1]
        for name, endpoint in order:
            started = time.perf_counter()
            try:
                payload = search(endpoint, case["q"])
            except urllib.error.HTTPError as exc:
                outcome = {"ok": False, "status": exc.code, "hit10": False, "strong": False, "first_rank": None}
            except (urllib.error.URLError, TimeoutError):
                outcome = {"ok": False, "status": "connection", "hit10": False, "strong": False, "first_rank": None}
            else:
                results = to_results(payload)
                outcome = metrics(results, case["expect_domains"])
                outcome.update(
                    ok=True, status=200, total=len(results), cached=payload["meta"]["cached"],
                    engines=payload["meta"]["engines"], unresponsive=payload["meta"]["unresponsive"],
                )
            outcome["ms"] = round((time.perf_counter() - started) * 1000)
            row[name] = outcome
        rows.append(row)
        print(
            f"case={index+1} q={case['q']!r} off_hit10={row['off']['hit10']} "
            f"on_hit10={row['on']['hit10']} off_ms={row['off']['ms']} on_ms={row['on']['ms']}",
            flush=True,
        )

    summary = {}
    for name, _ in endpoints:
        values = [row[name] for row in rows]
        latencies = sorted(value["ms"] for value in values)
        summary[name] = {
            "cases": len(values), "success": sum(value["ok"] for value in values),
            "hit10": sum(value["hit10"] for value in values),
            "strong": sum(value["strong"] for value in values),
            "median_ms": statistics.median(latencies),
            "p95_ms": latencies[math.ceil(len(latencies) * 0.95) - 1],
        }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return {"rows": rows, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--aggregate", type=Path, help="Aggregate stored row metrics without live API calls")
    parser.add_argument("--compare-base-url", default="", help="开启付费兜底的隔离实例；与 --base-url 的关闭实例比较")
    args = parser.parse_args()
    if args.aggregate:
        source_bytes = args.aggregate.read_bytes()
        rows = json.loads(source_bytes)["rows"]
        result = evaluation(rows, {"artifact": args.aggregate.as_posix(), "sha256": hashlib.sha256(source_bytes).hexdigest(), "mode": "offline-aggregation"})
        save_output(args.json_out, result)
        print(json.dumps({"alias_subset": result["summary"], "all_queries": result["all_summary"], "controls": result["controls_summary"]}, ensure_ascii=False))
        return 0
    cases = json.loads(args.labels.read_text(encoding="utf-8"))["cases"]
    if not cases:
        parser.error("empty label set")
    if args.compare_base_url:
        comparison = compare_paid(args.base_url, args.compare_base_url, cases)
        save_output(args.json_out, comparison)
        return 0 if all(arm["success"] == arm["cases"] for arm in comparison["summary"].values()) else 1

    def measured_search(query):
        started = time.perf_counter()
        try:
            payload = search(args.base_url, query)
            candidates = to_results(payload)
            detail = {"ok": True, "cached": payload["meta"]["cached"], "engines": payload["meta"]["engines"]}
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            candidates = []
            detail = {"ok": False, "error": f"HTTP_{exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__}
        detail["ms"] = round((time.perf_counter() - started) * 1000)
        return candidates, detail

    rows = []
    source = {"labels": args.labels.as_posix(), "labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              "mode": "live-returned-candidates", "server_expansion_and_cache": "record deployment settings separately"}
    for case in cases:
        q, expected = case["q"], case["expect_domains"]
        aliases = expand_aliases(q)
        results, request = measured_search(q)
        baseline = {**metrics(rank(results, q, []), expected), **request}
        ranking = {**metrics(rank(results, q, aliases), expected), **request}
        rewrite = None
        if aliases:
            rewritten = q + " " + " ".join(aliases[:2])
            rewritten_results, rewritten_request = measured_search(rewritten)
            rewrite = {**metrics(rank(rewritten_results, q, aliases), expected), **rewritten_request, "rewritten": rewritten}
        row = {"q": q, "aliases": aliases, "candidates": len(results), "has_expansion": bool(aliases),
               "baseline": baseline, "ranking": ranking, "rewrite": rewrite}
        rows.append(row)
        save_output(args.json_out, evaluation(rows, source))
        print(f"case={len(rows)}/{len(cases)} ok={request['ok']} alias={bool(aliases)}", flush=True)
    result = evaluation(rows, source)
    save_output(args.json_out, result)
    print(json.dumps({"alias_subset": result["summary"], "all_queries": result["all_summary"]}, ensure_ascii=False))
    return 0 if all(value["success"] == value["cases"] for value in result["all_summary"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
