"""聚合入口：按配置选择真实 SearXNG 或固定样本，返回已归一化结果。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import Settings, get_settings
from app.core.breaker import UPSTREAM_KEY, EngineHealthStore, engine_name
from app.core.errors import (
    EngineUnavailable,
    EnginesUnresponsive,
    SearchError,
    UpstreamUnavailable,
)
from app.core.fixture_provider import FixtureProvider
from app.core.paid import build_paid_search
from app.core.searxng import ENGINE_NAMES, SearxngClient
from app.schemas import Result


@dataclass
class Aggregated:
    results: list[Result]
    engines: list[str] = field(default_factory=list)
    unresponsive: list[str] = field(default_factory=list)
    provider: str = "searxng"
    ms: int = 0


class Aggregator:
    def __init__(self, settings: Settings, health: EngineHealthStore | None = None) -> None:
        self._settings = settings
        self._fixture = FixtureProvider()
        self._searxng = SearxngClient(settings)
        self._paid = build_paid_search(settings)
        self._health = health


    def _health_store(self) -> EngineHealthStore | None:
        if not self._settings.breaker_enabled:
            return None
        if self._health is None:
            from app.core.breaker import get_health_store

            self._health = get_health_store()
        return self._health

    @property
    def provider_name(self) -> str:
        return self._settings.provider

    @property
    def paid_provider(self) -> str:
        return self._paid.engine if self._paid is not None and self.provider_name == "searxng" else ""

    async def search(
        self,
        q: str,
        page: int = 1,
        region: str | None = None,
        safe: bool = True,
        engine: str = "default",
        fixture: str | None = None,
    ) -> Aggregated:
        started = time.perf_counter()
        health = self._health_store()
        provider = self._settings.provider
        paid_search = self._paid if provider == "searxng" and page == 1 and engine == "default" else None

        routed_engine = ENGINE_NAMES.get(engine, engine)
        if health is not None and routed_engine != "default" and health.is_open(routed_engine):
            minutes = health.remaining(routed_engine) // 60 + 1
            raise EngineUnavailable(
                f"引擎 {engine} 连续失败已熔断，约 {minutes} 分钟后重试；可移除后缀或更换引擎"
            )

        results: list[Result] = []
        engines: list[str] = []
        unresponsive: list[str] = []
        primary_error: SearchError | None = None
        if health is not None and health.is_open(UPSTREAM_KEY):
            minutes = health.remaining(UPSTREAM_KEY) // 60 + 1
            primary_error = UpstreamUnavailable(
                f"上游检索服务熔断中，约 {minutes} 分钟后自动恢复"
            )
        else:
            try:
                if provider == "fixture":
                    results, engines, unresponsive = self._fixture.search(
                        q, page, region, safe, engine=engine, fixture=fixture
                    )
                else:
                    results, engines, unresponsive = await self._searxng.search(
                        q, page, region, safe, engine=engine, fixture=fixture
                    )
            except EnginesUnresponsive as exc:
                primary_error = exc
                unresponsive = list(exc.engines)
                if health is not None:
                    for raw in exc.engines:
                        health.record_failure(engine_name(raw), raw)
            except SearchError as exc:
                primary_error = exc
                if health is not None:
                    health.record_failure(UPSTREAM_KEY, exc.message)
            else:
                if health is not None:
                    elapsed = int((time.perf_counter() - started) * 1000)
                    health.record_success(UPSTREAM_KEY, elapsed)
                    for name in engines:
                        health.record_success(name)
                    for raw in unresponsive:
                        health.record_failure(engine_name(raw), raw)

        if primary_error is not None:
            if paid_search is None:
                raise primary_error
            if not unresponsive:
                unresponsive.append(f"searxng({primary_error.code})")

        if paid_search is not None:
            paid_engine = paid_search.engine
            if health is not None and health.is_open(paid_engine):
                unresponsive.append(f"{paid_engine}(熔断冷却中)")
            else:
                paid = await paid_search.search(q, page, region)
                if paid.error:
                    unresponsive.append(f"{paid.engine}({paid.error})")
                    if health is not None:
                        health.record_failure(paid.engine, paid.error)
                else:
                    # 统一交给检索路由做 canonical 去重，保留重复 URL 的付费来源。
                    results.extend(paid.results)
                    if paid.results and paid.engine not in engines:
                        engines.append(paid.engine)
                    if health is not None:
                        health.record_success(paid.engine)

        if primary_error is not None and not results:
            raise primary_error

        return Aggregated(
            results=results,
            engines=engines,
            unresponsive=unresponsive,
            provider=provider,
            ms=int((time.perf_counter() - started) * 1000),
        )


@lru_cache(maxsize=1)
def get_aggregator() -> Aggregator:
    return Aggregator(get_settings())
