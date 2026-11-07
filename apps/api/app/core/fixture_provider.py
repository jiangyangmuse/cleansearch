"""固定样本上游：不需要 Docker / SearXNG 也能跑通 M0 闭环与三态验收。

样本选择规则（优先级从高到低）：
1. 请求体 opts.fixture = hit | empty | error | risky
2. 查询以 "__empty" 开头 -> 零结果；"__fail" 开头 -> 上游不可用；"__risky" 开头 -> 含恶意/可疑链接的样本
3. 其余 -> hit 样本
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import UpstreamUnavailable
from app.core.normalize import format_unresponsive, normalise_result
from app.schemas import Result

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def _load(name: str) -> dict:
    path = FIXTURE_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # 样本缺失属于部署错误，直接抛出可见
        raise UpstreamUnavailable(f"固定样本缺失：{path}") from exc


class FixtureProvider:
    name = "fixture"

    def __init__(self) -> None:
        self._hit = _load("searxng_hit.json")
        self._empty = _load("searxng_empty.json")
        self._risky = _load("searxng_risky.json")

    @staticmethod
    def resolve_fixture(q: str, explicit: str | None) -> str:
        if explicit in ("hit", "empty", "error", "risky"):
            return explicit
        lowered = q.strip().lower()
        if lowered.startswith("__fail"):
            return "error"
        if lowered.startswith("__empty"):
            return "empty"
        if lowered.startswith("__risky"):
            return "risky"
        return "hit"

    def search(
        self,
        q: str,
        page: int,
        region: str | None,
        safe: bool,
        engine: str = "default",
        fixture: str | None = None,
    ) -> tuple[list[Result], list[str], list[str]]:
        kind = self.resolve_fixture(q, fixture)
        if kind == "error":
            raise UpstreamUnavailable("固定样本：上游 SearXNG 不可用（模拟连接失败）")
        if kind == "empty":
            payload = self._empty
        elif kind == "risky":
            payload = self._risky
        else:
            payload = self._hit
        if kind in ("hit", "risky") and page > 1:
            payload = self._empty  # 样本只有一页，翻页即零结果，行为可预期
        raw = payload.get("results") or []
        results: list[Result] = []
        for index, item in enumerate(raw, 1):
            parsed = normalise_result(item, index)
            if parsed is not None:
                results.append(parsed)
        engines = list(dict.fromkeys(engine for item in results for engine in item.engine))
        unresponsive = format_unresponsive(payload.get("unresponsive_engines"))
        return results, engines, unresponsive
