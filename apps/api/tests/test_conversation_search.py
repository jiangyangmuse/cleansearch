import json

import httpx

from app.core.aggregator import Aggregated, get_aggregator
from app.core.engine_preferences import EnginePreferences, read_engine_preferences
from app.core.errors import UpstreamTimeout
from app.core.llm import OpenAICompatibleClient
from app.core.model_settings import ModelSettings, read_model_settings
from app.core.normalize import normalise_result
from app.main import app
from app.routers import search


def model_with_plan(monkeypatch, *directions):
    requests = []

    def respond(request):
        requests.append(json.loads(json.loads(request.content)["messages"][-1]["content"]))
        output = json.dumps({"directions": directions})
        chunk = json.dumps({"choices": [{"delta": {"content": output}}]})
        return httpx.Response(200, text=f"data: {chunk}\n\ndata: [DONE]\n\n")

    model = OpenAICompatibleClient("https://model.test", "test", "planner", 1, httpx.MockTransport(respond))
    monkeypatch.setattr(search, "configured_client", lambda: model)
    return requests


def test_conversation_carries_context_and_groups_real_sources(client, monkeypatch):
    calls = model_with_plan(monkeypatch,
        {"label": "入门文档", "query": "Python 官方教程"},
        {"label": "教学视频", "query": "Python 中文视频"},
        {"label": "练习", "query": "Python 入门练习"},
    )
    sent = []

    class CandidateSource:
        async def search(self, *, q, allow_paid, selected_engines):
            sent.append(q)
            assert not allow_paid and selected_engines == ("bing",)
            if "练习" in q:
                raise UpstreamTimeout("练习方向超时")
            urls = ["https://docs.python.org/3/tutorial/"] if "教程" in q else [
                "https://docs.python.org/3/tutorial/?utm_source=test", "https://www.bilibili.com/video/BV100/",
            ]
            return Aggregated(results=[normalise_result(
                {"url": url, "title": q, "engine": "bing"}, index,
            ) for index, url in enumerate(urls, 1)])

    monkeypatch.setitem(app.dependency_overrides, get_aggregator, CandidateSource)
    monkeypatch.setitem(app.dependency_overrides, read_engine_preferences, lambda: EnginePreferences(default_engines=["b"]))
    history = [{"message": "想自学 Python", "directions": ["官方教程"]}]
    result = client.post("/api/conversation-search", json={"message": "加视频和练习", "history": history})
    assert result.status_code == 200
    data = result.json()
    assert data["model"] == "planner" and calls[0]["history"] == history
    assert set(sent) == {"Python 官方教程", "Python 中文视频", "Python 入门练习"}
    assert [[row["url"] for row in group["results"]] for group in data["groups"]] == [
        ["https://docs.python.org/3/tutorial/"], ["https://www.bilibili.com/video/BV100/"], [],
    ]
    assert data["groups"][2]["error"] == "练习方向超时"


def test_invalid_plan_can_use_enabled_backup_and_skips_disabled_backup(client, monkeypatch):
    model_with_plan(monkeypatch, {"label": "网页", "query": "!google https://invented.test"})
    config = ModelSettings.model_validate({
        "models": [{"id": "backup", "label": "备选", "model": "mock", "base_url": "http://localhost:11434/v1", "features": []}],
        "assignments": {"search": {"fallback": "backup"}},
    })
    monkeypatch.setitem(app.dependency_overrides, read_model_settings, lambda: config)
    invoked = []
    model = search.configured_client()
    monkeypatch.setattr(search, "imported_client", lambda entry: invoked.append(entry.id) or model)
    response = client.post("/api/conversation-search", json={"message": "找 Python 教程"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "MODEL_FALLBACK_DISABLED"
    assert not invoked
    config.models[0].features.add("search")
    model_with_plan(monkeypatch, {"label": "Python 教程", "query": "Python 官方教程"})
    backup = search.configured_client()
    monkeypatch.setattr(search, "configured_client", lambda: model)
    monkeypatch.setattr(search, "imported_client", lambda entry: invoked.append(entry.id) or backup)
    result = client.post("/api/conversation-search", json={"message": "找 Python 教程"})
    assert result.status_code == 200 and result.json()["model"] == "备选"
    assert invoked == ["backup"]
