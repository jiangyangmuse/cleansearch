"""GET /api/summarize —— 侧栏流式总结（SSE）。

事件：meta → cite×N → token×M → done；失败发 error 并结束，不删除快照。
"""

from __future__ import annotations

import json
import time
from contextlib import aclosing

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.fetch import SafeFetcher
from app.core.llm import LLMError
from app.core.session_store import SessionStore, get_session_store
from app.core.summarize import (
    FULL_MAX_SOURCES,
    MAX_SOURCES,
    Summarizer,
    enrich_with_full_text,
    get_summarizer,
)
from app.deps import get_fetcher

router = APIRouter(prefix="/api", tags=["summarize"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error(status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "retryable": retryable}},
    )


@router.get("/summarize", response_model=None)
async def summarize(
    sid: str,
    mode: str = "fast",
    store: SessionStore = Depends(get_session_store),
    summarizer: Summarizer = Depends(get_summarizer),
    fetcher: SafeFetcher = Depends(get_fetcher),
) -> StreamingResponse | JSONResponse:
    if mode not in ("fast", "full"):
        return _error(400, "MODE_UNSUPPORTED", "mode 只支持 fast 或 full")

    snapshot = store.get(sid)
    if snapshot is None:
        return _error(404, "SESSION_NOT_FOUND", "该搜索快照已过期，请重新搜索后生成总结")
    if not snapshot.sources:
        return _error(409, "SESSION_EMPTY", "本次搜索没有可用于总结的结果")

    async def generator():
        started = time.perf_counter()
        materials = snapshot
        stats = {"fetched": 0, "failed": 0, "truncated": 0}
        if mode == "full":
            materials, stats = await enrich_with_full_text(snapshot, fetcher, FULL_MAX_SOURCES)
        sources = materials.sources[:MAX_SOURCES]
        partial = bool(stats["failed"] or stats["truncated"])
        yield sse(
            "meta",
            {
                "model": summarizer.model,
                "sources": len(sources),
                "mode": mode,
                "sid": sid,
                "query": snapshot.query,
                "fetched": stats["fetched"],
                "failed": stats["failed"],
                "truncated": stats["truncated"],
                "degraded": partial,
            },
        )
        for index, source in enumerate(sources, 1):
            yield sse(
                "cite",
                {
                    "i": index,
                    "result_id": source.result_id,
                    "title": source.title,
                    "url": source.url,
                    "domain": source.domain,
                    "material": source.material,
                },
            )

        tokens = 0
        try:
            async with aclosing(summarizer.stream(materials)) as stream:
                async for token in stream:
                    if not token:
                        continue
                    tokens += 1
                    yield sse("token", {"t": token})
        except LLMError as exc:
            yield sse(
                "error",
                {"code": exc.code, "message": exc.message, "retryable": exc.retryable},
            )
            return
        except Exception as exc:  # 兜底：任何未预期异常都要让前端进入 error 态
            yield sse(
                "error",
                {"code": "LLM_ERROR", "message": str(exc)[:200], "retryable": True},
            )
            return

        yield sse(
            "done",
            {
                "ms": int((time.perf_counter() - started) * 1000),
                "tokens": tokens,
                "partial": partial,
                "mode": mode,
            },
        )

    return StreamingResponse(generator(), media_type="text/event-stream", headers=SSE_HEADERS)
