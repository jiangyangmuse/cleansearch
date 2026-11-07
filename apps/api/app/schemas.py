"""请求 / 响应模型。字段命名与 docs/搜索聚合器-构建方案.md §6.1 对齐。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SearchOpts(BaseModel):
    safe: bool = True
    exact: bool = False
    summarize: bool = False
    # M0 自检用：显式指定 fixture 样本，未指定则按查询内容判定
    fixture: Literal["hit", "empty", "error", "risky"] | None = None


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


class Groups(BaseModel):
    strong: list[Result] = Field(default_factory=list)
    related: list[Result] = Field(default_factory=list)
    weak: list[Result] = Field(default_factory=list)


class FilteredCounts(BaseModel):
    dup: int = 0
    risk: int = 0


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
    sid: str


class SearchResponse(BaseModel):
    parsed: ParsedQuery
    groups: Groups
    meta: SearchMeta


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