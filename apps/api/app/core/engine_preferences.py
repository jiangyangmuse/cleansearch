"""默认引擎与自定义搜索入口的本机配置。"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Literal
from urllib.parse import quote, quote_plus, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings
from app.core.engine_catalog import ENGINE_SUFFIXES, SPEC_BY_CODE
from app.core.errors import SearchError
from app.core.normalize import is_renderable_url
from app.core.query_parser import REGION_SUFFIXES, Parsed, parse_query


class EnginePreferencesConflict(SearchError):
    code = "ENGINE_SETTINGS_CONFLICT"
    http_status = 409
    retryable = False


class NoSelectedEngines(SearchError):
    code = "SEARCH_ENGINES_DISABLED"
    http_status = 422
    retryable = False


class CustomSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9]{0,7}$")
    label: str = Field(min_length=1, max_length=48)
    kind: Literal["engine", "region", "website"]
    target: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_target(self) -> CustomSearch:
        if self.kind == "engine":
            if not re.fullmatch(r"[\w .&()+/-]{1,100}", self.target):
                raise ValueError("请输入 SearXNG 中的引擎名称")
        elif self.kind == "region":
            if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{4})?(?:-[A-Za-z]{2}|-\d{3})?", self.target):
                raise ValueError("请输入有效的语言或地区，如 fr 或 fr-FR")
        else:
            if self.target.count("{q}") != 1 or not is_renderable_url(self.target.replace("{q}", "test")):
                raise ValueError("网址模板须为 HTTP(S) 链接，并含一个 {q}")
            parts = urlsplit(self.target)
            if "{q}" in parts.netloc or "{q}" in parts.fragment:
                raise ValueError("{q} 须放在网址路径或查询参数中")
        return self

    def website_url(self, query: str) -> str:
        encoded = quote_plus(query) if "{q}" in urlsplit(self.target).query else quote(query, safe="")
        return self.target.replace("{q}", encoded)


class EnginePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(default=0, ge=0)
    default_engines: list[str] | None = Field(default=None, max_length=60)
    custom: list[CustomSearch] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_codes(self) -> EnginePreferences:
        reserved = {*ENGINE_SUFFIXES, *REGION_SUFFIXES, "ds"}
        custom_codes = {entry.code for entry in self.custom}
        if len(custom_codes) != len(self.custom) or reserved & custom_codes:
            raise ValueError("后缀重复或已被系统占用")
        if self.default_engines is not None:
            allowed = {*SPEC_BY_CODE, *(entry.code for entry in self.custom if entry.kind == "engine")}
            if not set(self.default_engines) <= allowed or len(set(self.default_engines)) != len(self.default_engines):
                raise ValueError("默认列表须使用已登记的引擎，每个后缀只选一次")
        return self

    def parse(self, query: str, *, literal: bool) -> tuple[Parsed, CustomSearch | None]:
        custom = {entry.code: entry for entry in self.custom}
        parsed = parse_query(query, literal=literal, custom_codes=custom)
        entry = custom.get(parsed.custom_code or "")
        if entry and entry.kind == "region":
            parsed = replace(parsed, region=entry.target)
        return parsed, entry

    def selected(self, parsed: Parsed, entry: CustomSearch | None) -> tuple[str, ...] | None:
        if entry and entry.kind == "engine":
            return (entry.target,)
        if parsed.engine != "default" or self.default_engines is None:
            return None
        targets = {entry.code: entry.target for entry in self.custom if entry.kind == "engine"}
        targets.update({code: spec.searx_engine for code, spec in SPEC_BY_CODE.items()})
        return tuple(sorted({targets[code] for code in self.default_engines}))


class EnginePreferencesStore:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _read(connection: sqlite3.Connection) -> EnginePreferences:
        row = connection.execute("SELECT payload FROM search_engine_preferences WHERE id = 1").fetchone()
        return EnginePreferences.model_validate_json(row[0]) if row else EnginePreferences()

    def read(self) -> EnginePreferences:
        if not self.path.is_file():
            return EnginePreferences()
        with closing(sqlite3.connect(self.path)) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'search_engine_preferences'"
            ).fetchone()
            return self._read(connection) if table else EnginePreferences()

    def save(self, preferences: EnginePreferences) -> EnginePreferences:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS search_engine_preferences (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute("BEGIN IMMEDIATE")
            if preferences.revision != self._read(connection).revision:
                raise EnginePreferencesConflict("引擎设置已更新，请重新加载后再保存")
            saved = preferences.model_copy(update={"revision": preferences.revision + 1})
            connection.execute("INSERT OR REPLACE INTO search_engine_preferences VALUES (1, ?)", (saved.model_dump_json(),))
        return saved


def get_engine_preferences_store() -> EnginePreferencesStore:
    return EnginePreferencesStore(get_settings().db_path)


def read_engine_preferences() -> EnginePreferences:
    return get_engine_preferences_store().read()
