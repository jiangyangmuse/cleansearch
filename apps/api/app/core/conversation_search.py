"""Turn a search conversation into a small, validated plan."""

import json
import re
import unicodedata
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.core.llm import LLMBadResponse, OpenAICompatibleClient
from app.core.model_routing import collect_text
from app.schemas import Result

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
DirectionLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Keywords = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class PreviousSearch(BaseModel):
    message: Message
    directions: list[DirectionLabel] = Field(max_length=3, default_factory=list)


class ConversationRequest(BaseModel):
    message: Message
    history: list[PreviousSearch] = Field(max_length=6, default_factory=list)


class SearchDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: DirectionLabel
    query: Keywords


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directions: list[SearchDirection] = Field(min_length=1, max_length=3)


class ConversationGroup(SearchDirection):
    results: list[Result]
    error: str | None = None


class ConversationResponse(BaseModel):
    model: str
    groups: list[ConversationGroup]


SYSTEM_PROMPT = (
    "你为网页搜索生成查询。结合对话里的需求和之前的方向，解析当前消息中的代词、限制与新增需求。"
    "根据意图给 1 到 3 个互补方向：需要多种内容时分开搜索，明确的单一需求只给一个。"
    "追问中用「再加」「另外」「也找」新增的独立材料单列。只把网站、语言等限制应用于它修饰的方向。"
    "例如前文是学习 Python，追问「视频只要 B 站，再加练习题」，分别查询「Python 入门视频 site:bilibili.com」"
    "和「Python 新手练习题」，不要合成一个查询。"
    "每个 query 是精简、可独立提交给搜索引擎的关键词，保留主题、地名、版本或用户约束。"
    "不确定时提供最有用的可能方向。不要回答问题、编造网址或输出引擎指令。"
    '只返回 JSON，形如 {"directions":[{"label":"官方入门文档","query":"Python 官方入门教程"}]}。'
    "label 用与当前用户相同的语言。"
)


async def plan_search(client: OpenAICompatibleClient, request: ConversationRequest) -> list[SearchDirection]:
    text = await collect_text(client.stream(
        SYSTEM_PROMPT, json.dumps(request.model_dump(), ensure_ascii=False),
    ), limit=4000)
    text = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", text, flags=re.IGNORECASE)
    try:
        plan = SearchPlan.model_validate_json(text)
        directions = {}
        for entry in plan.directions:
            query = " ".join(unicodedata.normalize("NFKC", entry.query).split())
            if len(query) > 120 or re.search(r"(?:^|\s)[!:]\S|https?://", query, re.IGNORECASE):
                raise ValueError("invalid search query")
            directions.setdefault(query.casefold(), SearchDirection(label=entry.label, query=query))
    except (ValidationError, ValueError) as exc:
        raise LLMBadResponse("模型没有返回有效的搜索方向，请重试") from exc
    return list(directions.values())
