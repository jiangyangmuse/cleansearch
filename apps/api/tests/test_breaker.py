"""引擎健康与熔断。"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.aggregator import Aggregator
from app.core.breaker import UPSTREAM_KEY, EngineHealthStore, engine_name
from app.core.errors import EngineUnavailable, UpstreamUnavailable


@pytest.fixture()
def store(tmp_path) -> EngineHealthStore:
    instance = EngineHealthStore(tmp_path / "health.db", fail_threshold=3, cooldown=60)
    yield instance
    instance.close()


def test_engine_name_strips_reason() -> None:
    assert engine_name("google(timeout)") == "google"
    assert engine_name("bing") == "bing"


def test_failures_open_after_threshold(store: EngineHealthStore) -> None:
    assert not store.is_open("google")
    store.record_failure("google", "timeout")
    store.record_failure("google", "timeout")
    assert not store.is_open("google")
    row = store.record_failure("google", "CAPTCHA")
    assert row.open and row.fails == 3
    assert store.remaining("google") > 0


def test_success_resets_state(store: EngineHealthStore) -> None:
    for _ in range(3):
        store.record_failure("bing", "boom")
    assert store.is_open("bing")
    store.record_success("bing", 120)
    row = store.row("bing")
    assert not row.open and row.fails == 0 and row.last_ok is not None
    assert row.avg_ms == 120


def test_cooldown_expires(store: EngineHealthStore, monkeypatch) -> None:
    for _ in range(3):
        store.record_failure("brave", "boom")
    assert store.is_open("brave")
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 61)
    assert not store.is_open("brave")


def test_snapshot_lists_engines(store: EngineHealthStore) -> None:
    store.record_failure("google", "x")
    rows = store.snapshot()
    assert rows[0]["engine"] == "google" and rows[0]["fails"] == 1


async def test_aggregator_records_health(store: EngineHealthStore) -> None:
    settings = replace(get_settings(), provider="fixture", breaker_enabled=True)
    aggregator = Aggregator(settings, health=store)
    outcome = await aggregator.search("python 文档")
    assert outcome.results
    assert store.row(UPSTREAM_KEY).last_ok is not None
    assert store.row("google").fails == 0


async def test_explicit_open_engine_is_rejected(store: EngineHealthStore) -> None:
    for _ in range(3):
        store.record_failure("google", "CAPTCHA")
    settings = replace(get_settings(), provider="fixture", breaker_enabled=True)
    aggregator = Aggregator(settings, health=store)
    with pytest.raises(EngineUnavailable) as excinfo:
        await aggregator.search("python 文档", engine="google")
    assert "熔断" in excinfo.value.message


async def test_all_engines_unresponsive_does_not_open_upstream(store: EngineHealthStore) -> None:
    """SearXNG 可达但引擎全 CAPTCHA：只记引擎失败，不锁整站。"""
    import httpx

    from app.core.searxng import SearxngClient

    payload = {"results": [], "unresponsive_engines": [["duckduckgo", "CAPTCHA"]]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    settings = replace(
        get_settings(),
        provider="searxng",
        searxng_url="http://upstream.test",
        breaker_enabled=True,
    )
    aggregator = Aggregator(settings, health=store)
    aggregator._searxng = SearxngClient(settings, transport=httpx.MockTransport(handler))

    for _ in range(3):
        with pytest.raises(Exception):
            await aggregator.search("anything")

    assert not store.is_open(UPSTREAM_KEY)
    assert store.row("duckduckgo").fails >= 3


async def test_open_upstream_short_circuits(store: EngineHealthStore) -> None:
    for _ in range(3):
        store.record_failure(UPSTREAM_KEY, "connect refused")
    settings = replace(get_settings(), provider="fixture", breaker_enabled=True)
    aggregator = Aggregator(settings, health=store)
    with pytest.raises(UpstreamUnavailable) as excinfo:
        await aggregator.search("python 文档")
    assert "熔断" in excinfo.value.message


def test_engine_breaker_endpoint(client: TestClient, store: EngineHealthStore) -> None:
    from app.core.aggregator import get_aggregator
    from app.main import app

    for _ in range(3):
        store.record_failure("google", "CAPTCHA")
    settings = replace(get_settings(), provider="fixture", breaker_enabled=True)
    app.dependency_overrides[get_aggregator] = lambda: Aggregator(settings, health=store)
    try:
        response = client.post("/api/search", json={"q": "python 文档 g"})
    finally:
        app.dependency_overrides.pop(get_aggregator, None)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENGINE_UNAVAILABLE"
