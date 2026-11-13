"""请求 / 响应模型。字段命名与 docs/搜索聚合器-构建方案.md §6.1 对齐。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_serializer


class SearchOpts(BaseModel):
    safe: bool = True
    exact: bool = False
    summarize: bool = False
    literal: bool = False  # 整段作为查询文本，末尾词不解析为路由
    # 筛选能力：时间范围 / 语言 / 站点限定 / 去重强度
    time_range: Literal["day", "week", "month", "year"] | None = None
    language: str | None = Field(default=None, max_length=12)
    site: str | None = Field(default=None, max_length=253)
    dedupe: Literal["off", "normal", "strict"] = "normal"
    # M0 自检用：显式指定 fixture 样本，未指定则按查询内容判定
    fixture: Literal["hit", "empty", "error", "risky"] | None = None

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().lower()
        if not text:
            return None
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", text):
            raise ValueError("语言代码形如 zh、en 或 pt-BR")
        language, separator, region = text.partition("-")
        return language + separator + (region.title() if len(region) == 4 else region.upper())

    @field_validator("site")
    @classmethod
    def _check_site(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().lower()
        if not text:
            return None
        for prefix in ("https://", "http://"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = re.split(r"[/?#]", text, maxsplit=1)[0].removesuffix(".")
        if text.startswith("www."):
            text = text[4:]
        labels = text.split(".")
        if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            raise ValueError("站点限定只接受域名，例如 example.com")
        return text


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=512)
    page: int = Field(default=1, ge=1, le=10)
    region: str | None = None
    opts: SearchOpts = Field(default_factory=SearchOpts)

    @field_validator("q")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("查询不能为空")
        return stripped


class ParsedQuery(BaseModel):
    q: str
    engine: str = "default"
    region: str | None = None
    router: Literal["suffix", "bang", "default"] = "default"
    # 查询扩展命中的同义词（M9）；没有扩展时为空数组
    expanded: list[str] = Field(default_factory=list)
    custom_code: str | None = None
    open_url: str | None = None

    @model_serializer(mode="wrap")
    def omit_unused_shortcut_fields(self, serialize):
        data = serialize(self)
        for key in ("custom_code", "open_url"):
            if data.get(key) is None:
                data.pop(key, None)
        return data


class Result(BaseModel):
    id: str
    url: str
    display_url: str
    title: str
    snippet: str = ""
    engine: list[str] = Field(default_factory=list)
    score: float = 0.0
    risk: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    favicon: str | None = None
    published: str | None = None
    read_minutes: int | None = None
    # 可疑结果的确认中转地址（/go?u=&sig=），正常结果为 None
    go_url: str | None = None
    # 品牌首页自称官网但未通过身份核验；不等于确认恶意。
    brand_warning: str | None = None
    category: Literal["encyclopedia", "download", "video"] | None = None


class AISearchResponse(BaseModel):
    provider: str
    results: list[Result]
    cached: bool = False


class Groups(BaseModel):
    strong: list[Result] = Field(default_factory=list)
    related: list[Result] = Field(default_factory=list)
    weak: list[Result] = Field(default_factory=list)


class OfficialLink(Result):
    """官方地址：区分检索候选与目录直达，不伪造搜索来源。"""

    role: str
    label: str
    host: str
    source: str = ""
    verified: str = ""
    origin: Literal["search", "directory"] = "search"


class OfficialSection(BaseModel):
    key: str
    brand: str
    entries: list[OfficialLink] = Field(default_factory=list)


class FilteredCounts(BaseModel):
    dup: int = 0
    risk: int = 0


class SearchFilters(BaseModel):
    """回显本次生效的筛选条件；未启用时字段为 None/默认。"""

    time_range: str | None = None
    language: str | None = None
    site: str | None = None
    dedupe: str = "normal"


class SearchMeta(BaseModel):
    status: Literal["ok", "empty"]
    engines: list[str] = Field(default_factory=list)
    unresponsive: list[str] = Field(default_factory=list)
    provider: str
    cached: bool = False
    ms: int = 0
    total: int = 0
    upstream_total: int = 0
    filtered: FilteredCounts = Field(default_factory=FilteredCounts)
    official: int = 0
    directory: int = 0
    # 本次生效的筛选条件（回显给前端做筛选条状态）
    filters: SearchFilters = Field(default_factory=SearchFilters)
    sid: str


class SearchResponse(BaseModel):
    parsed: ParsedQuery
    groups: Groups
    meta: SearchMeta
    # 品牌导航查询的独立官方入口区；未知品牌或未命中时为 None
    official: OfficialSection | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = True


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    provider: str
    searxng_url: str
    web_dist: str
    web_built: bool
    blocklist_rules: int = 0
    llm_provider: str = "stub"
    llm_model: str = ""
    bookmarks: int = 0
    db_path: str = ""
    version: str


class BookmarkCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=512)
    group_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=32)


class BookmarkUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    tags: list[str] | None = Field(default=None, max_length=32)
    group_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    dead: int | None = Field(default=None, ge=0, le=1)


class Bookmark(BaseModel):
    id: int
    url: str
    url_key: str
    title: str | None = None
    favicon: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    note: str | None = None
    created_at: int
    last_visit: int | None = None
    visits: int = 0
    dead: int = 0
    dead_status: int | None = None
    dead_checked_at: int | None = None
    tags: list[str] = Field(default_factory=list)


class BookmarkGroup(BaseModel):
    id: int
    name: str
    icon: str | None = None
    sort: int = 0
    count: int = 0


class BookmarkList(BaseModel):
    items: list[Bookmark]
    groups: list[BookmarkGroup]
    tags: list[dict] = Field(default_factory=list)
    total: int
    fts: bool


class BookmarkCaptureResult(BaseModel):
    deduplicated: bool


class BookmarkSaveResult(BookmarkCaptureResult):
    item: Bookmark


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ImportResult(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    groups_created: int
