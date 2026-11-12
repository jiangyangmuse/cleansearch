"""逐个引擎探测 SearXNG 可用性，输出 JSON 矩阵。

用法：
  python scripts/probe-engines.py --base-url http://127.0.0.1:8888 \
      --json-out docs/m11-evidence/engine-probe.json

每个引擎跑两轮查询，记录结果数、来源、延迟与 unresponsive；
先读取 /config 跳过未加载的引擎，避免静默默认聚合造成额外请求。
用于回答「哪些后缀现在真的能用」，不替代 API 层验收。
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request

ENGINES = [
    "google", "google cse", "google scholar", "bing", "duckduckgo", "duckduckgo web",
    "yahoo", "sogou", "brave", "startpage", "mojeek", "qwant", "baidu", "naver",
    "yep", "seznam", "marginalia", "dogpile", "swisscows", "yandex", "yandex api",
    "360search", "quark", "wikipedia", "wikidata", "youtube", "github", "arxiv",
]

QUERIES = ["python 文档", "SearXNG meta search"]


def loaded_engines(base: str) -> set[str] | None:
    """配置不可读时保留未知，不能将它误当成所有引擎都未加载。"""
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/config", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        engines = payload.get("engines") if isinstance(payload, dict) else None
        if not isinstance(engines, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in engines):
            return None
        return {item["name"] for item in engines}
    except (OSError, ValueError):
        return None


def probe(base: str, engine: str, query: str, loaded: set[str] | None = None) -> dict:
    if loaded is not None and engine not in loaded:
        return {"engine": engine, "query": query, "ms": 0, "ok": False, "count": 0,
                "sources": [], "unresponsive": [], "skipped": "not_loaded"}
    params = urllib.parse.urlencode({"q": query, "format": "json", "engines": engine, "pageno": 1})
    url = f"{base}/search?{params}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 探测脚本要记录所有失败形态
        return {
            "engine": engine,
            "query": query,
            "ms": int((time.perf_counter() - started) * 1000),
            "ok": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    elapsed = int((time.perf_counter() - started) * 1000)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return {"engine": engine, "query": query, "ms": elapsed, "ok": False,
                "error": "响应缺少 results 列表"}
    results = [item for item in payload["results"] if isinstance(item, dict)]

    def sources(item: dict) -> list[str]:
        value = item.get("engines") or ([item["engine"]] if item.get("engine") else [])
        return [source for source in value if isinstance(source, str)] if isinstance(value, list) else []

    matched = [item for item in results if engine in sources(item)]
    engines = sorted(
        {
            source
            for item in results
            for source in sources(item)
        }
    )
    return {
        "engine": engine,
        "query": query,
        "ms": elapsed,
        # 未启用的引擎可能被 SearXNG 静默回落到默认聚合；不能以总条数判通过。
        "ok": bool(matched),
        "count": len(matched),
        "raw_count": len(payload["results"]),
        "routing_ok": bool(matched) if results else None,
        "sources": engines,
        "unresponsive": payload.get("unresponsive_engines") or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8888")
    parser.add_argument("--engines", nargs="*", default=ENGINES)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    loaded = loaded_engines(args.base_url)
    rows = []
    for engine in args.engines:
        attempts = [probe(args.base_url, engine, q, loaded) for q in QUERIES]
        oks = [item for item in attempts if item.get("ok")]
        latencies = [item["ms"] for item in attempts]
        sources = sorted({source for item in attempts for source in item.get("sources", [])})
        errors = sorted({item.get("error", "") for item in attempts if item.get("error")})
        unresponsive = sorted(
            {f"{item[0]}:{item[1]}" for attempt in attempts for item in attempt.get("unresponsive", [])}
        )
        row = {
            "engine": engine,
            "ok": len(oks),
            "attempts": len(attempts),
            "search_requests": sum(not item.get("skipped") for item in attempts),
            "catalog_checked": loaded is not None,
            "skipped": "not_loaded" if loaded is not None and engine not in loaded else "",
            "median_ms": int(statistics.median(latencies)) if latencies else 0,
            "counts": [item.get("count", 0) for item in attempts],
            "sources": sources,
            "errors": errors,
            "unresponsive": unresponsive,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
