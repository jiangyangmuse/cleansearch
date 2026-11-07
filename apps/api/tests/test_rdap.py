"""RDAP 域名年龄：缓存、解析、风险加分。"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.core.rdap import DomainAgeStore, enrich, lookup
from app.core.fetch import SafeFetcher
from app.schemas import Result


def make_result(url: str, risk: float = 0.2) -> Result:
    return Result(
        id=url,
        url=url,
        display_url=url,
        title="t",
        snippet="s",
        engine=["google cse"],
        score=0.0,
        risk=risk,
        reasons=[],
        favicon=None,
        published=None,
        read_minutes=None,
    )


def test_store_hit_and_expiry(tmp_path) -> None:
    store = DomainAgeStore(tmp_path / "age.db", ttl_days=30)
    store.put("fresh.test", int(time.time()) - 86400 * 5)
    hit, registered = store.get("fresh.test")
    assert hit and registered is not None

    # 过期后视为未命中
    import sqlite3

    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE domain_age SET checked_at = ? WHERE domain = 'fresh.test'", (int(time.time()) - 86400 * 31,))
    assert store.get("fresh.test") == (False, None)
    store.close()


def test_legacy_future_timestamp_is_refetched(tmp_path) -> None:
    store = DomainAgeStore(tmp_path / "legacy.db")
    try:
        store.put("example.com", int(time.time()) + 86400)
        assert store.get("example.com") == (False, None)
    finally:
        store.close()


def test_lookup_parses_registration_and_negative_caches(tmp_path) -> None:
    calls = {"n": 0}
    registered = "2020-01-02T03:04:05Z"

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "missing-domain.com" in str(request.url):
            return httpx.Response(404, json={})
        return httpx.Response(
            200,
            json={"events": [{"eventAction": "registration", "eventDate": registered}]},
            headers={"content-type": "application/rdap+json"},
        )

    fetcher = SafeFetcher(timeout=1.0, transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "age.db")

    info = asyncio.run(lookup("old-domain.com", store, fetcher))
    assert info is not None and info.fresh is False and info.registered_at

    # 第二次直接命中缓存，不再请求
    before = calls["n"]
    asyncio.run(lookup("old-domain.com", store, fetcher))
    assert calls["n"] == before

    # 404 → 负缓存：第二次不再请求
    assert asyncio.run(lookup("missing-domain.com", store, fetcher)) is None
    before = calls["n"]
    assert asyncio.run(lookup("missing-domain.com", store, fetcher)) is None
    assert calls["n"] == before
    store.close()


def test_enrich_bumps_fresh_domain_risk(tmp_path) -> None:
    from datetime import datetime, timezone, timedelta

    recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat().replace("+00:00", "Z")

    def handler(request: httpx.Request) -> httpx.Response:
        if "fresh-domain.com" in str(request.url):
            return httpx.Response(
                200,
                json={"events": [{"eventAction": "registration", "eventDate": recent}]},
                headers={"content-type": "application/rdap+json"},
            )
        return httpx.Response(404, json={})

    fetcher = SafeFetcher(timeout=1.0, transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "age.db")
    items = [make_result("https://fresh-domain.com/a"), make_result("https://old-domain.com/b")]

    assert store.get("fresh-domain.com") == (False, None)
    bumped = asyncio.run(enrich(items, store, fetcher))

    assert bumped >= 1
    assert items[0].risk > 0.2
    assert any("新注册" in reason for reason in items[0].reasons)
    store.close()


async def test_batch_budget_includes_waiting_domains(tmp_path, monkeypatch) -> None:
    from app.core import rdap

    monkeypatch.setattr(rdap, "BUDGET_SECONDS", 0.03)
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.2)
        return httpx.Response(404)

    fetcher = SafeFetcher(timeout=1, transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "budget.db")
    try:
        await enrich([make_result(f"https://candidate{i}.com") for i in range(8)], store, fetcher)
        assert len(calls) == 4
    finally:
        store.close()


async def test_concurrent_searches_share_network_limit_and_release_on_timeout(tmp_path, monkeypatch) -> None:
    from app.core import rdap

    monkeypatch.setattr(rdap, "BUDGET_SECONDS", 0.08)
    active = peak = calls = 0
    slow = True

    async def handler(request):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            if slow:
                await asyncio.sleep(0.5)
            return httpx.Response(429)
        finally:
            active -= 1

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "concurrent.db")
    try:
        await asyncio.gather(*(
            enrich([make_result(f"https://request{batch}candidate{i}.com") for i in range(8)], store, fetcher)
            for batch in range(3)
        ))
        assert peak <= rdap.CONCURRENCY
        assert active == 0
        # 预算取消后不泄漏许可；429 不写负缓存，下一次仍能重试。
        slow = False
        before = calls
        assert await lookup("retry-after-budget.com", store, fetcher) is None
        assert await lookup("retry-after-budget.com", store, fetcher) is None
        assert calls == before + 2
    finally:
        store.close()


async def test_cached_age_does_not_queue_behind_other_searches(tmp_path, monkeypatch) -> None:
    from app.core import rdap

    monkeypatch.setattr(rdap, "BUDGET_SECONDS", 0.3)
    all_started = asyncio.Event()
    started = 0

    async def handler(request):
        nonlocal started
        started += 1
        if started == rdap.CONCURRENCY:
            all_started.set()
        await asyncio.sleep(1)
        return httpx.Response(404)

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "warm-priority.db")
    store.put("cached-reference.com", int(time.time()) - 5 * 86400)
    task = asyncio.create_task(enrich([make_result(f"https://slow{i}.com") for i in range(4)], store, fetcher))
    try:
        await asyncio.wait_for(all_started.wait(), timeout=1)
        warm = [make_result("https://cached-reference.com")]
        assert await asyncio.wait_for(enrich(warm, store, fetcher), timeout=0.1) == 1
        assert started == rdap.CONCURRENCY
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        store.close()


async def test_transient_failure_does_not_create_day_negative_cache(tmp_path) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "retry.db")
    try:
        assert await lookup("example.com", store, fetcher) is None
        assert await lookup("example.com", store, fetcher) is None
        assert len(calls) == 2
    finally:
        store.close()


async def test_subdomains_share_registered_domain_cache(tmp_path) -> None:
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"events": [{"eventAction": "registration", "eventDate": "2020-01-02T03:04:05Z"}]}, headers={"content-type": "application/rdap+json"})

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "domains.db")
    try:
        await lookup("a.example.co.uk", store, fetcher)
        await lookup("b.example.co.uk", store, fetcher)
        assert len(calls) == 1 and calls[0].endswith("/domain/example.co.uk")
    finally:
        store.close()


async def test_same_young_domain_does_not_add_risk_to_clean_result(tmp_path) -> None:
    store = DomainAgeStore(tmp_path / "clean-result.db")
    store.put("young-reference.com", int(time.time()) - 5 * 86400)
    items = [make_result("https://young-reference.com/signal", 0.25),
             make_result("https://young-reference.com/clean", 0.0)]
    try:
        assert await enrich(items, store, SafeFetcher(), cache_only=True) == 1
        assert items[0].risk == 0.4
        assert items[1].risk == 0 and items[1].reasons == []
    finally:
        store.close()


@pytest.mark.parametrize("payload", [[], {"events": [None]}, {"events": [{"eventAction": "registration", "eventDate": "2999-01-01T00:00:00Z"}]}])
async def test_invalid_registration_is_not_used(tmp_path, payload) -> None:
    fetcher = SafeFetcher(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload, headers={"content-type": "application/rdap+json"})), resolver=lambda host: ["93.184.216.34"])
    store = DomainAgeStore(tmp_path / "invalid.db")
    try:
        info = await lookup("example.com", store, fetcher)
        assert info is None or (info.registered_at is None and not info.fresh)
    finally:
        store.close()


def test_search_and_go_keep_domain_age_explanation(client, tmp_path, monkeypatch) -> None:
    from dataclasses import replace
    from html import unescape

    from app.config import get_settings
    from app.core.rdap import AGE_REASON
    from app.main import app
    from app.routers import go, search

    store = DomainAgeStore(tmp_path / "display.db")
    store.put("xn--80ak6aa92e.top", int(time.time()) - 5 * 86400)
    settings = replace(get_settings(), rdap_enabled=True)
    monkeypatch.setattr(search, "get_settings", lambda: settings)
    monkeypatch.setattr(go, "get_settings", lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, search.get_age_store, lambda: store)
    try:
        body = client.post("/api/search", json={"q": "账号验证", "opts": {"fixture": "risky"}}).json()
        item = next(item for group in body["groups"].values() for item in group if item["go_url"])
        assert AGE_REASON in item["reasons"] and item["risk"] == 0.5
        page = client.get(item["go_url"])
        assert page.status_code == 200 and AGE_REASON in unescape(page.text) and "0.50" in page.text
    finally:
        store.close()


async def test_unavailable_age_cache_does_not_break_lookup(tmp_path) -> None:
    store = DomainAgeStore(tmp_path / "closed.db")
    store.close()
    fetcher = SafeFetcher(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"events": [{"eventAction": "registration", "eventDate": "2020-01-02T03:04:05Z"}]},
        headers={"content-type": "application/rdap+json"},
    )), resolver=lambda host: ["93.184.216.34"])
    assert (await lookup("example.com", store, fetcher)).fresh is False


def test_fixture_age_enrichment_uses_cache_without_network(client, tmp_path, monkeypatch) -> None:
    from dataclasses import replace

    from app.config import get_settings
    from app.deps import get_fetcher
    from app.main import app
    from app.routers import search

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    store = DomainAgeStore(tmp_path / "offline.db")
    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    settings = replace(get_settings(), rdap_enabled=True)
    monkeypatch.setattr(search, "get_settings", lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, search.get_age_store, lambda: store)
    monkeypatch.setitem(app.dependency_overrides, get_fetcher, lambda: fetcher)
    try:
        response = client.post("/api/search", json={"q": "账号验证", "opts": {"fixture": "risky"}})
        assert response.status_code == 200 and not calls
    finally:
        store.close()
