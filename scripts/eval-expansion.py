"""P2 评估：词典查询扩展对排序与召回的影响。

三种条件对比（同一批标注查询）：
  baseline   —— 原查询，排序不用别名
  ranking    —— 原查询，排序用别名词（只改排序，不改上游召回）
  rewrite    —— 把别名并入查询再发上游（改召回）

指标：期望域名在 Top10 的命中率、进入强相关的命中率、首个命中排名。
"""

from __future__ import annotations

import argparse
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


def summarize(rows: list[dict], key: str) -> dict:
    values = [row[key] for row in rows if row["has_expansion"]]
    ranks = [value["first_rank"] for value in values if value["first_rank"]]
    return {
        "cases": len(values),
        "hit10": sum(1 for v in values if v["hit10"]),
        "strong": sum(1 for v in values if v["strong"]),
        "mean_first_rank": round(statistics.mean(ranks), 2) if ranks else None,
    }


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
    parser.add_argument("--compare-base-url", default="", help="开启付费兜底的隔离实例；与 --base-url 的关闭实例比较")
    args = parser.parse_args()

    cases = json.loads(LABELS.read_text(encoding="utf-8"))["cases"]
    if args.compare_base_url:
        comparison = compare_paid(args.base_url, args.compare_base_url, cases)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(arm["success"] == arm["cases"] for arm in comparison["summary"].values()) else 1
    rows: list[dict] = []

    for case in cases:
        q, expected = case["q"], case["expect_domains"]
        aliases = expand_aliases(q)
        payload = search(args.base_url, q)
        results = to_results(payload)

        baseline = metrics(rank(results, q, []), expected)
        ranking = metrics(rank(results, q, aliases), expected)

        rewrite = None
        if aliases:
            rewritten = q + " " + " ".join(aliases[:2])
            rewritten_payload = search(args.base_url, rewritten)
            rewrite = metrics(rank(to_results(rewritten_payload), q, aliases), expected)
            rewrite["rewritten"] = rewritten

        row = {
            "q": q,
            "aliases": aliases,
            "candidates": len(results),
            "has_expansion": bool(aliases),
            "baseline": baseline,
            "ranking": ranking,
            "rewrite": rewrite,
        }
        rows.append(row)
        flag = "ALIAS" if aliases else "     "
        extra = f" rewrite={rewrite['first_rank']}" if rewrite else ""
        print(
            f"{flag} {q[:22]:<24} 候选={len(results):>2} "
            f"base={baseline['first_rank']} ranking={ranking['first_rank']}{extra}"
        )

    summary = {key: summarize(rows, key) for key in ("baseline", "ranking")}
    expanded_rows = [row for row in rows if row["has_expansion"]]
    summary["rewrite"] = {
        "cases": len(expanded_rows),
        "hit10": sum(1 for row in expanded_rows if row["rewrite"] and row["rewrite"]["hit10"]),
        "strong": sum(1 for row in expanded_rows if row["rewrite"] and row["rewrite"]["strong"]),
        "mean_first_rank": (
            round(statistics.mean([r["rewrite"]["first_rank"] for r in expanded_rows
                                   if r["rewrite"] and r["rewrite"]["first_rank"]]), 2)
            if any(r["rewrite"] and r["rewrite"]["first_rank"] for r in expanded_rows)
            else None
        ),
    }

    print("\n=== 汇总（仅统计有扩展的 %d 条） ===" % len(expanded_rows))
    for key in ("baseline", "ranking", "rewrite"):
        item = summary[key]
        print(
            f"{key:<8} 命中Top10 {item['hit10']}/{item['cases']}  "
            f"强相关 {item['strong']}/{item['cases']}  首个命中均位 {item['mean_first_rank']}"
        )

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
