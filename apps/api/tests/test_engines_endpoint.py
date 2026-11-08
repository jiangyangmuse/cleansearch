"""GET /api/engines：目录与状态接口。"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.breaker import EngineHealthStore, UPSTREAM_KEY
from app.routers import engines as engine_router


def test_engines_endpoint_lists_catalog(client: TestClient) -> None:
    response = client.get("/api/engines")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "fixture"
    codes = {item["code"] for item in payload["engines"]}
    assert {"g", "b", "d", "sc", "w", "gc", "mj", "n", "yd", "sw"} <= codes
    google = next(item for item in payload["engines"] if item["code"] == "g")
    assert google["engine"] == "google"
    assert google["fallbacks"] == ["google cse"]
    assert google["paid"] == "search"
    assert google["status"] == "unknown"
    assert google["available"] is None
    assert google["selectable"] is True


def test_catalog_selection_accounts_for_fallback_and_paid_switch(client, monkeypatch, tmp_path):
    health = EngineHealthStore(tmp_path / "health.db", fail_threshold=1, cooldown=60)
    settings = replace(get_settings(), provider="searxng", breaker_enabled=True,
                       brave_api_key="", serper_api_key="test-only", paid_fallback=False)
    monkeypatch.setattr(engine_router, "get_settings", lambda: settings)
    monkeypatch.setattr(engine_router, "_health_store", lambda: health)

    def google():
        payload = client.get("/api/engines").json()
        assert "test-only" not in str(payload)
        return payload, next(item for item in payload["engines"] if item["code"] == "g")

    try:
        health.record_failure("google", "blocked")
        payload, row = google()
        assert row["status"] == "cooldown" and row["available"] is False
        assert row["can_fallback"] and row["selectable"]  # CSE 仍可尝试
        assert payload["paid"] == {"serper": False, "brave": False}
        health.record_failure("google cse", "blocked")
        assert google()[1]["selectable"] is False
        settings = replace(settings, paid_fallback=True)
        assert google()[1]["selectable"] is True  # 已配置的 Serper
        health.record_failure("serper", "HTTP 429")
        assert google()[1]["selectable"] is False
        health.record_success("google")
        health.record_failure(UPSTREAM_KEY, "offline")
        assert google()[1]["selectable"] is False  # 实例熔断阻断所有免费候选
    finally:
        health.close()
