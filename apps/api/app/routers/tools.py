"""一键添加辅助接口：生成 bookmarklet 代码（同源可读，跨域被中间件挡住）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.feeds import refresh as refresh_feeds
from app.core.fetch import SafeFetcher
from app.core.tokens import get_api_token
from app.deps import get_fetcher

router = APIRouter(prefix="/api", tags=["tools"])


def build_bookmarklet(base_url: str, token: str) -> str:
    """单行 javascript: URL，在任意页面执行时把当前页写入本地书签。"""
    return (
        "javascript:(async()=>{"
        f"const API={json.dumps(base_url)},TOKEN={json.dumps(token)};"
        "if(location.protocol!=='http:'&&location.protocol!=='https:'){alert('只能收藏 HTTP(S) 页面');return}"
        "const data={url:location.href,title:[...document.title].slice(0,512).join('')};"
        "try{"
        "const r=await fetch(API+'/api/bookmarks',{method:'POST',redirect:'error',"
        "credentials:'omit',targetAddressSpace:'loopback',"
        "headers:{'Content-Type':'application/json','X-CS-Token':TOKEN},"
        "body:JSON.stringify(data)});"
        "const j=await r.json().catch(()=>({}));"
        "alert(r.ok?(j.deduplicated?'已在书签里':'已收藏到 CleanSearch'):"
        "('保存失败：'+(j.error?.message||(typeof j.detail==='string'?j.detail:r.status))));"
        "}catch{if(confirm('当前网页无法直连 CleanSearch，是否打开本机书签页并预填？'))"
        "location.assign(API+'/bookmarks?'+new URLSearchParams(data))}"
        "})()"
    )


@router.get("/tools/bookmarklet")
def bookmarklet(request: Request, response: Response) -> dict:
    try:
        token = get_api_token(get_settings().api_token_path)
    except (OSError, UnicodeError) as exc:
        raise HTTPException(status_code=503, detail="本地 token 无法读取或创建") from exc
    response.headers["Cache-Control"] = "no-store"
    base = f"{request.url.scheme}://{request.url.netloc}"
    return {
        "api": base,
        "token": token,
        "code": build_bookmarklet(base, token),
        "hint": "把这个链接拖到书签栏；在任意页面点一下就会保存当前页。",
    }


class RefreshRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=10)


@router.post("/tools/refresh-feeds")
async def refresh_blacklist(
    payload: RefreshRequest | None = None,
    fetcher: SafeFetcher = Depends(get_fetcher),
) -> dict:
    """拉取无 key 的纯文本黑名单（如 OpenPhish），合并进本地 feed 文件。

    GSB / URLhaus 需要 API key，未接入；此处只处理能直接下载的源。
    """
    settings = get_settings()
    urls = payload.urls if payload and payload.urls else list(settings.feed_urls)
    if not urls:
        raise HTTPException(
            status_code=400,
            detail="未配置 FEED_URLS；可在请求体传 urls，或设置环境变量 FEED_URLS",
        )
    # feed 文件常有几 MB，给它们更长的超时；其余限额不变
    feed_fetcher = fetcher.clone_with_timeout(max(10.0, fetcher.timeout))
    results = await refresh_feeds(urls, settings.feed_output_path, feed_fetcher)
    ok = [item for item in results if item.ok]
    return {
        "output": str(settings.feed_output_path),
        "sources": [item.__dict__ for item in results],
        "total_entries": sum(item.entries for item in ok),
        "ok": bool(ok),
    }