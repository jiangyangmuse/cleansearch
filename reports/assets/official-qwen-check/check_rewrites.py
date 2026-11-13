"""Test whether one local-model query rewrite can recover a missing homepage."""

import asyncio
import json
import re
import time

import httpx

from check_official import ARTIFACTS, CASES, check, site_kind
from check_qwen import MODEL


TARGETS = ("VLC", "東京大学", "日本気象庁", "空中客车")
SYSTEM = (
    "Rewrite the user's organization or product name into one short search engine query to "
    "find its official homepage. Use the native spelling when you know it, optionally add the "
    "English or local-language equivalent of official homepage. Do not include URLs, domain "
    "names, search operators, explanations, or any other fields. Return JSON with one query field."
)


async def rewrite(client, query):
    started = time.perf_counter()
    response = await client.post("/api/chat", json={
        "model": MODEL, "think": False, "stream": False,
        "format": {
            "type": "object", "required": ["query"], "additionalProperties": False,
            "properties": {"query": {"type": "string"}},
        },
        "options": {"temperature": 0, "num_predict": 96},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": query}],
    })
    response.raise_for_status()
    body = response.json()
    assert body["done"] and body["done_reason"] == "stop"
    rewritten = json.loads(body["message"]["content"])["query"].strip()
    assert 2 <= len(rewritten) <= 80 and not re.search(r"[!:/\\.]", rewritten), rewritten
    return rewritten, round(time.perf_counter() - started, 3)


async def raw_bing(client, query, host, paths):
    response = await client.get("/search", params={
        "q": query, "format": "json", "pageno": 1, "safesearch": 1, "engines": "bing",
    })
    rows = response.json().get("results", []) if response.status_code == 200 else []
    rows = [row for row in rows if row.get("engine") == "bing" or "bing" in row.get("engines", [])]
    return {
        "status": response.status_code, "bing_count": len(rows),
        "landing_matches": [
            {"position": pos, "url": row["url"]}
            for pos, row in enumerate(rows, 1) if site_kind(row["url"], host, paths) == "landing"
        ],
    }


async def main():
    results = []
    async with (
        httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=90, trust_env=False) as ollama,
        httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=25, trust_env=False) as bing,
        httpx.AsyncClient(base_url="http://127.0.0.1:8888", timeout=20, trust_env=False) as upstream,
    ):
        for category, query, host, *paths in CASES:
            if query not in TARGETS:
                continue
            raw = await raw_bing(upstream, query, host, paths)
            rewritten, model_seconds = await rewrite(ollama, query)
            row = await check(bing, "bing", (category, rewritten, host, *paths))
            matches = [item for item in row["results"] if item["site_kind"] == "landing"]
            evidence = {"original_query": query, "original_upstream": raw, "model_seconds": model_seconds, **row}
            if query in {"東京大学", "日本気象庁"}:
                evidence["japan_original"] = await check(bing, "bing", (category, query, host, *paths), "jp")
                evidence["japan_rewrite"] = await check(bing, "bing", (category, rewritten, host, *paths), "jp")
            results.append(evidence)
            print(f"{query} -> {rewritten} {row['status']} "
                  f"original_raw={raw['landing_matches']} rewritten_hits={[item['url'] for item in matches]}", flush=True)
            (ARTIFACTS / "rewrite-results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
            )


if __name__ == "__main__":
    asyncio.run(main())
