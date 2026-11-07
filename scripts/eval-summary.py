"""Capture fast/full SSE output and validate completion and citation binding.

These are protocol/traceability checks, not an automated factuality score.
Only use public queries: output contains generated text and source URLs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def events(response):
    """Read complete SSE frames, including multiline data and comments."""
    name, data = "message", []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield name, json.loads("\n".join(data))
            name, data = "message", []
        elif line.startswith("event:"):
            name = line[6:].lstrip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    # An unterminated last frame is not treated as a completed event.


def assess(row: dict, results: list[dict], sid: str, mode: str) -> dict:
    by_id = {item["id"]: item["url"] for item in results}
    cites = row.get("citations", [])
    numbers = [cite.get("i") for cite in cites]
    mentions = sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", row.get("text", ""))))
    meta, done = row.get("meta") or {}, row.get("done") or {}
    checks = {
        "stream_completed": bool(row.get("done")) and not row.get("error"),
        "correct_session_and_mode": meta.get("sid") == sid and meta.get("mode") == mode and done.get("mode") == mode,
        "nonempty_text": bool(row.get("text", "").strip()),
        "citation_numbers_unique": bool(numbers) and all(type(n) is int and n > 0 for n in numbers) and len(set(numbers)) == len(numbers),
        "citation_urls_bound": bool(cites) and all(by_id.get(c.get("result_id")) == c.get("url") for c in cites),
        "declared_counts_match": meta.get("sources") == len(cites) and done.get("tokens") == row.get("token_chunks"),
        "numbered_mentions_valid": bool(mentions) and set(mentions).issubset(numbers),
        "degradation_consistent": (bool(meta.get("failed") or meta.get("truncated")) == bool(meta.get("degraded")) == bool(done.get("partial"))),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "numbered_mentions": mentions, "factuality": "requires-human-review"}


def request_json(url: str, body=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def measure(base: str, q: str, modes: list[str]):
    started = time.perf_counter()
    search = request_json(base + "/api/search", {"q": q})
    search_ms = round((time.perf_counter() - started) * 1000)
    results = [item for group in search["groups"].values() for item in group]
    sid = search["meta"]["sid"]
    for mode in modes:
        row = {"query": q, "mode": mode, "search_ms": search_ms,
               "search": {"cached": search["meta"]["cached"], "engines": search["meta"]["engines"],
                          "sources": [{key: item[key] for key in ("id", "url", "title", "snippet")} for item in results]},
               "citations": [], "text": "", "token_chunks": 0, "first_text_ms": None}
        started = time.perf_counter()
        try:
            url = base + "/api/summarize?" + urllib.parse.urlencode({"sid": sid, "mode": mode})
            with urllib.request.urlopen(url, timeout=120) as response:
                for event, data in events(response):
                    if event == "token" and data.get("t"):
                        if row["first_text_ms"] is None:
                            row["first_text_ms"] = round((time.perf_counter() - started) * 1000)
                        row["text"] += data["t"]
                        row["token_chunks"] += 1
                    elif event == "cite":
                        row["citations"].append(data)
                    elif event in ("meta", "done", "error"):
                        row[event] = data
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            row["error"] = {"code": f"HTTP_{exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__}
        row["total_ms"] = round((time.perf_counter() - started) * 1000)
        row["assessment"] = assess(row, results, sid, mode)
        print(f"mode={mode} passed={row['assessment']['passed']} first_ms={row['first_text_ms']} query={q!r}", flush=True)
        yield row


def summarize(rows):
    result = {}
    for mode in ("fast", "full"):
        group = [row for row in rows if row["mode"] == mode]
        if not group:
            continue
        first = [row["first_text_ms"] for row in group if row["first_text_ms"] is not None]
        result[mode] = {"cases": len(group), "protocol_passed": sum(r["assessment"]["passed"] for r in group),
                        "first_text_median_ms": statistics.median(first) if first else None,
                        "total_median_ms": statistics.median(r["total_ms"] for r in group),
                        "fetched": sum(r.get("meta", {}).get("fetched", 0) for r in group),
                        "failed": sum(r.get("meta", {}).get("failed", 0) for r in group),
                        "partial": sum(bool(r.get("done", {}).get("partial")) for r in group)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--query", action="append", default=[], help="Public query; repeat to add topics")
    parser.add_argument("--modes", nargs="+", choices=("fast", "full"), default=["fast", "full"])
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--reassess", type=Path, help="Revalidate captured text/citations without API calls")
    args = parser.parse_args()
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    if args.reassess:
        output = json.loads(args.reassess.read_text(encoding="utf-8"))
        for row in output["rows"]:
            if row.get("meta") and row.get("search"):
                row["assessment"] = assess(row, row["search"]["sources"], row["meta"]["sid"], row["mode"])
        output["reassessed_at"] = datetime.now(timezone.utc).isoformat()
        output["assessment_tool_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        output["summary"] = summarize(output["rows"])
        args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(output["summary"], ensure_ascii=False))
        return 0 if all(row["assessment"]["passed"] for row in output["rows"]) else 1
    if not args.query:
        parser.error("use --query or --reassess")
    output = {"scope": "completion-citation-binding-not-factuality", "measured_at": datetime.now(timezone.utc).isoformat(),
              "latency_scope": "summary-request only; search_ms recorded separately; warm/cold state uncontrolled", "rows": []}
    try:
        health = request_json(args.base_url.rstrip("/") + "/api/health")
        output["service"] = {key: health[key] for key in ("provider", "llm_provider", "llm_model")}
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        output["service"] = {"status": "unavailable"}

    def checkpoint():
        output["summary"] = summarize(output["rows"])
        args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for q in args.query:
        started = time.perf_counter()
        try:
            for row in measure(args.base_url.rstrip("/"), q, args.modes):
                output["rows"].append(row)
                checkpoint()
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            for mode in args.modes:
                output["rows"].append({"query": q, "mode": mode, "first_text_ms": None, "total_ms": round((time.perf_counter() - started) * 1000),
                                       "error": {"code": type(exc).__name__}, "assessment": {"passed": False}})
            checkpoint()
    print(json.dumps(output["summary"], ensure_ascii=False))
    return 0 if all(row["assessment"]["passed"] for row in output["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
