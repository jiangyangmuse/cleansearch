"""聚合入口：按配置选择真实 SearXNG 或固定样本，返回已归一化结果。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import Settings, get_settings
from app.core.breaker import UPSTREAM_KEY, EngineHealthStore, engine_name
from app.core.engine_catalog import ENGINE_SPECS, engine_candidates, searx_engine_name
from app.core.engine_preferences import NoSelectedEngines
from app.core.errors import (
    EngineUnavailable,
    EnginesUnresponsive,
    SearchError,
    UpstreamUnavailable,
)
from app.core.fixture_provider import FixtureProvider
from app.core.paid import build_paid_search
from app.core.searxng import SearxngClient, restrict_results
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

    @property
    def paid_capabilities(self) -> str:
        return ",".join(self._paid.engines) if self._paid is not None and self.provider_name == "searxng" else ""

    async def configured_engines(self) -> dict[str, bool]:
        if self.provider_name == "fixture":
            return {spec.searx_engine: spec.code in {"b", "g", "d", "br"} for spec in ENGINE_SPECS}
        return await self._searxng.configured_engines()

    async def search(
        self,
        q: str,
        page: int = 1,
        region: str | None = None,
        safe: bool = True,
        engine: str = "default",
        fixture: str | None = None,
        allow_paid: bool = True,
        selected_engines: tuple[str, ...] | None = None,
        time_range: str | None = None,
        language: str | None = None,
        site: str | None = None,
    ) -> Aggregated:
        started = time.perf_counter()
        health = self._health_store()
        provider = self._settings.provider
        # 现有商用客户端不支持时间和语言，避免把未筛选的付费结果混进来。
        allow_paid = allow_paid and not (time_range or language)
        if selected_engines == ():
            raise NoSelectedEngines("默认搜索引擎已全部关闭，请在设置中开启引擎或使用指定引擎的后缀")

        # 显式引擎：主引擎失败时按目录里的回退链继续，最后才考虑商用接口。
        # fixture 模式保持单次调用，测试与自检不接真实上游。
        if provider == "searxng" and engine != "default":
            return await self._search_explicit(
                q=q,
                page=page,
                region=region,
                safe=safe,
                engine=engine,
                fixture=fixture,
                started=started,
                health=health,
                time_range=time_range,
                language=language,
                site=site,
                allow_paid=allow_paid,
            )

        paid_search = self._paid if (
            allow_paid and selected_engines is None and provider == "searxng" and page == 1 and engine == "default"
        ) else None

        routed_engine = searx_engine_name(engine)
        if health is not None and engine != "default" and health.is_open(routed_engine):
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
                    if selected_engines is not None:
                        results, engines = restrict_results(results, selected_engines)
                else:
                    selection = {} if selected_engines is None else {"selected_engines": selected_engines}
                    results, engines, unresponsive = await self._searxng.search(
                        q, page, region, safe, engine=engine, fixture=fixture,
                        time_range=time_range, language=language, site=site, **selection
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

        # 免费请求成功（包括合法空态/部分引擎失败）不补付费结果。
        if paid_search is not None and primary_error is not None:
            paid_engine = paid_search.engine
            if health is not None and health.is_open(paid_engine):
                unresponsive.append(f"{paid_engine}(熔断冷却中)")
            else:
                paid = await paid_search.search(f"{q} site:{site}" if site else q, page, region)
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

    async def _search_explicit(
        self,
        *,
        q: str,
        page: int,
        region: str | None,
        safe: bool,
        engine: str,
        fixture: str | None,
        started: float,
        health: EngineHealthStore | None,
        time_range: str | None = None,
        language: str | None = None,
        site: str | None = None,
        allow_paid: bool = True,
    ) -> Aggregated:
        """显式引擎：主引擎 → 回退链 → 商用接口，任一成功即返回。"""
        candidates = engine_candidates(engine)
        results: list[Result] = []
        engines: list[str] = []
        unresponsive: list[str] = []
        attempted: list[str] = []
        last_error: SearchError | None = None
        upstream_error: SearchError | None = None

        if health is not None and health.is_open(UPSTREAM_KEY):
            minutes = health.remaining(UPSTREAM_KEY) // 60 + 1
            upstream_error = UpstreamUnavailable(f"上游检索服务熔断中，约 {minutes} 分钟后自动恢复")
            unresponsive.append("searxng(熔断冷却中)")
            candidates = []

        for candidate in candidates:
            routed = searx_engine_name(candidate)
            if health is not None and health.is_open(routed):
                minutes = health.remaining(routed) // 60 + 1
                unresponsive.append(f"{routed}(熔断冷却，约 {minutes} 分钟)")
                continue

            attempted.append(candidate)
            try:
                results, engines, extra = await self._searxng.search(
                    q, page, region, safe, engine=candidate, fixture=fixture,
                    time_range=time_range, language=language, site=site,
                )
            except EnginesUnresponsive as exc:
                last_error = exc
                failures = exc.engines or [f"{routed}({exc.code})"]
                unresponsive.extend(failures)
                if health is not None:
                    # 实例已正常响应，故障只属于数据面引擎。
                    health.record_success(UPSTREAM_KEY)
                    for raw in dict.fromkeys(failures):
                        health.record_failure(engine_name(raw), raw)
                continue
            except SearchError as exc:
                last_error = exc
                unresponsive.append(f"searxng({exc.code})")
                upstream_error = exc
                if health is not None:
                    health.record_failure(UPSTREAM_KEY, exc.message)
                # 所有免费候选都走同一实例；实例失败后不要重复等待同一故障。
                break

            if health is not None:
                health.record_success(UPSTREAM_KEY, int((time.perf_counter() - started) * 1000))
                health.record_success(routed)
                for raw in dict.fromkeys(extra):
                    health.record_failure(engine_name(raw), raw)
            unresponsive.extend(extra)
            # 合法零结果也是成功：不触发回退、不消耗付费额度、不累计故障。
            return Aggregated(
                results=results,
                engines=engines or ([routed] if results else []),
                unresponsive=unresponsive,
                provider="searxng",
                ms=int((time.perf_counter() - started) * 1000),
            )

        # 商用兜底只补「显式引擎」这一路，且每个引擎有独立路由；
        # 没有可用 key / 不是该引擎对应的接口时直接跳过。
        paid_provider = self._paid.provider_for_engine(engine) if allow_paid and self._paid is not None and page == 1 else ""
        if paid_provider and health is not None and health.is_open(paid_provider):
            unresponsive.append(f"{paid_provider}(熔断冷却中)")
        elif paid_provider:
            paid = await self._paid.search_for_engine(engine, f"{q} site:{site}" if site else q, page, region)
            if paid is not None:
                if paid.error:
                    unresponsive.append(f"{paid.engine}({paid.error})")
                    if health is not None:
                        health.record_failure(paid.engine, paid.error)
                else:
                    if health is not None:
                        health.record_success(paid.engine)
                    return Aggregated(
                        results=paid.results,
                        engines=[paid.engine] if paid.results else [],
                        unresponsive=unresponsive,
                        provider="searxng",
                        ms=int((time.perf_counter() - started) * 1000),
                    )

        if upstream_error is not None:
            raise upstream_error

        minutes_note = f"已尝试 {', '.join(attempted)}" if attempted else "没有可尝试的引擎"
        detail = "；".join(unresponsive[:6])
        message = f"引擎 {engine} 没有可用结果（{minutes_note}）"
        if detail:
            message += f"：{detail}"
        if last_error is not None and not unresponsive:
            message += f"：{last_error.message}"
        raise EngineUnavailable(message, engines=unresponsive)


@lru_cache(maxsize=1)
def get_aggregator() -> Aggregator:
    return Aggregator(get_settings())
