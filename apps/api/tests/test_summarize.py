"""M2 侧栏总结：SSE 事件序列、引用绑定、超时与错误、快照生命周期。"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.llm import LLMBadResponse, LLMTimeout, OpenAICompatibleClient
from app.core.session_store import SessionStore, Source
from app.core.summarize import StubSummarizer, get_summarizer
from app.main import app


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        name = ""
        payload: dict = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
        if name:
            events.append((name, payload))
    return events


def search(client: TestClient, q: str = "python 文档") -> dict:
    response = client.post("/api/search", json={"q": q})
    assert response.status_code == 200, response.text
    return response.json()


def stream_summary(client: TestClient, sid: str, mode: str = "fast") -> httpx.Response:
    return client.get("/api/summarize", params={"sid": sid, "mode": mode})


def test_summarize_stream_has_stable_citations(client: TestClient) -> None:
    body = search(client)
    sid = body["meta"]["sid"]
    result_ids = {
        item["id"]
        for group in body["groups"].values()
        for item in group
    }

    with client.stream("GET", "/api/summarize", params={"sid": sid}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse("".join(response.iter_text()))

    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names.count("cite") >= 1
    assert "token" in names and "done" in names
    assert "error" not in names

    meta = events[0][1]
    cites = [payload for name, payload in events if name == "cite"]
    assert meta["model"] == "stub-extractive"
    assert meta["sources"] == len(cites)
    assert [cite["i"] for cite in cites] == list(range(1, len(cites) + 1))
    # 引用绑定的必须是这次搜索结果里真实存在的 result_id
    assert {cite["result_id"] for cite in cites} <= result_ids

    text = "".join(payload["t"] for name, payload in events if name == "token")
    assert "[1]" in text and len(text) > 40
    done = dict(events)["done"]
    assert done["partial"] is False and done["tokens"] > 0 and done["ms"] >= 0


def test_unknown_sid_returns_404(client: TestClient) -> None:
    response = client.get("/api/summarize", params={"sid": "s_dead", "mode": "fast"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_mode_unknown_is_rejected(client: TestClient) -> None:
    sid = search(client)["meta"]["sid"]
    response = client.get("/api/summarize", params={"sid": sid, "mode": "turbo"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MODE_UNSUPPORTED"


def test_empty_search_has_no_snapshot(client: TestClient) -> None:
    body = client.post("/api/search", json={"q": "test", "opts": {"fixture": "empty"}}).json()
    assert body["meta"]["status"] == "empty"
    response = client.get("/api/summarize", params={"sid": body["meta"]["sid"]})
    assert response.status_code == 404


class _TimeoutSummarizer:
    model = "fake-timeout"

    async def stream(self, snapshot):
        raise LLMTimeout("模型 0.1s 内未返回")
        yield ""  # pragma: no cover


def test_llm_timeout_emits_error_event(client: TestClient) -> None:
    sid = search(client)["meta"]["sid"]
    app.dependency_overrides[get_summarizer] = lambda: _TimeoutSummarizer()
    try:
        with client.stream("GET", "/api/summarize", params={"sid": sid}) as response:
            events = parse_sse("".join(response.iter_text()))
    finally:
        app.dependency_overrides.pop(get_summarizer, None)

    names = [name for name, _ in events]
    assert "error" in names and "done" not in names
    error = dict(events)["error"]
    assert error["code"] == "LLM_TIMEOUT"
    assert error["retryable"] is True
    # 出错前已经发出的 meta 与 cite 保留了，前端可以继续展示来源
    assert names.count("cite") >= 1


def test_unexpected_summary_error_does_not_expose_request_details(client: TestClient) -> None:
    class BrokenSummarizer:
        model = "fake-broken"

        async def stream(self, snapshot):
            raise RuntimeError("private upstream request detail")
            yield ""  # pragma: no cover

    sid = search(client)["meta"]["sid"]
    app.dependency_overrides[get_summarizer] = BrokenSummarizer
    try:
        response = stream_summary(client, sid)
    finally:
        app.dependency_overrides.pop(get_summarizer, None)

    events = dict(parse_sse(response.text))
    assert events["error"]["code"] == "LLM_ERROR"
    assert "done" not in events and "private upstream request detail" not in response.text


def test_stub_summarizer_stays_within_citation_range() -> None:
    from app.core.session_store import Snapshot

    sources = [
        Source(result_id=f"r_{i}", url=f"https://e{i}.test/a", title=f"标题 {i}",
               snippet=f"摘要内容 {i}。", domain=f"e{i}.test")
        for i in range(1, 4)
    ]
    snapshot = Snapshot(sid="s_x", query="测试", sources=sources, provider="fixture")
    text = StubSummarizer.compose(snapshot)
    assert "[1]" in text and "[3]" in text
    assert "[4]" not in text
    assert "分歧：" in text


def test_session_store_ttl_and_capacity(tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions.db", ttl_seconds=1, capacity=2)
    src = [Source("r_1", "https://a.test", "a", "", "a.test")]
    store.put("s_1", "q", src)
    assert store.get("s_1") is not None

    # 容量淘汰：最早的被挤掉
    store.put("s_2", "q", src)
    store.put("s_3", "q", src)
    assert len(store) == 2
    assert store.get("s_1") is None and store.get("s_3") is not None

    # TTL：直接改库里的创建时间模拟过期
    import sqlite3

    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE search_sessions SET created_at = ? WHERE sid = 's_3'", (int(time.time()) - 5,))
    assert store.get("s_3") is None


async def test_openai_client_streams_tokens() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        body = (
            'data: {"choices":[{"delta":{"reasoning":"内部推理"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"第一"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"段"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    client = OpenAICompatibleClient(
        base_url="http://llm.test/v1",
        api_key="k",
        model="qwen3:8b",
        timeout=2.0,
        transport=httpx.MockTransport(handler),
        reasoning_effort="none",
    )
    tokens = [token async for token in client.stream("系统", "用户")]
    assert tokens == ["第一", "段"]
    assert captured["url"] == "http://llm.test/v1/chat/completions"
    assert captured["body"]["stream"] is True
    assert captured["body"]["reasoning_effort"] == "none"


@pytest.mark.parametrize(("status", "code"), [(401, "LLM_AUTH_FAILED"), (402, "LLM_INSUFFICIENT_BALANCE")])
async def test_openai_client_reports_credentials_and_balance_errors(status: int, code: str) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": "private provider detail"})
    )
    client = OpenAICompatibleClient("http://llm.test/v1", "k", "m", 2, transport)

    with pytest.raises(LLMBadResponse) as caught:
        [token async for token in client.stream("s", "u")]

    assert caught.value.code == code and caught.value.retryable is False
    assert "private provider detail" not in caught.value.message


@pytest.mark.parametrize("body", [
    'data: {"choices":[{"delta":{"reasoning":"thinking only"}}]}\n\ndata: [DONE]\n\n',
    'data: {"choices":[{"delta":{"content":"unfinished"}}]}\n\n',
    'data: {"error":{"message":"upstream failure"}}\n\n',
])
async def test_openai_client_rejects_unsuccessful_stream(body: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    client = OpenAICompatibleClient("http://llm.test/v1", "k", "m", 2, transport)

    with pytest.raises(LLMBadResponse):
        [token async for token in client.stream("s", "u")]


async def test_openai_client_times_out_waiting_for_first_answer() -> None:
    closed = False

    class ReasoningStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b'data: {"choices":[{"delta":{"reasoning":"still thinking"}}]}\n\n'
                await asyncio.sleep(0.01)

        async def aclose(self):
            nonlocal closed
            closed = True

    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=ReasoningStream()))
    client = OpenAICompatibleClient("http://llm.test/v1", "k", "m", 0.05, transport)

    with pytest.raises(LLMTimeout):
        [token async for token in client.stream("s", "u")]
    assert closed


async def test_openai_client_timeout_is_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = OpenAICompatibleClient(
        base_url="http://llm.test/v1", api_key="k", model="m", timeout=0.1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMTimeout):
        [token async for token in client.stream("s", "u")]


async def test_openai_client_deadline_includes_wait_for_headers() -> None:
    cancelled = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"too late"}}]}\n\ndata: [DONE]\n\n'
        )

    client = OpenAICompatibleClient("http://llm.test/v1", "k", "m", 0.05, httpx.MockTransport(handler))
    with pytest.raises(LLMTimeout):
        [token async for token in client.stream("s", "u")]
    assert cancelled


def test_stub_single_source_quotes_sentences() -> None:
    from app.core.session_store import Snapshot, Source
    from app.core.summarize import StubSummarizer

    text = (
        "事件循环负责调度协程与回调。协程通过 await 让出控制权，避免线程阻塞。"
        "实践上应避免在协程里做同步阻塞调用，否则会拖慢整个事件循环。"
    ) * 6
    snapshot = Snapshot(
        sid="page",
        query="asyncio 文档",
        sources=[Source("r_1", "https://e.test/a", "asyncio 文档", text, "e.test")],
        provider="page",
    )
    summary = StubSummarizer.compose(snapshot)
    assert "单篇原文" in summary
    assert summary.count("- ") >= 3
    assert "材料指向 1 条结果" not in summary
