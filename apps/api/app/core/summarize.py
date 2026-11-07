"""侧栏总结管线：把搜索快照转成带编号引用的流式文本。

M2 只做 mode=fast（用摘要，不抓正文）；正文增强是 M4。
没有配置 LLM 端点时用本地抽取式桩，产物明确标注为桩，便于离线验收与测试。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from dataclasses import replace

from app.config import get_settings
from app.core.extract import extract_article
from app.core.llm import OpenAICompatibleClient
from app.core.session_store import Snapshot

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_SOURCES = 10
FULL_MAX_SOURCES = 5
FULL_CHARS_PER_SOURCE = 3000
SENTENCE_END = re.compile(r"(?<=[。！？!?；;])\s*")


class Summarizer(Protocol):
    model: str

    def stream(self, snapshot: Snapshot) -> AsyncGenerator[str, None]: ...


def build_materials(snapshot: Snapshot) -> str:
    blocks: list[str] = []
    for index, source in enumerate(snapshot.sources[:MAX_SOURCES], 1):
        blocks.append(
            f"[{index}] 标题：{source.title} ｜ 域名：{source.domain} ｜ 链接：{source.url}\n"
            f"摘要：{source.snippet or '（无摘要）'}"
        )
    return "\n\n".join(blocks)


def build_user_prompt(snapshot: Snapshot) -> str:
    template = (PROMPT_DIR / "summary_user.txt").read_text(encoding="utf-8")
    return template.format(query=snapshot.query, materials=build_materials(snapshot))


def build_system_prompt(*, single_page: bool = False) -> str:
    prompt = (PROMPT_DIR / "summary_system.txt").read_text(encoding="utf-8")
    if single_page:
        prompt += (
            "\n单页总结格式：第一行只写一句结论。正文足够时，另起行列出 2–3 条不同要点，"
            "每条以「- 」开头。省略「结论」「要点」等小标题，材料不足时可以少写。"
        )
    return prompt


async def enrich_with_full_text(snapshot, fetcher, limit: int = FULL_MAX_SOURCES):
    """抓正文替换摘要；失败的单条保留原摘要，并统计降级条数。"""
    sources = snapshot.sources[:MAX_SOURCES]
    stats = {"fetched": 0, "failed": 0, "truncated": 0}

    async def one(source):
        try:
            page = await fetcher.fetch(source.url)
            article = await asyncio.to_thread(extract_article, page.text, page.url, source.title)
            if len(article.text.strip()) < 80:
                raise ValueError("正文过短")
            if page.truncated:
                stats["truncated"] += 1
            return replace(
                source, snippet=article.text[:FULL_CHARS_PER_SOURCE],
                material="truncated" if page.truncated else "full",
            )
        except Exception:
            return source

    results = await asyncio.gather(*(one(source) for source in sources[:limit]))
    for source in results:
        if source.material == "snippet":
            stats["failed"] += 1
        else:
            stats["fetched"] += 1
    adjusted = replace(snapshot, sources=results + sources[limit:])
    return adjusted, stats


class LLMSummarizer:
    """真实模型：OpenAI 兼容端点（Ollama / vLLM / 云 API 都吃这套）。"""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self._client = client
        self.model = client.model

    async def stream(self, snapshot: Snapshot) -> AsyncGenerator[str, None]:
        system = build_system_prompt(single_page=snapshot.provider == "page")
        async with aclosing(self._client.stream(system, build_user_prompt(snapshot))) as stream:
            async for token in stream:
                yield token


class StubSummarizer:
    """本地抽取式桩：不调用模型，只用摘要拼出结构化结果，便于离线验收。

    产物结构与提示词要求一致（结论段 + 要点 + 分歧），引用编号始终落在材料范围内。
    """

    model = "stub-extractive"
    chunk_size = 6

    def __init__(self, delay: float = 0.0) -> None:
        self._delay = max(0.0, delay)

    @staticmethod
    def compose(snapshot: Snapshot) -> str:
        sources = snapshot.sources[:MAX_SOURCES]
        if not sources:
            return "材料不足：本次搜索没有可用结果。"
        if len(sources) == 1 and len(sources[0].snippet) > 240:
            # 单页模式：原文就是材料，直接摘句子，别复述一句「材料指向 1 条」
            sentences = [
                chunk.strip()
                for chunk in SENTENCE_END.split(sources[0].snippet)
                if len(chunk.strip()) >= 12
            ][:4]
            body = "\n".join(f"- {sentence}" for sentence in sentences)
            return f"围绕「{snapshot.query}」，材料为单篇原文。\n主要要点：\n{body}"
        first = sources[0]
        lead = first.snippet.strip() or first.title
        lead_sentence = SENTENCE_END.split(lead)[0].strip()[:120]
        citations = "".join(f"[{i}]" for i in range(1, min(len(sources), 3) + 1))
        lines = [
            f"围绕「{snapshot.query}」，材料指向 {len(sources)} 条结果{'' if not lead_sentence else '：' + lead_sentence}{citations}。",
            "主要要点：",
        ]
        for index, source in enumerate(sources, 1):
            snippet = (source.snippet.strip() or source.title).split("。")[0][:70]
            lines.append(f"- [{index}] {source.title}：{snippet}")
        if len(sources) > 1:
            lines.append(
                f"分歧：材料侧重不同（[1] 讲 {sources[0].domain}，[{len(sources)}] 讲 {sources[-1].domain}），未发现直接冲突。"
            )
        return "\n".join(lines)

    async def stream(self, snapshot: Snapshot) -> AsyncGenerator[str, None]:
        text = self.compose(snapshot)
        for start in range(0, len(text), self.chunk_size):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield text[start : start + self.chunk_size]


@lru_cache(maxsize=1)
def get_summarizer() -> Summarizer:
    settings = get_settings()
    if settings.llm_provider == "openai" and settings.llm_base_url:
        return LLMSummarizer(
            OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
                reasoning_effort=settings.llm_reasoning_effort,
            )
        )
    return StubSummarizer(delay=settings.llm_stub_delay)
