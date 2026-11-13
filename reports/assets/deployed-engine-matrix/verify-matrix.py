"""真实部署矩阵：逐条核对路由/实际来源，空态和可用性分别统计。"""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CASES = [("b", "python 文档"), ("d", "python 文档"), ("y", "python 文档"),
         ("mj", "python 文档"), ("gc", "python 文档"), ("n", "python 文档"),
         ("yd", "python 文档"), ("sw", "python 文档"), ("w", "Python"),
         ("g", "python 文档"), ("sc", "retrieval augmented generation"),
         ("sg", "python 文档"), ("sp", "python 文档")]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--out", default=str(Path(__file__).with_name("api-matrix.json")))
args = parser.parse_args()
output = Path(args.out)


def request(path, data=None):
    raw = json.dumps(data).encode() if data is not None else None
    req = Request(args.base_url.rstrip("/") + path, data=raw,
                  headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=35)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


_, health = request("/api/health")
_, catalog = request("/api/engines")
assert health["provider"] == "searxng" and health["web_built"], health
specs = {item["code"]: item for item in catalog["engines"]}
evidence = {"base_url": args.base_url, "health": health, "catalog_before": catalog,
            "checks": [], "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "scope": "真实线上搜索；仅公开测试查询；不写书签；付费可限于首屏 g/gc/sc"}


def save():
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


def check(code, query, page, phase):
    spec = specs[code]
    allowed = {spec["searx_engine"], *spec["fallbacks"]}
    paid_provider = "brave" if spec["paid"] == "brave" else "serper"
    if page == 1 and spec["paid"] and catalog["paid"].get(paid_provider):
        allowed.add(paid_provider)
    row = {"phase": phase, "code": code, "q": f"{query} {code}", "page": page,
           "expected_engine": spec["engine"], "allowed_sources": sorted(allowed)}
    started = time.perf_counter()
    try:
        status, body = request("/api/search", {"q": row["q"], "page": page})
        row["http"] = status
        if status == 200:
            parsed, meta = body["parsed"], body["meta"]
            items = [item for group in body["groups"].values() for item in group]
            sources = {source for item in items for source in item["engine"]}
            route_ok = parsed["q"] == query and parsed["engine"] == spec["engine"] and parsed["router"] == "suffix"
            source_ok = sources <= allowed and set(meta["engines"]) <= allowed
            semantic_ok = meta["total"] == len(items) and meta["status"] == ("ok" if items else "empty")
            row.update(parsed=parsed, meta={k: v for k, v in meta.items() if k != "sid"},
                       results=[{k: item[k] for k in ("url", "title", "engine")} for item in items],
                       sources=sorted(sources), route_ok=route_ok, source_ok=source_ok,
                       contract_ok=route_ok and source_ok and semantic_ok and meta["provider"] == "searxng",
                       has_results=bool(items), direct=spec["searx_engine"] in sources,
                       no_paid_source=not bool(sources & {"serper", "brave"}))
            if phase == "repeat":
                row["contract_ok"] = row["contract_ok"] and meta["cached"] is True
        else:
            row.update(error=body.get("error"), has_results=False, route_ok=None, source_ok=None,
                       contract_ok=status == 503 and body.get("error", {}).get("code") in {
                           "ENGINE_UNAVAILABLE", "UPSTREAM_UNAVAILABLE", "UPSTREAM_TIMEOUT"})
    except (OSError, ValueError, KeyError, TypeError) as error:
        row.update(error=f"{type(error).__name__}: {error}", contract_ok=False, has_results=False)
    row["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    evidence["checks"].append(row)
    save()
    print(json.dumps({k: row.get(k) for k in ("phase", "code", "page", "http", "sources", "has_results", "contract_ok", "elapsed_ms")}, ensure_ascii=False), flush=True)
    return row


for code, query in CASES:
    check(code, query, 1, "first")
for code, query in CASES:
    if code in {"b", "g"} and next(r for r in evidence["checks"] if r["code"] == code)["has_results"]:
        check(code, query, 1, "repeat")
for code, query in CASES:
    check(code, query, 2, "page2")
_, evidence["catalog_after"] = request("/api/engines")
first = [row for row in evidence["checks"] if row["phase"] == "first"]
evidence["summary"] = {
    "first_with_results": sum(row["has_results"] for row in first), "first_total": len(first),
    "direct_with_results": sum(bool(row.get("direct")) for row in first),
    "fallback_with_results": sum(row["has_results"] and not row.get("direct") for row in first),
    "contract_failures": sum(not row["contract_ok"] for row in evidence["checks"]),
    "paid_source_on_page2": any(not row.get("no_paid_source", True) for row in evidence["checks"] if row["page"] == 2),
}
evidence["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
save()
print(json.dumps(evidence["summary"], ensure_ascii=False), flush=True)
raise SystemExit(int(evidence["summary"]["contract_failures"] > 0 or evidence["summary"]["first_with_results"] < 13))
