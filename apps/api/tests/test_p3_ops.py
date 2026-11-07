"""P3：SQLite 快照、favicon 缓存、导入进度、指标。"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import metrics
from app.core.session_store import SessionStore, Source
from app.core.summarize import get_summarizer
from app.deps import get_fetcher
from app.main import app
from app.routers import assets

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def test_session_snapshot_survives_new_process(tmp_path) -> None:
    db = tmp_path / "s.db"
    first = SessionStore(db)
    first.put("s_1", "查询", [Source("r1", "https://a.test", "标题", "摘要", "a.test")], provider="searxng")
    first.close()

    # 新实例 = 新进程的等价物：快照必须还在
    second = SessionStore(db)
    snapshot = second.get("s_1")
    assert snapshot is not None and snapshot.query == "查询"
    assert snapshot.sources[0].url == "https://a.test"
    second.close()


def test_favicon_is_cached_after_first_fetch(client: TestClient, tmp_path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    from app.core.fetch import SafeFetcher

    fetcher = SafeFetcher(
        timeout=0.5,
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"],
    )
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    try:
        first = client.get("/api/favicon", params={"host": "example.com"})
        second = client.get("/api/favicon", params={"host": "example.com"})
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    assert second.status_code == 200
    assert calls["n"] == 1, "第二次应命中磁盘缓存，不再请求上游"


def test_favicon_rejects_bad_host(client: TestClient) -> None:
    assert client.get("/api/favicon", params={"host": "http://evil/x"}).status_code == 400
    assert client.get("/api/favicon", params={"host": "127.0.0.1"}).status_code == 400


@pytest.mark.parametrize("legacy_cached", [False, True])
def test_favicon_does_not_serve_svg(client: TestClient, tmp_path, monkeypatch, legacy_cached) -> None:
    from app.core.favicon import FaviconCache
    from app.core.fetch import SafeFetcher

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>void 0</script></svg>'
    fetcher = SafeFetcher(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            200, content=svg, headers={"content-type": "image/svg+xml"}
        )),
        resolver=lambda host: ["93.184.216.34"],
    )
    cache = FaviconCache(tmp_path, fetcher)
    if legacy_cached:
        base = cache._base("example.com")
        base.with_suffix(".bin").write_bytes(svg)
        base.with_suffix(".json").write_text(
            json.dumps({"content_type": "image/svg+xml", "ts": int(time.time())}), encoding="utf-8"
        )
    monkeypatch.setattr(assets, "get_favicon_cache", lambda: cache)
    monkeypatch.setitem(app.dependency_overrides, get_fetcher, lambda: fetcher)
    assert client.get("/api/favicon", params={"host": "example.com"}).status_code == 404


def test_import_job_reports_progress(client: TestClient) -> None:
    html = (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>"
        + "".join(
            f'<DT><A HREF="https://import.test/{index}" ADD_DATE="1700000000">{index}</A>'
            for index in range(60)
        )
        + "</DL><p>"
    )
    started = client.post(
        "/api/bookmarks/import/jobs",
        files={"file": ("bookmarks.html", html.encode(), "text/html")},
    )
    assert started.status_code == 200
    job_id = started.json()["id"]

    import time as _time

    for _ in range(50):
        job = client.get(f"/api/bookmarks/import/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        _time.sleep(0.05)

    assert job["state"] == "done", job
    assert job["created"] == 60
    assert job["processed"] == job["total"] == 60
    assert client.get("/api/bookmarks/import/jobs/nope").status_code == 404


def test_metrics_endpoint_counts_requests(client: TestClient) -> None:
    client.get("/api/health")
    payload = client.get("/api/metrics").json()
    assert payload["window"] >= 1
    assert "p95_ms" in payload
    assert "/api/health" in payload["groups"] or "/api/other" in payload["groups"]


async def test_summary_metrics_wait_until_response_finishes(monkeypatch) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()

    class PendingSummary:
        model = "pending-summary"

        async def stream(self, snapshot):
            started.set()
            await finish.wait()
            yield "总结 [1]"

    monkeypatch.setattr(metrics, "_METRICS", metrics.Metrics())
    monkeypatch.setitem(app.dependency_overrides, get_summarizer, PendingSummary)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as api:
        search = await api.post("/api/search", json={"q": "python 文档"})
        sid = search.raise_for_status().json()["meta"]["sid"]
        pending = asyncio.create_task(api.get("/api/summarize", params={"sid": sid}))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            before = (await api.get("/api/metrics")).json()
            assert "/api/summarize" not in before["groups"]
        finally:
            finish.set()
            response = await pending
        assert "event: done" in response.text
        after = (await api.get("/api/metrics")).json()["groups"]["/api/summarize"]
        assert after["count"] == 1 and after["errors"] == 0
