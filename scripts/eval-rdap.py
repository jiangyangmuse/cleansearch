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


def load_samples(path: Path) -> tuple[list[dict], dict]:
    raw = path.read_bytes()
    previous = json.loads(raw)
    scorer = SafetyScorer(Blocklist())
    samples = []
    seen = set()
    for item in previous["rows"]:
        domain = registered_domain(item["domain"].replace("[.]", "."))
        if domain is None or domain in seen:
            raise ValueError("样本域名无效或注册域名重复")
        seen.add(domain)
        label = item.get("label", "reference")
        if label not in ("feed-phishing", "reference"):
            raise ValueError("label 必须为 feed-phishing 或 reference")
        row = dict(item, domain=domain.replace(".", "[.]"), label=label,
                   base_risk=item.get("base_risk", scorer.evaluate(f"https://{domain}").risk))
        samples.append(row)
    if not samples:
        raise ValueError("样本不能为空")
    source = {"artifact": path.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
              "original_source": previous.get("source"),
              "warning": "No provenance field means legitimacy provenance was not recorded"}
    return samples, source


def summarize_rows(rows: list[dict]) -> dict:
    summary = {}
    for label in ("feed-phishing", "reference"):
        group = [row for row in rows if row["label"] == label]
        known = [row for row in group if row.get("age_days") is not None]
        thresholds = {}
        for days in (7, 30, 90):
            young = [row for row in known if 0 <= row["age_days"] < days]
            thresholds[str(days)] = {
                "young": len(young),
                "newly_flagged": sum(row["base_risk"] < 0.35 <= row["base_risk"] + AGE_PENALTY
                                     for row in young if row["base_risk"] > 0),
            }
        weights = {str(weight): sum(row["base_risk"] < 0.35 <= row["base_risk"] + weight
                                   for row in known if 0 <= row["age_days"] < 30 and row["base_risk"] > 0)
                   for weight in (0.1, 0.15, 0.2)}
        summary[label] = {"samples": len(group), "age_known": len(known), "unknown": len(group) - len(known),
                          "thresholds": thresholds, "newly_flagged_by_weight": weights}
    references = [r for r in rows if r["label"] == "reference"]
    fresh = [r for r in references if r.get("age_days") is not None and 0 <= r["age_days"] < 30]
    provenance = lambda r: isinstance(r.get("provenance"), str) and urlsplit(r["provenance"]).scheme in ("https", "http") and bool(urlsplit(r["provenance"]).hostname)
    summary["fresh_normal_controls"] = {
        "age_known_under_30d": len(fresh),
        "with_recorded_provenance": sum(provenance(r) for r in fresh),
        "reference_provenance_missing": sum(not provenance(r) for r in references),
        "new_site_false_positive_rate": None if not fresh else "requires-human-verified-labels",
        "scope": "offline age collection, not online four-second batch coverage",
    }
    return summary


async def evaluate(args) -> dict:
    settings = get_settings()
    fetcher = SafeFetcher(timeout=12, extra_cidrs=settings.fetch_extra_cidrs)
    samples, source = load_samples(Path(args.samples)) if args.samples else await collect(fetcher)
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
        for key in ("provenance", "verified_at"):
            if key in sample:
                row[key] = sample[key]
        row.update(registered_at=info.registered_at if info else None, age_days=age, ms=elapsed)
        print(f"label={row['label']} domain={row['domain']} age_days={age} ms={elapsed}", flush=True)
        return row

    tasks = [asyncio.create_task(one(sample)) for sample in samples]
    try:
        rows = await asyncio.gather(*tasks)
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        store.close()
    return {"source": source, "measured_at": datetime.now(timezone.utc).isoformat(), "summary": summarize_rows(rows), "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", help="使用独立派生缓存数据库；离线汇总不需要")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--samples", default="", help="重放带 domain/label/base_risk 的任意长度样本，可带 provenance/verified_at")
    parser.add_argument("--aggregate", type=Path, help="只重新汇总已有年龄记录，不查询网络")
    parser.add_argument("--require-fresh-references", type=int, default=0, help="要求至少 N 个 <30 天且有出处的正常对照；不足退出 2")
    args = parser.parse_args()
    if args.require_fresh_references < 0:
        parser.error("require-fresh-references 不能为负数")
    if args.aggregate:
        rows, source = load_samples(args.aggregate)
        result = {"source": source, "mode": "offline-aggregation", "summary": summarize_rows(rows), "rows": rows}
    else:
        if not args.db_path:
            parser.error("网络查询需 --db-path")
        result = asyncio.run(evaluate(args))
    count = result["summary"]["fresh_normal_controls"]["with_recorded_provenance"]
    result["fresh_reference_gate"] = {"required": args.require_fresh_references, "available": count, "passed": count >= args.require_fresh_references}
    output = Path(args.json_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "gate": result["fresh_reference_gate"]}, ensure_ascii=False))
    return 0 if result["fresh_reference_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
