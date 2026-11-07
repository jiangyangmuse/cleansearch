"""查询扩展：词典版同义 / 缩写映射。

没有 embedding 模型时，用一张人工维护的小词典补「同义改写」召回；
别名命中只给一半权重，避免扩出来的词压过用户真正输入的词。
"""

from __future__ import annotations

import re

MAX_ALIASES = 6

ALIASES: dict[str, tuple[str, ...]] = {
    "数分": ("数据分析", "数学分析"),
    "高数": ("高等数学", "微积分"),
    "概率": ("概率论", "统计"),
    "ml": ("machine learning", "机器学习"),
    "ai": ("artificial intelligence", "人工智能"),
    "dl": ("deep learning", "深度学习"),
    "nlp": ("natural language processing", "自然语言处理"),
    "js": ("javascript",),
    "ts": ("typescript",),
    "py": ("python",),
    "k8s": ("kubernetes",),
    "db": ("database", "数据库"),
    "sql": ("structured query language", "数据库查询"),
    "llm": ("large language model", "大语言模型", "大模型"),
    "rag": ("retrieval augmented generation", "检索增强"),
    "ops": ("devops", "运维"),
}


def _hit(key: str, lowered: str) -> bool:
    """ASCII 短码按词边界匹配（避免 py 命中 python），中文按子串匹配。"""
    if key.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", lowered) is not None
    return key in lowered


def expand_aliases(query: str) -> list[str]:
    """返回与查询相关的别名词（最多 MAX_ALIASES 个），按词典顺序去重。"""
    lowered = (query or "").lower()
    found: list[str] = []
    for key, aliases in ALIASES.items():
        if _hit(key, lowered):
            for alias in aliases:
                if alias not in found and alias.lower() != lowered:
                    found.append(alias)
    return found[:MAX_ALIASES]
