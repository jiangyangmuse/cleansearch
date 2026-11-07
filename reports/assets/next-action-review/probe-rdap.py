"""Controlled three-request RDAP load probe; never calls a real registry."""
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api"))
import httpx
from app.core.fetch import SafeFetcher
from app.core.rdap import BUDGET_SECONDS, CONCURRENCY, DomainAgeStore, enrich
from app.schemas import Result

async def main():
    active = peak = calls = 0
    async def handler(request):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(10)
            return httpx.Response(429)
        finally:
            active -= 1
    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(ROOT / "data/next-review-load.db")
    async def batch(n):
        items = [Result(id=f"{n}-{i}",url=f"https://request{n}domain{i}.com",display_url="synthetic",
                        title="controlled",snippet="synthetic",engine=["test"],score=0,risk=0.2,reasons=[])
                 for i in range(8)]
        started = time.perf_counter()
        await enrich(items, store, fetcher)
        return round((time.perf_counter() - started) * 1000)
    try:
        durations = await asyncio.gather(*(batch(n) for n in range(3)))
        result = {"transport":"httpx.MockTransport; no real RDAP network", "requests":3,"domains_per_request":8,
                  "configured_concurrency": CONCURRENCY, "batch_budget_seconds": BUDGET_SECONDS,
                  "peak_network_concurrency":peak,"network_calls_started":calls,"active_after_completion":active,
                  "request_ms":durations,"global_across_workers":False}
        (Path(__file__).parent / "rdap-concurrency.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result))
        assert peak <= CONCURRENCY and active == 0
    finally:
        store.close()

asyncio.run(main())
