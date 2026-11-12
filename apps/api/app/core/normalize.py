"""URL 规范化、展示串、结果去重。M1 会在此基础上加 simhash 近重复判定。"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.schemas import Result
from app.core.result_category import result_category

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_cid", "utm_reader",
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid",
    "spm", "scm", "from", "ref", "ref_src", "referrer", "share_source",
    "_hsenc", "_hsmi", "mkt_tok", "si", "s_cid",
}


ALLOWED_SCHEMES = ("http", "https")
MAX_URL_LEN = 2048
AMBIGUOUS_URL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f\\]")


def is_renderable_url(url: str) -> bool:
    """只放行具有明确主机、无凭证的 HTTP(S) 结果链接。"""
    if not isinstance(url, str):
        return False
    candidate = url.strip()
    if not candidate or len(candidate) > MAX_URL_LEN:
        return False
    if AMBIGUOUS_URL_CHARACTERS.search(candidate):
        return False
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        _ = parts.port  # 非法端口在这里抛 ValueError
    except ValueError:
        return False
    if parts.scheme.lower() not in ALLOWED_SCHEMES or parts.username is not None:
        return False
    if not host or host.startswith(".") or host.endswith("."):
        return False
    if any(ch.isspace() or ch in "%<>^|" for ch in host):
        return False
    return True


def canonical_url(url: str) -> str:
    """去掉跟踪参数、锚点与 URL 内嵌凭证，统一大小写与末尾斜杠，作为去重键。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        netloc = parts.netloc.lower()
        if parts.username is not None or parts.password is not None:
            host = parts.hostname or ""
            netloc = f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return ""
    scheme = (parts.scheme or "https").lower()
    path = parts.path.rstrip("/") or "/"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def display_url(url: str) -> str:
    """面包屑式展示：example.com › path › page。"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.netloc.lower() or url
    segments = [seg for seg in parts.path.split("/") if seg]
    tail = " › ".join(segments[-2:])
    return f"{host} › {tail}" if tail else host


def favicon_for(url: str) -> str | None:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return None
    if not host:
        return None
    return f"https://{host}/favicon.ico"


def format_unresponsive(raw: object) -> list[str]:
    """SearXNG 的 unresponsive_engines 是 ["google", "timeout"] 这样的二元组列表。"""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            parts = [str(p) for p in item if p not in (None, "")]
            if not parts:
                continue
            out.append(parts[0] + (f"({', '.join(parts[1:])})" if len(parts) > 1 else ""))
        else:
            out.append(str(item))
    return out


def _as_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalise_result(raw: dict, index: int) -> Result | None:
    url = _as_str(raw.get("url"))
    title = _as_str(raw.get("title"))
    if not is_renderable_url(url) or not title:
        return None
    engine = raw.get("engine")
    engines = raw.get("engines")
    engine_list: list[str] = []
    if isinstance(engines, list):
        engine_list = [str(e) for e in engines if e]
    if not engine_list and isinstance(engine, str) and engine:
        engine_list = [engine]
    score = raw.get("score")
    try:
        score_value = float(score)
    except (TypeError, ValueError, OverflowError):
        score_value = 0.0
    published = _as_str(raw.get("publishedDate") or raw.get("published")) or None
    return Result(
        id=f"r_{index}",
        url=url,
        display_url=display_url(url),
        title=title,
        snippet=_as_str(raw.get("content") or raw.get("snippet")),
        engine=engine_list,
        score=max(0.0, min(score_value, 1.0)),
        reasons=[f"来源 {engine_list[0]}" if engine_list else "来源未知"],
        favicon=favicon_for(url),
        published=published,
        category=result_category(url, title),
    )


def dedupe_results(results: list[Result]) -> tuple[list[Result], int]:
    """按 canonical URL 去重，保留首次出现（上游按相关度排序），合并引擎列表。"""
    seen: dict[str, Result] = {}
    removed = 0
    for item in results:
        key = canonical_url(item.url)
        if not key:
            removed += 1
            continue
        kept = seen.get(key)
        if kept is None:
            seen[key] = item
            item.reasons = list(item.reasons)
            continue
        removed += 1
        for engine in item.engine:
            if engine not in kept.engine:
                kept.engine.append(engine)
        if len(kept.engine) > 1:
            kept.reasons = [f"来源 {len(kept.engine)} 个引擎" if len(kept.engine) >= 2 else kept.reasons[0]]
    ordered = list(seen.values())
    for i, item in enumerate(ordered, 1):
        item.id = f"r_{i}"
    return ordered, removed


_HASH_CJK = re.compile(r"[\u4e00-\u9fff]+")
_HASH_LATIN = re.compile(r"[a-z0-9]+")


def title_fingerprint_tokens(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens = _HASH_LATIN.findall(lowered)
    for run in _HASH_CJK.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def _hash64(token: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
    )


def title_simhash(text: str, bits: int = 64) -> int | None:
    """64 位 simhash：同稿标题汉明距离 <= 3 判为近似重复。"""
    tokens = title_fingerprint_tokens(text)
    if not tokens:
        return None
    vector = [0] * bits
    for token in tokens:
        value = _hash64(token)
        for index in range(bits):
            vector[index] += 1 if (value >> index) & 1 else -1
    fingerprint = 0
    for index in range(bits):
        if vector[index] > 0:
            fingerprint |= 1 << index
    return fingerprint


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


_LANDING_LOCALE = re.compile(r"[a-z]{2}(?:-[a-z]{2})?", re.IGNORECASE)
_LANDING_INDEX = {"index.html", "index.htm", "index.php"}
MIN_TITLE_DEDUPE_TOKENS = 4


def _landing_page(url: str) -> bool:
    """A home or language entry is a distinct destination, not a syndicated article."""
    try:
        path = urlsplit(url).path.strip("/").lower()
    except ValueError:
        return False
    return not path or path in _LANDING_INDEX or bool(_LANDING_LOCALE.fullmatch(path))


def dedupe_similar_titles(
    results: list[Result], max_distance: int = 3
) -> tuple[list[Result], int]:
    """仅对信息量足够的非入口页做标题近重复合并。

    品牌短标题无法证明页面相同，首页/语言首页也不应被同名文章吞掉。
    相同 URL 已由 dedupe_results 合并，不在这里猜测不同地址是否等价。
    """
    kept: list[Result] = []
    fingerprints: list[tuple[int, Result]] = []
    removed = 0
    for item in results:
        if _landing_page(item.url) or len(set(title_fingerprint_tokens(item.title))) < MIN_TITLE_DEDUPE_TOKENS:
            kept.append(item)
            continue
        fingerprint = title_simhash(item.title)
        if fingerprint is None:
            kept.append(item)
            continue
        for existing, target in fingerprints:
            if hamming(fingerprint, existing) <= max_distance:
                for engine in item.engine:
                    if engine not in target.engine:
                        target.engine.append(engine)
                removed += 1
                break
        else:
            kept.append(item)
            fingerprints.append((fingerprint, item))
    return kept, removed
