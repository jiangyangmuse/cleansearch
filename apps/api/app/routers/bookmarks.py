"""书签与分组：CRUD、搜索、Netscape HTML 导入导出（M3）。"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.core.fetch import FetchError, SafeFetcher
from app.db.repo import BookmarkError, BookmarkRepo
from app.deps import get_fetcher
from app.schemas import (
    Bookmark,
    BookmarkCaptureResult,
    BookmarkCreate,
    BookmarkGroup,
    BookmarkList,
    BookmarkSaveResult,
    BookmarkUpdate,
    GroupCreate,
    ImportResult,
)

router = APIRouter(prefix="/api", tags=["bookmarks"])
MAX_IMPORT_BYTES = 20 * 1024 * 1024
CHECK_CONCURRENCY = 5


class BookmarkCheckRequest(BaseModel):
    ids: list[Annotated[int, Field(ge=1, le=2**63 - 1)]] | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)


@lru_cache(maxsize=1)
def get_repo() -> BookmarkRepo:
    return BookmarkRepo(get_settings().db_path)


@router.get("/bookmarks", response_model=BookmarkList)
def list_bookmarks(
    q: str | None = Query(default=None, max_length=200),
    group: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=2**63 - 1),
    tag: str | None = Query(default=None, max_length=64),
    repo: BookmarkRepo = Depends(get_repo),
) -> BookmarkList:
    items, total = repo.page(q, group, limit, offset, tag)
    return BookmarkList(
        items=[Bookmark(**item) for item in items],
        groups=[BookmarkGroup(**group_item) for group_item in repo.groups()],
        tags=repo.tags(),
        total=total,
        fts=repo.fts_enabled,
    )


@router.post("/bookmarks", response_model=BookmarkSaveResult | BookmarkCaptureResult, status_code=201)
def create_bookmark(
    payload: BookmarkCreate,
    request: Request,
    response: Response,
    repo: BookmarkRepo = Depends(get_repo),
) -> BookmarkSaveResult | BookmarkCaptureResult:
    external = getattr(request.state, "external_bookmark", False)
    if external and payload.model_fields_set - {"url", "title"}:
        raise HTTPException(status_code=403, detail="一键添加只接受网址和标题")
    try:
        item, deduplicated = repo.add(
            url=payload.url,
            title=payload.title,
            group_id=payload.group_id,
            note=payload.note,
            tags=payload.tags,
            update_existing=not external,
        )
    except BookmarkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if deduplicated:
        response.status_code = 200
    if external:
        return BookmarkCaptureResult(deduplicated=deduplicated)
    return BookmarkSaveResult(item=Bookmark(**item), deduplicated=deduplicated)


@router.patch("/bookmarks/{bookmark_id}", response_model=Bookmark)
def update_bookmark(
    bookmark_id: int,
    payload: BookmarkUpdate,
    repo: BookmarkRepo = Depends(get_repo),
) -> Bookmark:
    try:
        item = repo.update(bookmark_id, **payload.model_dump(exclude_unset=True))
    except BookmarkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="书签不存在")
    return Bookmark(**item)


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(bookmark_id: int, repo: BookmarkRepo = Depends(get_repo)) -> Response:
    if not repo.delete(bookmark_id):
        raise HTTPException(status_code=404, detail="书签不存在")
    return Response(status_code=204)


@router.get("/groups", response_model=list[BookmarkGroup])
def list_groups(repo: BookmarkRepo = Depends(get_repo)) -> list[BookmarkGroup]:
    return [BookmarkGroup(**item) for item in repo.groups()]


@router.post("/groups", response_model=BookmarkGroup, status_code=201)
def create_group(payload: GroupCreate, repo: BookmarkRepo = Depends(get_repo)) -> BookmarkGroup:
    try:
        group = repo.create_group(payload.name)
    except BookmarkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    counts = {item["id"]: item.get("count", 0) for item in repo.groups()}
    group["count"] = counts.get(group["id"], 0)
    return BookmarkGroup(**group)


@router.post("/bookmarks/import", response_model=ImportResult)
def import_bookmarks(
    file: UploadFile = File(...),
    repo: BookmarkRepo = Depends(get_repo),
) -> ImportResult:
    raw = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="请使用 UTF-8 编码的书签 HTML") from exc
    try:
        return ImportResult(**repo.import_netscape(text))
    except BookmarkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bookmarks/export")
def export_bookmarks(repo: BookmarkRepo = Depends(get_repo)) -> Response:
    html = repo.export_netscape()
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cleansearch-bookmarks.html"'},
    )

@router.post("/bookmarks/check")
async def check_bookmarks(
    payload: BookmarkCheckRequest,
    repo: BookmarkRepo = Depends(get_repo),
    fetcher: SafeFetcher = Depends(get_fetcher),
) -> dict:
    """批量检测书签，只在明确存活或失效时更新标记。"""
    def select_items() -> list[dict]:
        if payload.ids is None:
            return repo.list(limit=payload.limit)
        return [item for bookmark_id in dict.fromkeys(payload.ids) if (item := repo.get(bookmark_id))][
            :payload.limit
        ]

    items = await run_in_threadpool(select_items)

    semaphore = asyncio.Semaphore(CHECK_CONCURRENCY)

    async def probe(item: dict) -> dict:
        async with semaphore:
            try:
                await fetcher.probe(item["url"])
                status = "alive"
                detail = ""
            except FetchError as exc:
                status = "dead" if exc.status in (404, 410) else "unknown"
                detail = exc.message
        return {"id": item["id"], "url": item["url"], "dead": status == "dead", "status": status, "detail": detail}

    results = await asyncio.gather(*(probe(item) for item in items))
    changes = [(int(result["dead"]), result["id"], result["url"]) for result in results if result["status"] != "unknown"]
    if changes:
        await run_in_threadpool(repo.save_link_checks, changes)
    return {
        "checked": len(results),
        "dead": sum(1 for result in results if result["dead"]),
        "unknown": sum(1 for result in results if result["status"] == "unknown"),
        "items": results,
    }