"""M4 正文提取与单页总结。"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.extract import extract_article
from app.core.fetch import SafeFetcher
from app.core.llm import LLMTimeout
from app.core.summarize import get_summarizer
from app.deps import get_fetcher
from app.main import app

ARTICLE_HTML = """<html><head><title>异步编程入门</title>
<meta name="author" content="张三">
<meta property="article:published_time" content="2026-09-01">
</head><body>
<nav>首页 目录 关于</nav>
<script>window.ads = 1;</script>
<article>
<h1>异步编程入门</h1>
<p>事件循环是 asyncio 的核心，它负责调度协程与回调，并在 IO 等待时切换任务。</p>
<p>协程通过 await 让出控制权，避免线程阻塞；任务调度器会在就绪队列里挑选下一个协程继续执行。</p>
<p>实践上应避免在协程中执行同步阻塞调用，否则整个事件循环都会被拖住，延迟明显上升。</p>
</article>
<footer>版权所有</footer>
</body></html>"""


def test_extract_keeps_article_drops_navigation() -> None:
    article = extract_article(ARTICLE_HTML, "https://example.com/a")
    assert article.title == "异步编程入门"
    assert article.byline == "张三"
    assert article.published == "2026-09-01"
    assert "事件循环是 asyncio 的核心" in article.text
    assert "首页 目录" not in article.text
    assert "window.ads" not in article.text
    assert article.word_count > 30
    assert article.read_minutes >= 1
    assert article.content_hash.startswith("sha1:")
    assert article.extractor in ("stdlib", "trafilatura")


def test_extract_drops_navigation_breadcrumb() -> None:
    html = (
        "<html><body><div>Navigation index modules | next | previous | Python » 3.15.2 » Library</div>"
        "<p>. 事件循环负责调度协程，并在等待 IO 时切换任务。</p>"
        "<p>. 协程通过 await 让出控制权，避免阻塞线程。</p></body></html>"
    )
    article = extract_article(html, "https://example.com/nav")
    assert "Navigation" not in article.text
    assert article.text.startswith(".")


def test_extract_survives_void_tags() -> None:
    html = (
        "<html><body><form><label>搜索</label><input type=\"text\" name=\"q\"></form>"
        "<article><p>" + "正文段落内容，包含 asyncio 事件循环的说明。" * 4 + "</p></article></body></html>"
    )
    article = extract_article(html, "https://example.com/void")
    assert "asyncio" in article.text
    assert len(article.text) > 60


def test_extract_is_deterministic() -> None:
    first = extract_article(ARTICLE_HTML, "https://example.com/a")
    second = extract_article(ARTICLE_HTML, "https://example.com/a")
    assert first.content_hash == second.content_hash
    assert first.text == second.text


def test_extract_handles_empty_html() -> None:
    article = extract_article("<html><body></body></html>", "https://example.com/empty")
    assert article.text == ""
    assert article.read_minutes == 0


def make_public_fetcher(handler) -> SafeFetcher:
    return SafeFetcher(
        timeout=0.5,
        max_bytes=200_000,
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"],
    )


@pytest.fixture()
def public_html():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ARTICLE_HTML, headers={"content-type": "text/html"})

    fetcher = make_public_fetcher(handler)
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    yield fetcher
    app.dependency_overrides.pop(get_fetcher, None)


def test_page_summarize_returns_structure(client: TestClient, public_html) -> None:
    response = client.post("/api/page/summarize", json={"url": "https://example.com/a"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "异步编程入门"
    assert body["read_minutes"] >= 1
    assert body["extractor"] in ("stdlib", "trafilatura")
    assert body["summary"]["one_liner"]
    assert isinstance(body["summary"]["bullets"], list)
    assert body["model"] == "stub-extractive"


def test_page_summarize_blocks_private_target(client: TestClient) -> None:
    response = client.post("/api/page/summarize", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert response.status_code == 403
    assert "非公网" in response.json()["detail"] or "内网" in response.json()["detail"]


def test_page_summarize_reports_upstream_failure(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    app.dependency_overrides[get_fetcher] = lambda: make_public_fetcher(handler)
    try:
        response = client.post("/api/page/summarize", json={"url": "https://example.com/missing"})
    finally:
        app.dependency_overrides.pop(get_fetcher, None)
    assert response.status_code == 502
    assert "404" in response.json()["detail"]


def test_page_summarize_rejects_thin_content(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html><body><p>太短</p></body></html>", headers={"content-type": "text/html"}
        )

    app.dependency_overrides[get_fetcher] = lambda: make_public_fetcher(handler)
    try:
        response = client.post("/api/page/summarize", json={"url": "https://example.com/thin"})
    finally:
        app.dependency_overrides.pop(get_fetcher, None)
    assert response.status_code == 422
    assert "正文过短" in response.json()["detail"]


def test_page_summarize_reports_model_timeout(client: TestClient, public_html) -> None:
    class SlowModel:
        model = "test"

        async def stream(self, snapshot):
            raise LLMTimeout("等待模型超时")
            yield ""

    app.dependency_overrides[get_summarizer] = SlowModel
    try:
        response = client.post("/api/page/summarize", json={"url": "https://example.com/a"})
    finally:
        app.dependency_overrides.pop(get_summarizer, None)
    assert response.status_code == 504
    assert response.json()["detail"] == "等待模型超时"


def test_page_summary_preserves_points_from_unformatted_model_output(client: TestClient, public_html) -> None:
    class ParagraphModel:
        model = "test"

        async def stream(self, snapshot):
            yield "协程适合并发 I/O。事件循环调度任务。await 可以让出控制权。"

    app.dependency_overrides[get_summarizer] = ParagraphModel
    try:
        response = client.post("/api/page/summarize", json={"url": "https://example.com/a"})
    finally:
        app.dependency_overrides.pop(get_summarizer, None)
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["one_liner"] == "协程适合并发 I/O。"
    assert summary["bullets"] == ["事件循环调度任务。", "await 可以让出控制权。"]


def _parse_sse(text: str):
    import json

    events = []
    for block in text.split("\n\n"):
        name, payload = "", {}
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                payload = json.loads(line[5:].strip())
        if name:
            events.append((name, payload))
    return events


def test_full_mode_uses_fetched_content(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ARTICLE_HTML, headers={"content-type": "text/html"})

    app.dependency_overrides[get_fetcher] = lambda: make_public_fetcher(handler)
    try:
        sid = client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["sid"]
        with client.stream("GET", "/api/summarize", params={"sid": sid, "mode": "full"}) as response:
            events = _parse_sse("".join(response.iter_text()))
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    meta = events[0][1]
    assert meta["mode"] == "full"
    assert meta["fetched"] >= 1
    assert meta["degraded"] is False
    done = dict(events)["done"]
    assert done["tokens"] > 0


def test_full_mode_degrades_when_all_fetches_fail(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    app.dependency_overrides[get_fetcher] = lambda: make_public_fetcher(handler)
    try:
        sid = client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["sid"]
        with client.stream("GET", "/api/summarize", params={"sid": sid, "mode": "full"}) as response:
            events = _parse_sse("".join(response.iter_text()))
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    meta = events[0][1]
    assert meta["failed"] >= 1
    assert meta["degraded"] is True
    assert dict(events)["done"]["partial"] is True
    # 降级后仍然有正文输出（用回原摘要）
    assert any(name == "token" for name, _ in events)


def test_full_mode_labels_each_citation_when_some_fetches_fail(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "fastapi.tiangolo.com":
            return httpx.Response(503)
        return httpx.Response(200, text=ARTICLE_HTML, headers={"content-type": "text/html"})

    app.dependency_overrides[get_fetcher] = lambda: make_public_fetcher(handler)
    try:
        sid = client.post("/api/search", json={"q": "python 文档"}).json()["meta"]["sid"]
        response = client.get("/api/summarize", params={"sid": sid, "mode": "full"})
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    events = _parse_sse(response.text)
    meta = events[0][1]
    assert meta["fetched"] == 4 and meta["failed"] == 1 and meta["degraded"] is True
    materials = {payload["domain"]: payload["material"] for name, payload in events if name == "cite"}
    assert materials["fastapi.tiangolo.com"] == "snippet" and "full" in materials.values()
    assert dict(events)["done"]["partial"] is True
