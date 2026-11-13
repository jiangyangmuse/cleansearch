"""引擎目录与健康状态：给前端后缀选择器与运维排查用。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.config import get_settings
from app.core.aggregator import Aggregator, get_aggregator
from app.core.breaker import UPSTREAM_KEY, EngineHealthStore, get_health_store
from app.core.engine_catalog import catalog_rows, engine_candidates, searx_engine_name
from app.core.engine_preferences import (
    EnginePreferences, EnginePreferencesStore, get_engine_preferences_store, read_engine_preferences,
)
from app.core.errors import SearchError
from app.core.paid import build_paid_search

router = APIRouter(prefix="/api", tags=["engines"])


def _health_store() -> EngineHealthStore | None:
    settings = get_settings()
    if not settings.breaker_enabled:
        return None
    try:
        return get_health_store()
    except (OSError, sqlite3.Error):
        return None


@router.get("/engines")
def engines(preferences: EnginePreferences = Depends(read_engine_preferences)) -> dict:
    settings = get_settings()
    health = _health_store()
    paid = build_paid_search(settings) if settings.provider == "searxng" else None
    upstream_open = health is not None and health.is_open(UPSTREAM_KEY)
    rows = []
    for item in catalog_rows():
        row = dict(item)
        try:
            health_row = health.row(item["searx_engine"]) if health is not None else None
        except (sqlite3.Error, IndexError, TypeError):
            # 健康表损坏/并发异常不应让整个目录 500；该引擎显示 unknown 即可。
            health_row = None
        if health_row is None:
            row.update(
                {
                    "status": "unknown",
                    "available": None,
                    "fails": 0,
                    "avg_ms": None,
                    "last_error": None,
                    "remaining_seconds": 0,
                }
            )
        else:
            open_ = health_row.open
            remaining = 0
            if open_:
                try:
                    remaining = health.remaining(item["searx_engine"])
                except (sqlite3.Error, IndexError, TypeError):
                    remaining = 0
            row.update(
                {
                    "status": "cooldown" if open_ else ("ok" if health_row.last_ok else "unknown"),
                    "available": False if open_ else (True if health_row.last_ok else None),
                    "fails": health_row.fails,
                    "avg_ms": health_row.avg_ms,
                    "last_error": health_row.last_error,
                    "remaining_seconds": remaining,
                }
            )
        candidates = engine_candidates(item["engine"])
        free = [candidate for candidate in candidates if not upstream_open and (
            health is None or not health.is_open(searx_engine_name(candidate))
        )]
        paid_provider = paid.provider_for_engine(item["engine"]) if paid is not None else ""
        paid_ready = bool(paid_provider) and (health is None or not health.is_open(paid_provider))
        row["can_fallback"] = any(candidate != item["engine"] for candidate in free) or paid_ready
        row["selectable"] = bool(free) or paid_ready
        rows.append(row)

    rows.extend({
        "code": entry.code, "label": entry.label, "engine": entry.target if entry.kind == "engine" else "default",
        "searx_engine": entry.target if entry.kind == "engine" else "",
        "fallbacks": [], "paid": "", "aliases": [], "note": "",
        "kind": entry.kind, "section": "custom", "status": "unknown", "available": None,
        "can_fallback": False, "selectable": True, "fails": 0, "avg_ms": None,
        "last_error": None, "remaining_seconds": 0,
    } for entry in preferences.custom)

    return {
        "provider": settings.provider,
        "searxng_url": settings.searxng_url,
        "breaker": settings.breaker_enabled,
        "paid": {
            "serper": paid is not None and "serper" in paid.engines,
            "brave": paid is not None and "brave" in paid.engines,
        },
        "engines": rows,
    }


@router.get("/settings/engines")
async def engine_settings(
    preferences: EnginePreferences = Depends(read_engine_preferences),
    aggregator: Aggregator = Depends(get_aggregator),
) -> dict:
    try:
        sources = await aggregator.configured_engines()
    except SearchError:
        sources = None
    return {"preferences": preferences, "builtins": catalog_rows(), "sources": sources}


@router.put("/settings/engines", response_model=EnginePreferences)
def save_engine_settings(payload: dict, store: EnginePreferencesStore = Depends(get_engine_preferences_store)) -> EnginePreferences:
    try:
        preferences = EnginePreferences.model_validate(payload)
    except ValidationError as exc:
        message = exc.errors(include_input=False, include_context=False, include_url=False)[0]["msg"]
        raise HTTPException(422, message) from exc
    return store.save(preferences)
