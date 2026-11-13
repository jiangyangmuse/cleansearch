"""Compare the deployed Bing route with an isolated free default route."""

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import httpx


ARTIFACTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ARTIFACTS.parents[2] / "apps/api"))

# Exact hosts and known landing paths. Product subpages are counted separately.
CASES = [
    ("tech", "Apple", "apple.com", "/", "/cn", "/jp"),
    ("messaging", "微信", "weixin.qq.com", "/"),
    ("development", "Docker", "docker.com", "/"),
    ("messaging", "Telegram", "telegram.org", "/"),
    ("development", "React", "react.dev", "/"),
    ("development", "Python", "python.org", "/"),
    ("development", "JetBrains", "jetbrains.com", "/", "/zh-cn", "/ja"),
    ("retail", "淘宝", "taobao.com", "/"),
    ("media", "哔哩哔哩", "bilibili.com", "/"),
    ("software", "Mozilla", "mozilla.org", "/", "/en-us", "/zh-cn", "/ja"),
    ("business", "Stripe", "stripe.com", "/", "/jp", "/en-jp", "/en-cn"),
    ("software", "Figma", "figma.com", "/", "/ja", "/zh-cn"),
    ("game", "原神", "ys.mihoyo.com", "/", "/main", "/main/home", "/main/m"),
    ("game", "崩坏星穹铁道", "sr.mihoyo.com", "/", "/main", "/main/home"),
    ("development", "Godot", "godotengine.org", "/"),
    ("software", "VLC", "videolan.org", "/", "/vlc", "/vlc/index.html",
     "/vlc/index.zh_cn.html", "/vlc/index.en.html"),
    ("software", "Krita", "krita.org", "/", "/en", "/zh-cn", "/ja"),
    ("game tools", "Modrinth", "modrinth.com", "/"),
    ("international organization", "UNESCO", "unesco.org", "/", "/en", "/zh"),
    ("university", "東京大学", "u-tokyo.ac.jp", "/", "/ja", "/ja/index.html", "/en", "/en/index.html"),
    ("museum", "Smithsonian Institution", "si.edu", "/"),
    ("government agency", "日本気象庁", "jma.go.jp", "/", "/jma/index.html", "/bosai", "/jma/indexe.html"),
    ("retail", "IKEA", "ikea.com", "/", "/jp/ja", "/jp/en", "/cn/zh", "/us/en", "/global/en"),
    ("industry", "空中客车", "airbus.com", "/", "/en", "/cn", "/zh", "/zh-hans"),
]

ALT_LANDINGS = {
    "ys.mihoyo.com": {
        "yuanshen.com": {"/", "/main", "/main/home"},
        "genshin.hoyoverse.com": {"/", "/zh-tw/home", "/zh-cn/home", "/en/home"},
    },
    "sr.mihoyo.com": {"hsr.hoyoverse.com": {"/", "/zh-cn/home", "/zh-tw/home", "/en-us/home"}},
    "videolan.org": {"images.videolan.org": {"/vlc/index.zh_cn.html", "/vlc/index.en.html"}},
}


def site_kind(url, host, paths):
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    path = parts.path.lower().rstrip("/") or "/"
    if path in ALT_LANDINGS.get(host, {}).get(hostname.removeprefix("www."), ()):
        return "landing"
    if hostname.removeprefix("www.") != host:
        return None
    if host == "jma.go.jp" and parts.fragment:
        return "subpage"
    return "landing" if path in paths else "subpage"


def visible_results(body, host, paths):
    sections = {"official": (body.get("official") or {}).get("entries", [])}
    sections.update(body.get("groups", {}))
    return [
        {
            "section": section, "position": position, "id": row["id"],
            "url": row["url"], "title": row["title"], "snippet": row["snippet"],
            "source": row.get("origin", "search"), "engines": row["engine"],
            "warning": row.get("brand_warning"), "site_kind": site_kind(row["url"], host, paths),
        }
        for section, rows in sections.items()
        for position, row in enumerate(rows, 1)
    ]


async def check(client, mode, case, region=None):
    category, query, host, *paths = case
    started = time.perf_counter()
    response = await client.post("/api/search", json={
        "q": f"{query} !b" if mode == "bing" else query, "region": region,
    })
    body = response.json()
    return {
        "mode": mode, "query": query, "category": category, "host": host, "paths": paths,
        "status": response.status_code, "seconds": round(time.perf_counter() - started, 3),
        "meta": body.get("meta"), "error": body.get("error"), "results": visible_results(body, host, paths),
    }


async def main():
    os.environ.update({
        "SEARCH_PROVIDER": "searxng", "SEARXNG_URL": "http://127.0.0.1:8888",
        "PAID_FALLBACK": "false", "CACHE_ENABLED": "false", "RDAP_ENABLED": "false",
        "SERVE_WEB": "false",
    })
    from app.core.official import BRANDS, brand_for_query
    from app.main import app

    retry_only = "--retry-timeouts" in sys.argv
    output = ARTIFACTS / ("official-retries.json" if retry_only else "official-matrix.json")
    timeout_queries = set()
    if retry_only:
        first_pass = json.loads((ARTIFACTS / "official-matrix.json").read_text(encoding="utf-8"))
        timeout_queries = {
            row["query"] for row in first_pass["results"]
            if row["mode"] == "free-default" and (row["error"] or {}).get("code") == "UPSTREAM_TIMEOUT"
        }
    results = []
    async with (
        httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=25, trust_env=False) as bing,
        httpx.AsyncClient(base_url="http://127.0.0.1", transport=httpx.ASGITransport(app=app)) as default,
    ):
        for case in CASES:
            if retry_only and case[1] not in timeout_queries:
                continue
            brand = brand_for_query(case[1])
            routes = ((default, "free-default"),) if retry_only else ((bing, "bing"), (default, "free-default"))
            for client, mode in routes:
                row = await check(client, mode, case)
                row["catalog"] = brand.key if brand else None
                results.append(row)
                match = [
                    f"{item['section']}#{item['position']}:{item['source']}"
                    for item in row["results"] if item["site_kind"] == "landing"
                ]
                print(f"{mode:12} {case[1]:24} {row['status']} {', '.join(match) or '-'}", flush=True)
            output.write_text(
                json.dumps({"catalog_size": len(BRANDS), "results": results}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


if __name__ == "__main__":
    asyncio.run(main())
