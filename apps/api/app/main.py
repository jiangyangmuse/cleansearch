"""FastAPI 入口：API + 同源托管前端构建产物（发布形态）。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import REPO_ROOT, Settings, get_settings, reload_settings
from app.core.errors import SearchError
from app.core.metrics import RequestMetricsMiddleware, get_metrics
from app.core.vitals import record_vitals, vitals_snapshot
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
from app.schemas import HealthResponse, SearchMeta

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
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
HOST_AUTHORITY = re.compile(r"(?:\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::[0-9]{1,5})?", re.I | re.ASCII)


def _host_allowed(host_header: str, allowed: tuple[str, ...]) -> bool:
    """回环永远放行；其余主机必须在 ALLOWED_HOSTS 里显式列出（手机/局域网用途）。"""
    if not HOST_AUTHORITY.fullmatch(host_header):
        return False
    try:
        authority = urlsplit(f"http://{host_header}")
        port = authority.port
    except ValueError:
        return False
    if port == 0:
        return False
    hostname = authority.hostname
    return hostname in LOOPBACK_HOSTS or hostname in allowed


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

# 前端依赖的接口契约版本：新增/改变前端读取的能力时 +1，前端低于它就提示重启服务。
API_VERSION = 2
# 能力名 → HTTP 方法及路径。前端按名核对，缺哪项就禁用对应功能。
CAPABILITY_ROUTES = {
    "filters": ("POST", "/api/search"),
    "bookmark_status": ("GET", "/api/bookmarks/status"),
    "vitals": ("POST", "/api/metrics/vitals"),
    "model_test": ("POST", "/api/settings/models/test"),
    "opensearch": ("GET", "/opensearch.xml"),
}


def _capabilities() -> dict[str, bool]:
    """按实际注册的路由回答"有哪些能力"，避免声明与实现各写一套。"""
    endpoints = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or ())
    }
    capabilities = {name: endpoint in endpoints for name, endpoint in CAPABILITY_ROUTES.items()}
    capabilities["filters"] = capabilities["filters"] and "filters" in SearchMeta.model_fields
    return capabilities


class VitalsSample(BaseModel):
    """前端上报的性能样本；字段都可缺省，单位统一为毫秒（CLS 为无量纲分数）。"""

    path: str = Field(default="/", max_length=200)
    lcp: float | None = Field(default=None, ge=0, le=600_000)
    cls: float | None = Field(default=None, ge=0, le=100)
    inp: float | None = Field(default=None, ge=0, le=600_000)
    ttfb: float | None = Field(default=None, ge=0, le=600_000)
    search_ms: float | None = Field(default=None, ge=0, le=600_000)
    panel_ms: float | None = Field(default=None, ge=0, le=600_000)


@app.get("/api/metrics")
def metrics_snapshot() -> dict:
    return {**get_metrics().snapshot(), "vitals": vitals_snapshot()}


@app.post("/api/metrics/vitals", status_code=204, include_in_schema=False)
def post_vitals(payload: VitalsSample) -> Response:
    """接收 Web Vitals 与搜索/面板耗时；只在内存留最近样本，不落盘。"""
    sample = payload.model_dump(exclude_none=True)
    path = sample.pop("path").split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"
    if not sample:
        raise HTTPException(status_code=422, detail="至少提供一项性能指标")
    if path not in {"/", "/r", "/bookmarks", "/settings", "/s", "/tools"}:
        path = "/"
    record_vitals({"path": path, **sample})
    return Response(status_code=204)


@app.middleware("http")
async def cross_origin_guard(request: Request, call_next):
    """跨域只放行书签写入，且必须带本地 token。

    bookmarklet 与浏览器扩展从任意页面发请求，无法靠 Origin 白名单；
    这里用 token 阻止「随便一个网页静默往你书签里塞东西」。
    """
    # 恶意域名即使重新解析到回环，也不能冒充同源页面读取 token。
    # 手机/局域网访问需在 ALLOWED_HOSTS 显式列出主机名，不做「任意 Host 都放行」。
    hosts = request.headers.getlist("host")
    if len(hosts) != 1 or not _host_allowed(hosts[0], get_settings().allowed_hosts):
        return _cross_origin_denied(
            "HOST_FORBIDDEN", "仅接受回环地址，或在 ALLOWED_HOSTS 中显式允许的主机", 403
        )

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
        db_path=str(current.db_path),
        version=__version__,
        api_version=API_VERSION,
        capabilities=_capabilities(),
        allowed_hosts=list(current.allowed_hosts),
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


@app.get("/opensearch.xml", include_in_schema=False)
def opensearch(request: Request) -> Response:
    origin = escape(str(request.base_url).rstrip("/"))
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n'
        '  <ShortName>CleanSearch</ShortName>\n'
        '  <Description>本机搜索与书签</Description>\n'
        '  <InputEncoding>UTF-8</InputEncoding>\n'
        f'  <Url type="text/html" template="{origin}/?q={{searchTerms}}"/>\n'
        '</OpenSearchDescription>\n',
        media_type="application/opensearchdescription+xml",
        headers={"Cache-Control": "no-store"},
    )


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
        if full_path in ("api", "go") or full_path.startswith(("api/", "go/")):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
        if full_path and candidate.is_file():
            headers = {"Cache-Control": "no-cache"} if full_path == "sw.js" else None
            return FileResponse(candidate, headers=headers)
        if full_path.startswith("assets/") or full_path in {
            "sw.js", "offline.html", "manifest.webmanifest", "favicon.svg",
            "icon-192.png", "icon-512.png", "icon-maskable-512.png",
        }:
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND"}})
        return FileResponse(index, headers={"Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"})


_mount_web()


def main() -> None:
    """本机启动：python -m app.main"""
    import uvicorn

    current = get_settings()
    uvicorn.run("app.main:app", host=current.api_host, port=current.api_port, reload=False)


if __name__ == "__main__":
    main()
