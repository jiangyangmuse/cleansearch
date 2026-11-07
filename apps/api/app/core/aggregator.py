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
from app.core.searxng import SearxngClient
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

        if health is not None:
            if engine and engine != "default" and health.is_open(engine):
                minutes = health.remaining(engine) // 60 + 1
                raise EngineUnavailable(
                    f"引擎 {engine} 连续失败已熔断，约 {minutes} 分钟后重试；可换一个引擎（去掉后缀或改 b / d / br）"
                )
            if health.is_open(UPSTREAM_KEY):
                minutes = health.remaining(UPSTREAM_KEY) // 60 + 1
                raise UpstreamUnavailable(
                    f"上游检索服务熔断中（连续失败），约 {minutes} 分钟后自动恢复"
                )

        try:
            if self._settings.provider == "fixture":
                results, engines, unresponsive = self._fixture.search(
                    q, page, region, safe, engine=engine, fixture=fixture
                )
                provider = "fixture"
            else:
                results, engines, unresponsive = await self._searxng.search(
                    q, page, region, safe, engine=engine, fixture=fixture
                )
                provider = "searxng"
        except EnginesUnresponsive as exc:
            # 实例是通的，只是引擎集体不给结果：只记引擎级，不锁整站
            if health is not None:
                for raw in exc.engines:
                    health.record_failure(engine_name(raw), raw)
            raise
        except SearchError as exc:
            if health is not None:
                health.record_failure(UPSTREAM_KEY, exc.message)
            raise

        if health is not None:
            elapsed = int((time.perf_counter() - started) * 1000)
            health.record_success(UPSTREAM_KEY, elapsed)
            # 先记成功（有结果），再记失败——同一个引擎被标 unresponsive 时以失败为准
            for name in engines:
                health.record_success(name)
            for raw in unresponsive:
                health.record_failure(engine_name(raw), raw)

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