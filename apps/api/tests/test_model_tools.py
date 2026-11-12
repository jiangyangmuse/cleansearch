import json

import httpx
import pytest

from app.core import ai_search, summarize
from app.core.fetch import SafeFetcher
from app.core.llm import OpenAICompatibleClient
from app.core.model_routing import FALLBACK_DISABLED
from app.core.model_settings import ModelStore, get_model_store, read_model_settings
from app.deps import get_fetcher
from app.main import app
from app.routers import ai_tools


def entry(name, features, **extra):
    return {
        "id": name, "label": name, "model": name, "base_url": "http://localhost:11434/v1",
        "features": features, **extra,
    }


@pytest.fixture
def registry(monkeypatch, tmp_path):
    store = ModelStore(tmp_path / "models.db")
    monkeypatch.setitem(app.dependency_overrides, get_model_store, lambda: store)
    monkeypatch.setitem(app.dependency_overrides, read_model_settings, store.read)
    return store


def mocked_models(monkeypatch, outputs):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        name = body["model"]
        calls.append(body)
        output = outputs[name]
        if isinstance(output, int):
            return httpx.Response(output)
        if callable(output):
            output = output(body)
        payload = json.dumps({"choices": [{"delta": {"content": output}}]}, ensure_ascii=False)
        return httpx.Response(200, text=f"data: {payload}\n\ndata: [DONE]\n\n")

    def build(model):
        return OpenAICompatibleClient(
            model.base_url, "", model.model, 2, transport=httpx.MockTransport(handler),
        )

    for module in (ai_tools, ai_search, summarize):
        monkeypatch.setattr(module, "imported_client", build)
    return calls


def test_registry_redacts_keys_rejects_stale_saves_and_does_not_forward_old_key(client, registry):
    path = "/api/settings/models"
    initial = {"revision": 0, "models": [entry("primary", ["search"], api_key="test-private-token")]}
    saved = client.put(path, json=initial)
    assert saved.status_code == 200
    assert "test-private-token" not in saved.text and "api_key" not in saved.text
    assert saved.json()["models"][0]["has_key"]
    assert client.get(path).headers["cache-control"] == "no-store"
    assert client.put(path, json=initial).status_code == 409
    assert registry.read().models[0].api_key.get_secret_value() == "test-private-token"

    moved = {"revision": 1, "models": [entry("primary", ["search"], base_url="https://api.example.com/v1")]}
    assert not client.put(path, json=moved).json()["models"][0]["has_key"]
    blocked = {"revision": 2, "models": [entry("primary", [], base_url="https://192.168.0.10/v1")]}
    assert client.put(path, json=blocked).status_code == 422
    assert client.put(path, json=moved, headers={"Origin": "https://evil.example"}).status_code == 403


def test_translation_only_attempts_enabled_fallback(client, registry, monkeypatch):
    calls = mocked_models(monkeypatch, {"primary": 503, "backup": "编程语言"})
    path = "/api/settings/models"
    config = {
        "models": [entry("primary", ["translate"]), entry("backup", ["summary"])],
        "assignments": {"translate": {"primary": "primary", "fallback": "backup"}},
    }
    assert client.put(path, json=config).status_code == 200
    translated = {"text": "programming language", "target": "zh"}
    failed = client.post("/api/translate", json=translated)
    assert failed.status_code == 503
    assert failed.json()["error"] == {
        "code": "MODEL_FALLBACK_DISABLED", "message": FALLBACK_DISABLED, "retryable": False,
    }
    assert [call["model"] for call in calls] == ["primary"]

    config["revision"] = 1
    config["models"][1]["features"].append("translate")
    assert client.put(path, json=config).status_code == 200
    response = client.post("/api/translate", json=translated)
    assert response.json() == {"text": "编程语言", "model": "backup"}
    assert [call["model"] for call in calls] == ["primary", "primary", "backup"]


def test_imported_search_only_returns_existing_urls_and_reuses_candidates_for_backup(client, registry, monkeypatch):
    candidate_url = None

    def select(body):
        nonlocal candidate_url
        candidate = json.loads(body["messages"][-1]["content"])["candidates"][0]
        candidate_url = candidate["url"]
        return json.dumps({"ids": [candidate["id"]]})

    calls = mocked_models(monkeypatch, {"primary": '{"ids":["unknown"]}', "backup": select})
    assert client.put("/api/settings/models", json={
        "models": [entry("primary", ["search"]), entry("backup", ["search"])],
        "assignments": {"search": {"primary": "primary", "fallback": "backup"}},
    }).status_code == 200
    response = client.post("/api/ai-search", json={"q": "python 文档 ds"})
    assert response.status_code == 200
    assert response.json()["provider"] == "backup"
    assert [item["url"] for item in response.json()["results"]] == [candidate_url]
    assert calls[0]["messages"][-1] == calls[1]["messages"][-1]


def test_batch_reports_failed_url_and_uses_same_model_as_search_summary(client, registry, monkeypatch):
    def upstream(request):
        source = "甲" if request.url.path == "/first" else "乙"
        text = ("这是一段用于验证正文抓取和来源编号的正文材料。" * 12) + source
        return httpx.Response(200, text=f"<html><title>来源{source}</title><article><p>{text}</p></article></html>",
                              headers={"content-type": "text/html"})

    fetcher = SafeFetcher(transport=httpx.MockTransport(upstream), resolver=lambda _: ["93.184.216.34"])
    monkeypatch.setitem(app.dependency_overrides, get_fetcher, lambda: fetcher)
    calls = mocked_models(monkeypatch, {"primary": 503, "backup": "总结文字[1]"})
    assert client.put("/api/settings/models", json={
        "models": [entry("primary", ["summary"]), entry("backup", ["summary"])],
        "assignments": {"summary": {"primary": "primary", "fallback": "backup"}},
    }).status_code == 200
    payload = {"urls": ["https://example.com/first", "http://127.0.0.1/private", "https://example.com/second"]}
    response = client.post("/api/pages/summarize", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "backup" and body["summary"] == "总结文字[1]"
    assert [page.get("title") for page in body["pages"]] == ["来源甲", None, "来源乙"]
    assert "拒绝非公网地址" in body["pages"][1]["error"]
    assert "[1] 标题：来源甲" in calls[1]["messages"][-1]["content"]
    assert "[2] 标题：来源乙" in calls[1]["messages"][-1]["content"]

    sid = client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["sid"]
    sse = client.get("/api/summarize", params={"sid": sid})
    assert sse.status_code == 200 and '"model": "backup"' in sse.text and "event: done" in sse.text
    page = client.post("/api/page/summarize", json={"url": payload["urls"][0]})
    assert page.status_code == 200 and page.json()["model"] == "backup"
