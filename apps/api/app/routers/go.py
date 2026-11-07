"""GET /go —— 可疑链接的确认中转页。

签名用本地 token 做 HMAC key，页面上补域名与风险说明，避免直接跳到可疑站点。
"""

from __future__ import annotations

from html import escape
from dataclasses import replace
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.core.normalize import is_renderable_url
from app.core.redirect import verify_go
from app.core.rdap import AGE_PENALTY, AGE_REASON, DomainAgeStore, cached_age
from app.core.safety import SafetyScorer
from app.core.tokens import get_api_token
from app.routers.search import get_age_store, get_safety

router = APIRouter(tags=["go"])

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>访问确认 · {host}</title>
<style>
 body{{margin:0;padding:48px 20px;font:15px/1.6 "Segoe UI","PingFang SC",system-ui,sans-serif;background:#fbfbf9;color:#1d2321}}
 main{{max-width:560px;margin:0 auto;background:#fff;border:1px solid #e3e7e3;border-radius:12px;padding:28px}}
 h1{{margin:0 0 8px;font-size:20px}}
 .host{{font-family:ui-monospace,monospace;background:#eaf2ed;color:#2f6f4f;padding:2px 6px;border-radius:4px}}
 ul{{margin:12px 0;padding-left:20px;color:#66716c}}
 a.go{{display:inline-block;margin-top:18px;padding:9px 16px;background:#2f6f4f;color:#fff;border-radius:8px;text-decoration:none;font-weight:600}}
 a.back{{margin-left:12px;color:#66716c}}
 p{{color:#66716c}}
</style></head><body><main>
<h1>这条结果有风险，确认后再打开</h1>
<p>目标站点：<span class="host">{host}</span></p>
<ul>{reasons}</ul>
<p>风险分 {risk:.2f}。CleanSearch 不会替你判断它是否安全。</p>
<a class="go" href="{url}" target="_blank" rel="noopener noreferrer nofollow">仍要访问</a>
<a class="back" href="/">返回搜索</a>
</main></body></html>"""


@router.get("/go", response_class=HTMLResponse)
async def go(
    u: str, sig: str = "", safety: SafetyScorer = Depends(get_safety),
    age_store: DomainAgeStore | None = Depends(get_age_store),
) -> HTMLResponse:
    secret = get_api_token(get_settings().api_token_path)
    url = verify_go(u, sig, secret)
    if not url or not is_renderable_url(url):
        return HTMLResponse(
            status_code=403,
            content="<h1>链接无效</h1><p>签名校验失败，可能是链接被改动。</p>",
        )
    report = safety.evaluate(url)
    host = urlsplit(url).hostname or url
    if get_settings().rdap_enabled and age_store is not None and report.risk > 0:
        age = await run_in_threadpool(cached_age, host, age_store)
        if age is not None and age.fresh:
            report = replace(report, risk=round(min(1.0, report.risk + AGE_PENALTY), 3), reasons=(*report.reasons, AGE_REASON))
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in report.reasons)
    if not reasons:
        reasons = "<li>启发式检查未给出具体原因</li>"
    return HTMLResponse(
        PAGE.format(host=escape(host), reasons=reasons, risk=report.risk, url=escape(url, quote=True))
    )
