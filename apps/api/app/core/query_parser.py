"""查询解析器：后缀 > bang > 默认，带中文输入场景的护栏。

规则来源：构建方案 §7.1。M1 只做路由，不做同义词扩展（留下轮）。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
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

_BANG_RE = re.compile(r"\s*!([A-Za-z][A-Za-z0-9]{0,7})$")
_SUFFIX_RE = re.compile(r"\s+([A-Za-z][A-Za-z0-9]{0,7})$")
_SINGLE_TOKEN_RE = re.compile(r"^[A-Za-z0-9]$")


@dataclass(frozen=True)
class Parsed:
    q: str
    engine: str = "default"
    region: str | None = None
    router: str = "default"
    custom_code: str | None = None


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
    if lowered == "ds":
        return "default", None, False
    if lowered in ENGINE_SUFFIXES:
        return ENGINE_SUFFIXES[lowered], None, True
    if lowered in REGION_SUFFIXES:
        return "default", REGION_SUFFIXES[lowered], False
    return None


def parse_query(raw: str, *, literal: bool = False, custom_codes: Collection[str] = ()) -> Parsed:
    q = unicodedata.normalize("NFKC", raw or "").strip()
    if literal or not q or _has_unbalanced_quotes(q):
        return Parsed(q=q)

    for router, pattern in (("bang", _BANG_RE), ("suffix", _SUFFIX_RE)):
        match = pattern.search(q)
        if match is None:
            continue
        base = q[:match.start()].strip()
        if not _base_ok(base):
            continue
        code = match.group(1).lower()
        target = _resolve(code)
        if target:
            engine, region, _ = target
            return Parsed(q=base, engine=engine, region=region, router=router)
        if code in custom_codes:
            return Parsed(q=base, router=router, custom_code=code)
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
