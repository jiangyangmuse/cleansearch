"""FastAPI 入口：API + 同源托管前端构建产物（发布形态）。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import REPO_ROOT, Settings, get_settings, reload_settings
from app.core.errors import SearchError
from app.core.metrics import RequestMetricsMiddleware, get_metrics
from app.core.tokens import read_api_token, token_matches
from app.routers import assets as assets_router
from app.routers import ai_tools as ai_tools_router
from app.routers import bookmarks as bookmarks_router
from app.routers import engines as engines_router
from app.routers import go as go_router
from app.routers import page as page_router
from app.routers import search as search_router
from app.routers import summarize as summarize_router
from app.routers import tools as tools_router
from app.schemas import HealthResponse

settings: Settings = get_settings()

app = FastAPI(
    title="CleanSearch API",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(search_router.router)
app.include_router(bookmarks_router.router)
app.include_router(engines_router.router)
app.include_router(go_router.router)
app.include_router(page_router.router)
app.include_router(summarize_router.router)
app.include_router(tools_router.router)
app.include_router(assets_router.router)
app.include_router(ai_tools_router.router)


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "content-type,x-cs-token",
    "Access-Control-Allow-Methods": "POST",
    "Access-Control-Max-Age": "600",
}
BOOKMARK_WRITE_PATH = "/api/bookmarks"
LOOPBACK_HOST = re.compile(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?", re.I)


def _origin_of(url) -> str:
    parsed = urlsplit(url)
    default_port = 443 if parsed.scheme == "https" else 80
    return f"{parsed.scheme}://{(parsed.hostname or '')}:{parsed.port or default_port}"


def _is_cross_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    if origin == "null":
        return True
    try:
        return _origin_of(origin) != _origin_of(str(request.base_url))
    except ValueError:
        return True


def _cross_origin_denied(code: str, message: str, status: int, *, cors: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "retryable": False}},
        headers=CORS_HEADERS if cors else None,
    )


app.add_middleware(RequestMetricsMiddleware)


@app.get("/api/metrics")
def metrics_snapshot() -> dict:
    return get_metrics().snapshot()


@app.middleware("http")
async def cross_origin_guard(request: Request, call_next):
    """跨域只放行书签写入，且必须带本地 token。

    bookmarklet 与浏览器扩展从任意页面发请求，无法靠 Origin 白名单；
    这里用 token 阻止「随便一个网页静默往你书签里塞东西」。
    """
    # 恶意域名即使重新解析到回环，也不能冒充同源页面读取 token。
    if not LOOPBACK_HOST.fullmatch(request.headers.get("host", "")):
        return _cross_origin_denied("HOST_FORBIDDEN", "仅接受本机回环地址访问", 403)

    cross_origin = _is_cross_origin(request)
    supplied = request.headers.get("x-cs-token")
    if not cross_origin and supplied is None:
        return await call_next(request)

    preflight = cross_origin and request.method == "OPTIONS"
    method = request.headers.get("access-control-request-method") if preflight else request.method
    if request.url.path != BOOKMARK_WRITE_PATH or method != "POST":
        return _cross_origin_denied(
            "CORS_FORBIDDEN", "该接口不允许跨域访问", 403
        )

    if preflight:
        return Response(status_code=204, headers=CORS_HEADERS)

    try:
        expected = await run_in_threadpool(read_api_token, get_settings().api_token_path) if supplied else None
    except (OSError, UnicodeError):
        return _cross_origin_denied("TOKEN_UNAVAILABLE", "本地 token 无法读取", 503, cors=cross_origin)
    if not token_matches(supplied, expected):
        return _cross_origin_denied(
            "TOKEN_REQUIRED",
            "跨域写书签需要 X-CS-Token，可在 /tools 页面获取",
            401,
            cors=cross_origin,
        )

    request.state.external_bookmark = True
    response = await call_next(request)
    if cross_origin:
        response.headers.update(CORS_HEADERS)
    return response


@app.exception_handler(SearchError)
async def _search_error_handler(_: Request, exc: SearchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    current = reload_settings()
    index = current.web_dist / "index.html"
    return HealthResponse(
        status="ok",
        provider=current.provider,
        searxng_url=current.searxng_url,
        web_dist=str(current.web_dist),
        web_built=index.is_file(),
        blocklist_rules=_blocklist_rules(current.blocklist_path, current.feed_output_path),
        llm_provider=current.llm_provider,
        llm_model="stub-extractive" if current.llm_provider == "stub" else current.llm_model,
        bookmarks=_bookmark_count(current.db_path),
        version=__version__,
    )


def _bookmark_count(path: Path) -> int:
    if not path.is_file():
        return 0
    import sqlite3

    try:
        with sqlite3.connect(str(path)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0])
    except sqlite3.Error:
        return 0


def _blocklist_rules(path: Path, feed_path: Path | None = None) -> int:
    """基础黑名单 + 可刷新 feed 的条数之和。"""
    total = 0
    for candidate in (path, feed_path):
        if candidate is None:
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        total += sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))
    return total


def _mount_web() -> None:
    """发布形态：FastAPI 同源提供 Vite 产物，并支持前端路由直接刷新。"""
    dist = get_settings().web_dist
    index = dist / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        async def _missing_frontend() -> JSONResponse:
            return JSONResponse(
                status_code=200,
                content={
                    "service": "cleansearch-api",
                    "hint": "前端产物不存在，先构建：npm --prefix apps/web run build（或用 npm --prefix apps/web run dev 走 Vite 代理）",
                    "web_dist": str(dist),
                },
            )
        return

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def _spa(full_path: str) -> Response:
        if full_path.startswith(("api/", "go/")):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"})


_mount_web()


def main() -> None:
    """本机启动：python -m app.main"""
    import uvicorn

    current = get_settings()
    uvicorn.run("app.main:app", host=current.api_host, port=current.api_port, reload=False)


if __name__ == "__main__":
    main()
