"""引擎目录：后缀短码、SearXNG 引擎名、回退链与付费兜底路由。

这个模块是唯一的真源，``query_parser`` 的后缀表与 ``/api/engines`` 都从这里生成，
避免「解析表里有、上游配置里没有」这类漂移。

字段说明：

- ``engine``：产品侧引擎名，也是 ``meta.engines`` / ``parsed.engine`` 用的名字；
- ``searx_engine``：SearXNG 实际引擎名；大多数与 ``engine`` 相同，
  ``scholar`` 例外（SearXNG 叫 ``google scholar``）；
- ``fallbacks``：显式后缀主引擎失败后按顺序尝试的 SearXNG 引擎；
- ``paid``：SearXNG 全失败后是否允许商用接口兜底，``search`` / ``scholar`` / ``brave``。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSpec:
    code: str
    label: str
    engine: str
    searx_engine: str
    fallbacks: tuple[str, ...] = ()
    paid: str = ""
    aliases: tuple[str, ...] = ()
    note: str = ""


ENGINE_SPECS: tuple[EngineSpec, ...] = (
    EngineSpec(
        "g", "Google", "google", "google",
        fallbacks=("google cse",), paid="search",
        note="Google 直连常被 403；先回退 Google CSE，再按配置走 Serper",
    ),
    EngineSpec(
        "b", "Bing", "bing", "bing",
        note="SearXNG 用 cn.bing.com，避免 www.bing.com 的 302 被引擎丢弃",
    ),
    EngineSpec(
        "d", "DuckDuckGo", "duckduckgo", "duckduckgo",
        fallbacks=("duckduckgo web",), aliases=("ddg",),
        note="间歇 CAPTCHA；失败时试 duckduckgo web",
    ),
    EngineSpec("dw", "DuckDuckGo Web", "duckduckgo web", "duckduckgo web", note="DuckDuckGo 的网页端备用入口"),
    EngineSpec(
        "br", "Brave", "brave", "brave", paid="brave",
        note="无 key 时网页端常限流；配置 BRAVE_API_KEY 后走官方接口",
    ),
    EngineSpec("yt", "YouTube", "youtube", "youtube"),
    EngineSpec("gh", "GitHub", "github", "github"),
    EngineSpec("ar", "arXiv", "arxiv", "arxiv"),
    EngineSpec(
        "sc", "Google Scholar", "scholar", "google scholar", paid="scholar",
        note="网页端 access denied；配置 Serper 时走 /scholar",
    ),
    EngineSpec(
        "w", "Wikipedia", "wikipedia", "wikipedia",
        note="需 display_type 含 list；默认配置已补",
    ),
    EngineSpec(
        "gc", "Google CSE", "google cse", "google cse", paid="search",
        note="独立索引；偶发超时，失败时可按配置回退 Serper",
    ),
    EngineSpec(
        "sp", "Startpage", "startpage", "startpage",
        fallbacks=("mojeek",), note="PoW CAPTCHA；失败回退 Mojeek",
    ),
    EngineSpec("mj", "Mojeek", "mojeek", "mojeek", note="需 inactive: false 才会被 SearXNG 加载"),
    EngineSpec("y", "Yahoo", "yahoo", "yahoo"),
    EngineSpec(
        "sg", "Sogou", "sogou", "sogou",
        fallbacks=("360search",), note="部分查询会触发 SearXNG 侧 crash；失败回退 360 搜索",
    ),
    EngineSpec("so", "360 Search", "360search", "360search", note="中文独立索引；Sogou 的回退目标"),
    EngineSpec("n", "Naver", "naver", "naver"),
    EngineSpec("yd", "Yandex", "yandex", "yandex"),
    EngineSpec("sw", "Swisscows", "swisscows", "swisscows", note="需 inactive: false"),
)

# 产品侧后缀 → 引擎名（含别名）
ENGINE_SUFFIXES: dict[str, str] = {}
for _spec in ENGINE_SPECS:
    ENGINE_SUFFIXES[_spec.code] = _spec.engine
    for _alias in _spec.aliases:
        ENGINE_SUFFIXES[_alias] = _spec.engine

ENGINE_LABELS: dict[str, str] = {spec.engine: spec.label for spec in ENGINE_SPECS}
FALLBACKS: dict[str, tuple[str, ...]] = {
    spec.engine: spec.fallbacks for spec in ENGINE_SPECS if spec.fallbacks
}
PAID_ROUTES: dict[str, str] = {spec.engine: spec.paid for spec in ENGINE_SPECS if spec.paid}
SEARX_ENGINE_NAMES: dict[str, str] = {
    spec.engine: spec.searx_engine for spec in ENGINE_SPECS
}
SPEC_BY_ENGINE: dict[str, EngineSpec] = {spec.engine: spec for spec in ENGINE_SPECS}


def engine_candidates(engine: str) -> list[str]:
    """显式引擎的尝试顺序：主引擎 → 回退链（去重，保持顺序）。"""
    if not engine or engine == "default":
        return ["default"]
    ordered = [engine, *FALLBACKS.get(engine, ())]
    seen: set[str] = set()
    result: list[str] = []
    for name in ordered:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def searx_engine_name(engine: str) -> str:
    """产品侧引擎名 → SearXNG 引擎名。"""
    return SEARX_ENGINE_NAMES.get(engine, engine)


def label_for(engine: str) -> str:
    return ENGINE_LABELS.get(engine, engine)


def paid_route(engine: str) -> str:
    return PAID_ROUTES.get(engine, "")


def catalog_rows() -> list[dict]:
    """给 /api/engines 用的静态目录（不含健康状态）。"""
    rows = []
    for spec in ENGINE_SPECS:
        rows.append(
            {
                "code": spec.code,
                "label": spec.label,
                "engine": spec.engine,
                "searx_engine": spec.searx_engine,
                "fallbacks": list(spec.fallbacks),
                "paid": spec.paid,
                "aliases": list(spec.aliases),
                "note": spec.note,
            }
        )
    return rows
