"""显式引擎回退链与定向付费兜底的契约测试。"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from app.config import get_settings
from app.core import aggregator as aggregator_module
from app.core.breaker import EngineHealthStore, UPSTREAM_KEY
from app.core.errors import EngineUnavailable, UpstreamUnavailable
from app.core.paid import PaidResult
from app.schemas import Result


def _result(url: str, engine: str) -> Result:
    return Result(id=url, url=url, display_url=url, title=url, engine=[engine])


class FakeSearxng:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def search(self, q, page, region, safe, engine="default", fixture=None):
        self.calls.append(engine)
        outcome = self.responses.get(engine)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            return [], [], []
        results, engines = outcome  # type: ignore[misc]
        return results, engines, []


class FakePaid:
    def __init__(self, result: PaidResult | None) -> None:
        self.result = result
        self.calls: list[str] = []

    def provider_for_engine(self, engine):
        return self.result.engine if self.result is not None else ""

    async def search_for_engine(self, engine, q, page=1, region=None):
        self.calls.append(engine)
        return self.result


def _settings():
    return replace(get_settings(), provider="searxng", breaker_enabled=False)


def test_primary_failure_falls_back_to_google_cse() -> None:
    aggregator = aggregator_module.Aggregator(_settings())
    aggregator._searxng = FakeSearxng(
        {
            "google": EngineUnavailable("blocked"),
            "google cse": ([_result("https://example.com/a", "google cse")], ["google cse"]),
        }
    )

    result = asyncio.run(aggregator.search("python", engine="google"))

    assert [item.url for item in result.results] == ["https://example.com/a"]
    assert result.engines == ["google cse"]
    assert any("google" in item for item in result.unresponsive)


def test_all_searxng_candidates_fail_then_paid_succeeds() -> None:
    aggregator = aggregator_module.Aggregator(_settings())
    aggregator._searxng = FakeSearxng(
        {
            "google": EngineUnavailable("blocked"),
            "google cse": EngineUnavailable("timeout"),
        }
    )
    paid = FakePaid(PaidResult([_result("https://paid.test/a", "serper")], "serper"))
    aggregator._paid = paid

    result = asyncio.run(aggregator.search("python", engine="google"))

    assert paid.calls == ["google"]
    assert [item.url for item in result.results] == ["https://paid.test/a"]
    assert result.engines == ["serper"]


def test_all_candidates_fail_without_paid_returns_engine_unavailable() -> None:
    aggregator = aggregator_module.Aggregator(_settings())
    aggregator._searxng = FakeSearxng(
        {
            "google": EngineUnavailable("blocked"),
            "google cse": EngineUnavailable("timeout"),
        }
    )
    aggregator._paid = None

    with pytest.raises(EngineUnavailable) as caught:
        asyncio.run(aggregator.search("python", engine="google"))
    assert "google" in caught.value.message and "google cse" in caught.value.message


def test_empty_results_are_an_empty_state_not_an_engine_error() -> None:
    aggregator = aggregator_module.Aggregator(_settings())
    aggregator._searxng = FakeSearxng({"bing": ([], [])})
    aggregator._paid = FakePaid(PaidResult([], "serper"))

    result = asyncio.run(aggregator.search("python", engine="bing"))

    assert result.results == [] and result.engines == []


@pytest.fixture
def health(tmp_path):
    store = EngineHealthStore(tmp_path / "health.db", fail_threshold=2, cooldown=60)
    yield store
    store.close()


def _with_health(health):
    return aggregator_module.Aggregator(replace(_settings(), breaker_enabled=True), health=health)


def _blocked_google():
    return FakeSearxng({name: EngineUnavailable("blocked") for name in ("google", "google cse")})


def test_normal_empty_does_not_fallback_spend_or_trip_circuit(health) -> None:
    aggregator = _with_health(health)
    aggregator._searxng = FakeSearxng({"google": ([], [])})
    paid = FakePaid(PaidResult([_result("https://paid.test/a", "serper")], "serper"))
    aggregator._paid = paid
    for _ in range(3):
        result = asyncio.run(aggregator.search("unmatched query", engine="google"))
        assert result.results == [] and result.unresponsive == []
    assert aggregator._searxng.calls == ["google"] * 3
    assert paid.calls == []
    assert health.row("google").fails == 0 and health.row("google").last_ok


@pytest.mark.parametrize("page", [2, 3])
def test_explicit_later_pages_never_spend_paid(page) -> None:
    aggregator = aggregator_module.Aggregator(_settings())
    aggregator._searxng = _blocked_google()
    paid = FakePaid(PaidResult([_result("https://paid.test/a", "serper")], "serper"))
    aggregator._paid = paid
    with pytest.raises(EngineUnavailable):
        asyncio.run(aggregator.search("python", page=page, engine="google"))
    assert paid.calls == []


def test_explicit_paid_failure_counted_once_and_cooldown_respected(health) -> None:
    aggregator = _with_health(health)
    aggregator._searxng = _blocked_google()
    paid = FakePaid(PaidResult([], "serper", "HTTP 429"))
    aggregator._paid = paid
    for _ in range(3):
        with pytest.raises(EngineUnavailable):
            asyncio.run(aggregator.search("python", engine="google"))
    assert paid.calls == ["google"] * 2
    assert health.row("serper").fails == 2


def test_paid_empty_is_successful_empty_state(health) -> None:
    aggregator = _with_health(health)
    aggregator._searxng = _blocked_google()
    aggregator._paid = FakePaid(PaidResult([], "serper"))
    result = asyncio.run(aggregator.search("python", engine="google"))
    assert result.results == [] and health.row("serper").last_ok


def test_instance_failure_is_not_repeated_for_each_candidate(health) -> None:
    aggregator = _with_health(health)
    aggregator._searxng = FakeSearxng({"google": UpstreamUnavailable("offline")})
    aggregator._paid = None
    with pytest.raises(UpstreamUnavailable) as caught:
        asyncio.run(aggregator.search("python", engine="google"))
    assert type(caught.value) is UpstreamUnavailable
    assert aggregator._searxng.calls == ["google"]
    assert health.row(UPSTREAM_KEY).fails == 1
    assert health.row("google").fails == 0


def test_open_instance_skips_free_chain_but_can_use_matching_paid(health) -> None:
    health.record_failure(UPSTREAM_KEY, "offline")
    health.record_failure(UPSTREAM_KEY, "offline")
    aggregator = _with_health(health)
    aggregator._searxng = FakeSearxng({})
    aggregator._paid = FakePaid(PaidResult([_result("https://paid.test/a", "serper")], "serper"))
    result = asyncio.run(aggregator.search("python", engine="google"))
    assert result.engines == ["serper"]
    assert aggregator._searxng.calls == []
    assert health.row(UPSTREAM_KEY).fails == 2


def test_explicit_success_clears_instance_failure_streak(health) -> None:
    health.record_failure(UPSTREAM_KEY, "offline")
    aggregator = _with_health(health)
    aggregator._searxng = FakeSearxng({"bing": ([_result("https://example.com", "bing")], ["bing"])})
    asyncio.run(aggregator.search("python", engine="bing"))
    assert health.row(UPSTREAM_KEY).fails == 0


def test_primary_cooldown_still_uses_free_fallback(health) -> None:
    health.record_failure("google", "blocked")
    health.record_failure("google", "blocked")
    aggregator = _with_health(health)
    aggregator._searxng = FakeSearxng({"google cse": ([_result("https://example.com", "google cse")], ["google cse"])})
    result = asyncio.run(aggregator.search("python", engine="google"))
    assert result.engines == ["google cse"]
    assert aggregator._searxng.calls == ["google cse"]
