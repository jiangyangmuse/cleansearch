"""查询解析器：后缀 > bang > 默认，带中文输入场景的护栏。

规则来源：构建方案 §7.1。M1 只做路由，不做同义词扩展（留下轮）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.core.engine_catalog import ENGINE_SUFFIXES

REGION_SUFFIXES: dict[str, str] = {
    "zh": "cn",
    "cn": "cn",
    "jp": "jp",
    "us": "us",
    "en": "en",
}

MIN_BASE_LEN = 2

_BANG_RE = re.compile(r"\s*!([A-Za-z]{1,3})$")
_SUFFIX_RE = re.compile(r"\s+([A-Za-z]{1,3})$")
_SINGLE_TOKEN_RE = re.compile(r"^[A-Za-z0-9]$")


@dataclass(frozen=True)
class Parsed:
    q: str
    engine: str = "default"
    region: str | None = None
    router: str = "default"


def _has_unbalanced_quotes(text: str) -> bool:
    return text.count('"') % 2 == 1


def _base_ok(base: str) -> bool:
    """护栏：短码前必须有真实查询内容。

    - 空、单字符（中英文数字）一律不认短码，C g / 1 g / x g 保持普通查询；
    - 单独成词的 ASCII 字母或数字同理，避免把型号、代号当引擎。
    """
    if len(base) < MIN_BASE_LEN:
        return False
    if _SINGLE_TOKEN_RE.match(base) and base.isascii():
        return False
    return True


def _resolve(code: str) -> tuple[str, str | None, bool] | None:
    """返回 (engine, region, is_engine)；未知短码返回 None。"""
    lowered = code.lower()
    if lowered in ENGINE_SUFFIXES:
        return ENGINE_SUFFIXES[lowered], None, True
    if lowered in REGION_SUFFIXES:
        return "default", REGION_SUFFIXES[lowered], False
    return None


def parse_query(raw: str) -> Parsed:
    q = unicodedata.normalize("NFKC", raw or "").strip()
    if not q:
        return Parsed(q="")
    if _has_unbalanced_quotes(q):
        return Parsed(q=q)

    bang = _BANG_RE.search(q)
    if bang:
        target = _resolve(bang.group(1))
        base = q[: bang.start()].strip()
        if target and _base_ok(base):
            engine, region, _ = target
            return Parsed(q=base, engine=engine, region=region, router="bang")

    suffix = _SUFFIX_RE.search(q)
    if suffix:
        target = _resolve(suffix.group(1))
        base = q[: suffix.start()].strip()
        if target and _base_ok(base):
            engine, region, _ = target
            return Parsed(q=base, engine=engine, region=region, router="suffix")

    return Parsed(q=q)


def describe(parsed: Parsed) -> str:
    """给日志和测试用的短描述。"""
    if parsed.router == "default":
        return "默认聚合"
    parts = [parsed.router]
    if parsed.engine != "default":
        parts.append(parsed.engine)
    if parsed.region:
        parts.append("region=" + parsed.region)
    return " ".join(parts)
