"""相关性打分与三档分组（M1：不含向量语义分）。

与构建方案 §7.5 的差异（已记入 docs/决策与接口变更.md）：
- 去掉 0.30 的向量语义分（M1 不接 bge-m3），权重按比例补到词法 / 共识 / 权威 / 时效；
- 不做 minmax 归一，改用绝对分 + 固定阈值，否则「全弱结果」集合也会被拉出 1.0 的强相关；
- 词法 BM25 用饱和函数映射到 [0,1)，避免长文档天然占优。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timezone

from app.schemas import Result

# 构建方案把 0.30 给了向量语义分；M1 还没接 bge-m3，把这部分按比例分给
# 词法与共识（可解释、可回归），权威与时效权重不变。负向权重保持原值。
WEIGHTS = {
    "lexical": 0.50,
    "consensus": 0.25,
    "authority": 0.15,
    "freshness": 0.10,
    "risk": -0.15,
    "spam": -0.10,
}

# M1 标定：构建方案里的 0.62 / 0.35 是给 minmax 归一后的相对分。
# 这里用绝对分，阈值按固定样本 + 40 条回归集重新标定（见决策文档 M1-D2）。
STRONG_THRESHOLD = 0.55
RELATED_THRESHOLD = 0.30
CAPS = {"strong": 10, "related": 10, "weak": 5}

BM25_K1 = 1.5
BM25_B = 0.75
LEXICAL_SATURATION = 6.0
# 扩展别名在覆盖率里的权重：只补召回，不抢主位
ALIAS_WEIGHT = 0.35

CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*")

TIME_INTENT = re.compile(
    r"(20\d{2}|最新|今年|本月|上周|昨天|今天|刚刚|新闻|动态|进展|发布|上线|"
    r"latest|news|release|update|changelog|roadmap)",
    re.IGNORECASE,
)

MARKETING_WORDS = (
    "加微信", "微信号", "加qq", "扫码", "限时优惠", "免费领取", "代理加盟",
    "点击咨询", "在线客服", "下载app", "私信我", "一手货源",
)

COMMERCIAL_INTENT = re.compile(r"(价格|报价|购买|下载|优惠|折扣|多少钱|批发|代理|price|buy|pricing)", re.IGNORECASE)

AUTHORITY_SUFFIXES = (".gov", ".gov.cn", ".edu", ".edu.cn", ".ac.uk", ".ac.jp", ".mil")
# 权威域名白名单：官方文档 / 百科 / 代码托管 / 标准组织。
# 这是人工维护的起点，M4 接黑名单与可信度数据后可以外部化。
AUTHORITY_DOMAINS = frozenset(
    {
        "wikipedia.org", "github.com", "gitlab.com", "arxiv.org", "python.org",
        "mozilla.org", "searxng.org", "nginx.org", "stackoverflow.com",
        "react.dev", "vitejs.dev", "openai.com", "kernel.org", "w3.org",
        "ietf.org", "npmjs.com", "tiangolo.com", "readthedocs.io",
        "nodejs.org", "typescriptlang.org", "rust-lang.org", "golang.org",
        "sqlite.org", "postgresql.org", "redis.io", "docker.com", "archlinux.org",
    }
)


def tokenize(text: str) -> list[str]:
    """英文按词、中文按二元组切分，够 BM25 用且不引入词典依赖。"""
    lowered = (text or "").lower()
    tokens = LATIN_TOKEN.findall(lowered)
    # 保留完整技术名，同时识别 deepseek-ai / DeepSeek-V4 等复合词的组成部分。
    tokens += [part for token in list(tokens) for part in re.findall(r"[a-z0-9]+", token)
               if part != token]
    for run in CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def bm25_scores(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    if not docs:
        return []
    total = len(docs)
    avgdl = sum(len(doc) for doc in docs) / total or 1.0
    df = Counter()
    for doc in docs:
        df.update(set(doc))
    scores: list[float] = []
    for doc in docs:
        tf = Counter(doc)
        length = len(doc)
        score = 0.0
        for term in set(query_tokens):
            if term not in tf:
                continue
            idf = math.log(1 + (total - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * freq * (BM25_K1 + 1) / (
                freq + BM25_K1 * (1 - BM25_B + BM25_B * length / avgdl)
            )
        scores.append(score)
    return scores


def authority_score(url_host: str) -> float:
    host = (url_host or "").lower()
    if not host:
        return 0.0
    if host.endswith(AUTHORITY_SUFFIXES):
        return 1.0
    registrable = ".".join(host.split(".")[-2:])
    if registrable in AUTHORITY_DOMAINS:
        return 1.0
    if host.startswith(("docs.", "developer.", "developers.")) or ".docs." in host:
        return 0.9
    return 0.0


def coverage(
    query_tokens: list[str],
    doc_tokens: list[str],
    alias_tokens: list[str] | None = None,
) -> float:
    """查询词覆盖率；别名（同义扩展）按半权计，避免扩展词压过原词。"""
    unique_query = set(query_tokens)
    alias_unique = set(alias_tokens or ()) - unique_query
    if not unique_query and not alias_unique:
        return 0.0
    doc = set(doc_tokens)
    original = len(unique_query & doc) / len(unique_query) if unique_query else 0.0
    alias = len(alias_unique & doc) / len(alias_unique) if alias_unique else 0.0
    if not alias_unique:
        return original
    # 原词为主、别名为辅：别名只补召回，不该压过用户真正输入的词
    return min(1.0, (1 - ALIAS_WEIGHT) * original + ALIAS_WEIGHT * alias)


def consensus_score(engine_count: int) -> float:
    """1 个引擎只是「有人报过」，2 个引擎同意才是有力信号，>=3 封顶。"""
    if engine_count <= 0:
        return 0.0
    if engine_count == 1:
        return 0.4
    if engine_count == 2:
        return 0.8
    return 1.0


def has_time_intent(query: str) -> bool:
    return bool(TIME_INTENT.search(query or ""))


def _freshness(published: str | None, time_intent: bool) -> float:
    if not time_intent or not published:
        return 0.0
    raw = published[:10]
    try:
        stamp = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    days = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 86400)
    return round(math.exp(-days / 365), 4)


def spam_score(result: Result, query: str) -> float:
    text = f"{result.title} {result.snippet}".lower()
    commercial = bool(COMMERCIAL_INTENT.search(query or ""))
    score = 0.0
    if not commercial and any(word in text for word in MARKETING_WORDS):
        score += 0.6
    if len(result.snippet.strip()) < 20:
        score += 0.2
    title_tokens = tokenize(result.title)
    if title_tokens:
        query_tokens = set(tokenize(query))
        hits = sum(1 for token in title_tokens if token in query_tokens)
        repeats = max((title_tokens.count(term) for term in query_tokens), default=0)
        if repeats >= 3 and hits / len(title_tokens) > 0.5:
            score += 0.4
    return round(min(score, 1.0), 4)


def _url_host(url: str) -> str:
    try:
        from urllib.parse import urlsplit

        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def score_results(
    query: str, results: list[Result], aliases: list[str] | None = None
) -> list[Result]:
    """就地写入 score 与 reasons，保持传入顺序（上游排名）不变。

    aliases 是查询扩展得到的同义词：只参与词法（BM25 与覆盖率），且半权。
    """
    if not results:
        return []
    query_tokens = tokenize(query)
    alias_tokens = tokenize(" ".join(aliases or []))
    lexical_query = query_tokens + alias_tokens
    docs = [tokenize(f"{r.title} {r.title} {r.snippet}") for r in results]
    raw_lexical = bm25_scores(lexical_query, docs)
    time_intent = has_time_intent(query)

    for result, raw, doc in zip(results, raw_lexical, docs):
        bm25_part = raw / (raw + LEXICAL_SATURATION) if raw > 0 else 0.0
        lexical = 0.5 * bm25_part + 0.5 * coverage(query_tokens, doc, alias_tokens)
        consensus = consensus_score(len(result.engine))
        authority = authority_score(_url_host(result.url))
        freshness = _freshness(result.published, time_intent)
        spam = spam_score(result, query)

        total = (
            WEIGHTS["lexical"] * lexical
            + WEIGHTS["consensus"] * consensus
            + WEIGHTS["authority"] * authority
            + WEIGHTS["freshness"] * freshness
            + WEIGHTS["risk"] * result.risk
            + WEIGHTS["spam"] * spam
        )
        result.score = round(max(0.0, min(total, 1.0)), 4)

        reasons: list[str] = []
        if lexical >= 0.35:
            reasons.append("标题与摘要命中查询词")
        if len(result.engine) >= 2:
            reasons.append(f"{len(result.engine)} 引擎共识")
        if authority >= 0.9:
            reasons.append("权威域名")
        if freshness >= 0.5:
            reasons.append("时效匹配")
        if result.risk >= SUSPICIOUS_RISK:
            reasons.append(f"风险分 {result.risk:.2f}")
        if spam >= 0.5:
            reasons.append("营销特征")
        result.reasons = reasons or ["仅弱匹配"]
    return results


SUSPICIOUS_RISK = 0.35


def group_results(results: list[Result]) -> tuple[list[Result], list[Result], list[Result]]:
    """按绝对分切三档；强相关允许为空，这是刻意设计。"""
    ordered = sorted(results, key=lambda r: (r.score, len(r.engine)), reverse=True)
    strong = [r for r in ordered if r.score >= STRONG_THRESHOLD][: CAPS["strong"]]
    related = [r for r in ordered if RELATED_THRESHOLD <= r.score < STRONG_THRESHOLD][: CAPS["related"]]
    weak = [r for r in ordered if r.score < RELATED_THRESHOLD][: CAPS["weak"]]
    return strong, related, weak
