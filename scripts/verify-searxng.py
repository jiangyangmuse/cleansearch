"""从 CleanSearch API 验收真实 SearXNG。运行方式见 README。"""

from __future__ import annotations

import argparse
import time

import httpx

ENGINES = {
    "g": "google",
    "b": "bing",
    "d": "duckduckgo",
    "br": "brave",
    "sc": "scholar",
    "gc": "google cse",
    "sp": "startpage",
    "mj": "mojeek",
    "y": "yahoo",
    "sg": "sogou",
}
QUERIES = ("日本 首都", "Python documentation", "HTTP")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--engines", nargs="+", choices=ENGINES, default=["g", "b"])
    args = parser.parse_args()
    if not 2 <= len(set(args.engines)) == len(args.engines) <= 3:
        parser.error("--engines 需给出 2–3 个不同的引擎短码")

    cases = [
        (f"{query} {code}", query, ENGINES[code], None, "suffix")
        for code in args.engines for query in QUERIES
    ] + [
        (f"Python !{args.engines[0]}", "Python", ENGINES[args.engines[0]], None, "bang"),
        ("日本 首都 jp", "日本 首都", "default", "jp", "suffix"),
        ("C g", "C g", "default", None, "default"),
    ]
    passed = 0
    with httpx.Client(base_url=args.base_url, timeout=15.0) as client:
        try:
            health = client.get("/api/health").raise_for_status().json()
            if health["provider"] != "searxng":
                print(f"FAIL: provider={health['provider']}；请启动真实 SearXNG 模式")
                return 1
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            print(f"FAIL: 无法确认 /api/health 的检索模式：{exc}")
            return 1

        # 引擎表里的 fallbacks 是公开契约：g 在 google 被拒时回退到 google cse 仍算通过，
        # 但必须记录用了回退，避免把"上游降级成功"当成"目标引擎可用"。
        catalog: dict[str, list[str]] = {}
        try:
            for entry in client.get("/api/engines").raise_for_status().json()["engines"]:
                if entry.get("section") != "custom" and entry.get("searx_engine"):
                    catalog[entry["searx_engine"]] = entry.get("fallbacks") or []
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            print(f"FAIL: 无法读取引擎表：{exc}")
            return 1

        for query, cleaned, engine, region, router in cases:
            start = time.perf_counter()
            try:
                response = client.post("/api/search", json={"q": query})
                body = response.json()
                if not response.is_success:
                    err = body.get("error", {})
                    raise ValueError(f"HTTP {response.status_code} {err.get('code', '')} {err.get('message', '')}")
                meta, parsed = body["meta"], body["parsed"]
                expected_route = dict(q=cleaned, engine=engine, region=region, router=router)
                if any(parsed[key] != expected for key, expected in expected_route.items()):
                    raise ValueError(f"路由不匹配：{parsed}")
                if meta["provider"] != "searxng" or meta["status"] != "ok" or meta["total"] < 1:
                    raise ValueError(f"无可展示的真实结果：{meta['status']}")
                sources = sorted({
                    source for group in body["groups"].values() for item in group for source in item["engine"]
                })
                expected_source = "google scholar" if engine == "scholar" else engine
                fallback_hit = ""
                if engine != "default":
                    allowed = [expected_source, *catalog.get(expected_source, [])]
                    if not sources or set(sources).difference(allowed):
                        raise ValueError(f"预期来源仅为 {expected_source} 或回退 {allowed[1:]}，实际 {sources}")
                    if expected_source not in sources:
                        hit = next(source for source in allowed[1:] if source in sources)
                        fallback_hit = f" 回退={hit}"
                details = f"结果={meta['total']} 来源={sources} 失败引擎={meta['unresponsive']}{fallback_hit}"
                status = "PASS"
                passed += 1
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                status, details = "FAIL", str(exc)
            elapsed = round((time.perf_counter() - start) * 1000)
            print(f"{status} {query!r}  {elapsed} ms  {details}")

    print(f"真实搜索验收：{passed}/{len(cases)} ({passed / len(cases):.0%})")
    return int(passed != len(cases))


if __name__ == "__main__":
    raise SystemExit(main())
