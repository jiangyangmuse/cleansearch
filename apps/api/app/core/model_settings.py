"""Local model registry. Browser reads omit credentials."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.config import get_settings
from app.core.errors import SearchError
from app.core.fetch import FetchBlocked, validate_public_url
from app.core.normalize import is_renderable_url


Feature = Literal["search", "summary", "translate"]
LOOPBACK = {"localhost": "127.0.0.1", "127.0.0.1": "127.0.0.1", "::1": "::1"}


def model_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    if not is_renderable_url(value):
        raise ValueError("请输入有效的模型接口地址")
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("请输入有效的模型接口地址") from exc
    if url.query or "#" in value or "?" in value or url.path.endswith("/chat/completions"):
        raise ValueError("请输入 API 基址（例如 /v1），不包含查询参数或 /chat/completions")
    if url.host in LOOPBACK:
        return str(url.copy_with(host=LOOPBACK[url.host])).rstrip("/")
    if url.scheme != "https":
        raise ValueError("远程模型接口须使用 HTTPS")
    try:
        validate_public_url(value)
    except FetchBlocked as exc:
        raise ValueError("远程模型接口须使用公网地址") from exc
    return str(url).rstrip("/")


class ModelEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=400)
    model: str = Field(min_length=1, max_length=150)
    api_key: SecretStr | None = None
    features: set[Feature] = Field(default_factory=set)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return model_endpoint(value)

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            key = value.get_secret_value()
            if len(key) > 4096 or any(not 33 <= ord(char) <= 126 for char in key):
                raise ValueError("API 密钥包含无效字符")
        return value


class Assignment(BaseModel):
    primary: str | None = None
    fallback: str | None = None


class ModelSettings(BaseModel):
    revision: int = Field(default=0, ge=0)
    models: list[ModelEntry] = Field(default_factory=list, max_length=20)
    assignments: dict[Feature, Assignment] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_assignments(self) -> "ModelSettings":
        ids = {model.id for model in self.models}
        if len(ids) != len(self.models):
            raise ValueError("模型编号不能重复")
        for route in self.assignments.values():
            if any(model_id is not None and model_id not in ids for model_id in (route.primary, route.fallback)):
                raise ValueError("选择的模型不存在")
            if route.primary is not None and route.primary == route.fallback:
                raise ValueError("默认模型和备选模型须分别选择")
        return self

    def assignment(self, feature: Feature) -> Assignment:
        return self.assignments.get(feature, Assignment())

    def routed(self, feature: Feature) -> bool:
        route = self.assignment(feature)
        return route.primary is not None or route.fallback is not None

    def public(self) -> dict:
        payload = self.model_dump(mode="json", exclude={"models"})
        payload["models"] = [
            {**item.model_dump(mode="json", exclude={"api_key"}), "has_key": bool(item.api_key)}
            for item in self.models
        ]
        return payload


class ModelSettingsConflict(SearchError):
    code = "MODEL_SETTINGS_CONFLICT"
    http_status = 409
    retryable = False


class ModelStore:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _read(connection: sqlite3.Connection) -> ModelSettings:
        row = connection.execute("SELECT payload FROM ai_models WHERE id = 1").fetchone()
        return ModelSettings.model_validate_json(row[0]) if row else ModelSettings()

    def read(self) -> ModelSettings:
        if not self.path.is_file():
            return ModelSettings()
        with closing(sqlite3.connect(self.path)) as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'ai_models'").fetchone():
                return ModelSettings()
            return self._read(connection)

    def save(self, update: ModelSettings) -> ModelSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS ai_models (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection)
            if update.revision != current.revision:
                raise ModelSettingsConflict("模型配置已经更新，请重新加载设置后再保存")
            existing = {model.id: model for model in current.models}
            models = []
            for model in update.models:
                old = existing.get(model.id)
                if model.api_key is None and old and old.base_url == model.base_url:
                    model = model.model_copy(update={"api_key": old.api_key})
                elif model.api_key is not None and not model.api_key.get_secret_value():
                    model = model.model_copy(update={"api_key": None})
                models.append(model)
            saved = update.model_copy(update={"revision": current.revision + 1, "models": models})
            payload = saved.model_dump(mode="json")
            for row, model in zip(payload["models"], models, strict=True):
                row["api_key"] = model.api_key.get_secret_value() if model.api_key else None
            connection.execute("INSERT OR REPLACE INTO ai_models VALUES (1, ?)", (json.dumps(payload),))
        return saved


def get_model_store() -> ModelStore:
    path = get_settings().db_path
    return ModelStore(path.with_name(path.name + ".ai-models"))


def read_model_settings() -> ModelSettings:
    return get_model_store().read()
