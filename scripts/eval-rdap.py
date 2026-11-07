"""用 OpenPhish 20 个注册域名和 20 个公开参考域名校准年龄信号，只访问 feed 与 RDAP。"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import get_settings
from app.core.fetch import SafeFetcher
from app.core.rdap import AGE_PENALTY, DomainAgeStore, lookup, registered_domain
from app.core.safety import Blocklist, SafetyScorer

FEED = "https://openphish.com/feed.txt"
REFERENCE_DOMAINS = (
    "python.org", "github.com", "wikipedia.org", "mozilla.org", "microsoft.com",
    "apple.com", "w3.org", "ietf.org", "iana.org", "icann.org",
    "ubuntu.com", "kernel.org", "postgresql.org", "sqlite.org", "docs.rs",
    "rust-lang.org", "nodejs.org", "npmjs.com", "pypi.org", "stackoverflow.com",
)


async def collect(fetcher: SafeFetcher) -> tuple[list[dict], dict]:
    page = await fetcher.fetch(FEED)
    scorer = SafetyScorer(Blocklist())
    by_domain = {}
    for line in page.text.splitlines():
        url = line.strip()
        try:
            host = urlsplit(url).hostname or ""
        except ValueError:
            continue
        domain = registered_domain(host)
        if domain is not None and domain not in REFERENCE_DOMAINS:
            by_domain.setdefault(domain, scorer.evaluate(url).risk)
    chosen = sorted(by_domain, key=lambda domain: hashlib.sha256(domain.encode()).hexdigest())[:20]
    if len(chosen) != 20:
        raise ValueError("公开 feed 中不足 20 个可解析注册域名")
    rows = [{"domain": domain.replace(".", "[.]"), "label": "feed-phishing", "base_risk": by_domain[domain]} for domain in chosen]
    rows.extend({"domain": domain.replace(".", "[.]"), "label": "reference", "base_risk": scorer.evaluate(f"https://{domain}").risk} for domain in REFERENCE_DOMAINS)
    return rows, {"url": FEED, "sha256": hashlib.sha256(page.raw).hexdigest(), "collected_at": datetime.now(timezone.utc).isoformat()}


async def evaluate(args) -> dict:
    settings = get_settings()
    fetcher = SafeFetcher(timeout=12, extra_cidrs=settings.fetch_extra_cidrs)
    if args.samples:
        previous = json.loads(Path(args.samples).read_text(encoding="utf-8"))
        samples, source = previous["rows"], previous["source"]
    else:
        samples, source = await collect(fetcher)
    if len(samples) != 40:
        raise ValueError("样本必须为 20 + 20 条")
    store = DomainAgeStore(Path(args.db_path), ttl_days=settings.rdap_ttl_days)
    semaphore = asyncio.Semaphore(3)
    rate_lock = asyncio.Lock()
    next_start = 0.0

    async def one(sample):
        nonlocal next_start
        domain = sample["domain"].replace("[.]", ".")
        async with semaphore:
            async with rate_lock:
                await asyncio.sleep(max(0, next_start - time.monotonic()))
                next_start = time.monotonic() + 1.1
            started = time.perf_counter()
            info = await lookup(domain, store, fetcher)
            elapsed = round((time.perf_counter() - started) * 1000)
        age = round((time.time() - info.registered_at) / 86400, 2) if info and info.registered_at is not None else None
        row = {key: sample[key] for key in ("domain", "label", "base_risk")}
        row.update(registered_at=info.registered_at if info else None, age_days=age, ms=elapsed)
        print(f"label={row['label']} domain={row['domain']} age_days={age} ms={elapsed}", flush=True)
        return row

    tasks = []
    try:
        for sample in samples:
            tasks.append(asyncio.create_task(one(sample)))
        rows = await asyncio.gather(*tasks)
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        store.close()

    summary = {}
    for label in ("feed-phishing", "reference"):
        group = [row for row in rows if row["label"] == label]
        known = [row for row in group if row["age_days"] is not None]
        thresholds = {}
        for days in (7, 30, 90):
            young = [row for row in known if row["age_days"] < days]
            newly_flagged = sum(
                row["base_risk"] < 0.35 <= row["base_risk"] + AGE_PENALTY
                for row in young if row["base_risk"] > 0
            )
            thresholds[str(days)] = {"young": len(young), "newly_flagged": newly_flagged}
        weights = {}
        for weight in (0.1, 0.15, 0.2):
            weights[str(weight)] = sum(
                row["base_risk"] < 0.35 <= row["base_risk"] + weight
                for row in known if row["age_days"] < 30 and row["base_risk"] > 0
            )
        summary[label] = {"samples": len(group), "age_known": len(known), "unknown": len(group) - len(known), "thresholds": thresholds, "newly_flagged_by_weight": weights}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return {"source": source, "measured_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True, help="使用独立派生缓存数据库")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--samples", default="", help="重放上次输出中的固定域名样本")
    args = parser.parse_args()
    result = asyncio.run(evaluate(args))
    output = Path(args.json_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
