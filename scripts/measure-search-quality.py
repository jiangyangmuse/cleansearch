"""真实上游质量测量：默认多引擎模式下的延迟、结果数、来源与失败引擎。

与 verify-searxng.py 的分工：那个脚本校验「路由参数是否真的传给了上游」，
这里只测「在当前网络与 SearXNG 配置下，搜索到底能不能用、多快」。

用法：python scripts/measure-search-quality.py --base-url http://127.0.0.1:18092 [--rounds 2]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

import httpx

QUERIES = (
    "日本 首都",
    "Python documentation",
    "HTTP",
    "asyncio event loop 原理",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    rows: list[dict] = []
    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        health = client.get("/api/health").raise_for_status().json()
        if health["provider"] != "searxng":
            print(f"FAIL: provider={health['provider']}，需要真实 SearXNG 模式")
            return 1
        print(f"provider=searxng upstream={health['searxng_url']}")

        for round_index in range(args.rounds):
            for query in QUERIES:
                started = time.perf_counter()
                response = client.post("/api/search", json={"q": query})
                elapsed = int((time.perf_counter() - started) * 1000)
                body = response.json()
                if not response.is_success or body["meta"]["total"] == 0:
                    error = body.get("error", {}).get("code", f"HTTP {response.status_code}")
                    rows.append(
                        {
                            "round": round_index + 1,
                            "q": query,
                            "ok": False,
                            "ms": elapsed,
                            "error": "NO_RESULTS" if response.is_success else error,
                        }
                    )
                    continue
                meta = body["meta"]
                engines = sorted(
                    {source for group in body["groups"].values() for item in group for source in item["engine"]}
                )
                rows.append(
                    {
                        "round": round_index + 1,
                        "q": query,
                        "ok": True,
                        "ms": elapsed,
                        "total": meta["total"],
                        "upstream_total": meta["upstream_total"],
                        "cached": meta["cached"],
                        "engines": engines,
                        "unresponsive": meta["unresponsive"],
                    }
                )

    ok_rows = [row for row in rows if row["ok"]]
    print(f"\n{len(ok_rows)}/{len(rows)} 次返回可展示结果")
    for row in rows:
        if row["ok"]:
            print(
                f"  r{row['round']} {row['q'][:24]:<26} {row['ms']:>6} ms  结果={row['total']:>2}  "
                f"缓存={row['cached']}  来源={','.join(row['engines']) or '-'}  "
                f"失败={','.join(row['unresponsive']) or '-'}"
            )
        else:
            print(f"  r{row['round']} {row['q'][:24]:<26} {row['ms']:>6} ms  ERROR {row['error']}")
    if ok_rows:
        latencies = [row["ms"] for row in ok_rows]
        print(
            f"\n延迟 中位 {statistics.median(latencies):.0f} ms / 最大 {max(latencies)} ms / "
            f"成功 {len(ok_rows)}"
        )
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
    return 0 if ok_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
