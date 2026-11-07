"""M3 书签：CRUD、去重规则、搜索、Netscape 导入导出往返。"""

from __future__ import annotations

import io
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.netscape import parse_netscape
from app.db.repo import SCHEMA_PATH, BookmarkError, BookmarkRepo
from app.main import app
from app.routers.bookmarks import get_repo


def netscape_html(entries: list[tuple[str, str, str]]) -> str:
    """entries: (folder, title, url)"""
    folders: dict[str, list[tuple[str, str]]] = {}
    for folder, title, url in entries:
        folders.setdefault(folder, []).append((title, url))
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">",
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for folder, items in folders.items():
        lines.append(f"    <DT><H3>{folder}</H3>")
        lines.append("    <DL><p>")
        for title, url in items:
            lines.append(f'        <DT><A HREF="{url}" ADD_DATE="1700000000">{title}</A>')
        lines.append("    </DL><p>")
    lines.append("</DL><p>")
    return "\n".join(lines)


@pytest.fixture()
def repo(tmp_path):
    repo = BookmarkRepo(tmp_path / "bookmarks.db")
    yield repo
    repo.close()


@pytest.fixture()
def bclient(client: TestClient, repo: BookmarkRepo):
    app.dependency_overrides[get_repo] = lambda: repo
    yield client
    app.dependency_overrides.pop(get_repo, None)


def test_add_and_duplicate_rule(repo: BookmarkRepo) -> None:
    item, deduped = repo.add("https://example.com/a?utm_source=x", title="示例")
    assert deduped is False and item["title"] == "示例"

    again, deduped = repo.add("https://example.com/a", title="另一个标题")
    assert deduped is True
    assert again["id"] == item["id"]
    assert again["title"] == "示例"          # 已有标题不被覆盖
    assert len(repo.list()) == 1


def test_duplicate_fills_missing_title_and_group(repo: BookmarkRepo) -> None:
    group = repo.create_group("资料")
    item, _ = repo.add("https://example.com/b")
    assert item["title"] is None and item["group_id"] is None
    updated, deduped = repo.add("https://example.com/b", title="补标题", group_id=group["id"])
    assert deduped and updated["title"] == "补标题" and updated["group_id"] == group["id"]


def test_invalid_url_rejected(repo: BookmarkRepo) -> None:
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "not a url"):
        with pytest.raises(BookmarkError):
            repo.add(bad)


def test_search_and_group_filter(repo: BookmarkRepo) -> None:
    group = repo.create_group("文档")
    repo.add("https://docs.python.org/3/library/asyncio.html", title="asyncio 文档", group_id=group["id"])
    repo.add("https://fastapi.tiangolo.com/", title="FastAPI 文档")
    repo.add("https://github.blog/news/", title="Octoverse 报告")

    assert [item["title"] for item in repo.list(q="asyncio")] == ["asyncio 文档"]
    assert len(repo.list(q="文档")) == 2
    assert [item["title"] for item in repo.list(group_id=group["id"])] == ["asyncio 文档"]
    assert repo.list(q="不存在的关键词") == []
    chinese, _ = repo.add("https://example.com/analysis", title="数据分析入门")
    assert [item["id"] for item in repo.list(q="分析")] == [chinese["id"]]
    assert [item["id"] for item in repo.list(q="nalysis")] == [chinese["id"]]


def test_import_export_round_trip(repo: BookmarkRepo) -> None:
    html = netscape_html(
        [
            ("开发", "Python 文档", "https://docs.python.org/3/"),
            ("开发", "MDN", "https://developer.mozilla.org/zh-CN/"),
            ("阅读", "维基百科", "https://zh.wikipedia.org/wiki/Inverted_index"),
        ]
    )
    result = repo.import_netscape(html)
    assert result == {"total": 3, "created": 3, "updated": 0, "skipped": 0, "groups_created": 2}

    exported = repo.export_netscape()
    assert "NETSCAPE-Bookmark-file-1" in exported
    assert "<H3>开发</H3>" in exported

    fresh = BookmarkRepo(repo.path.parent / "roundtrip.db")
    try:
        imported = fresh.import_netscape(exported)
        assert imported["created"] == 3
        original = {(item["url"], item["title"], item["group_name"]) for item in repo.list()}
        copied = {(item["url"], item["title"], item["group_name"]) for item in fresh.list()}
        assert copied == original                      # URL / 标题 / 分组三者一致
    finally:
        fresh.close()


def test_reimport_skips_duplicates(repo: BookmarkRepo) -> None:
    html = netscape_html([("", "A", "https://a.test/x"), ("", "B", "https://b.test/y")])
    first = repo.import_netscape(html)
    second = repo.import_netscape(html)
    assert first["created"] == 2
    assert second["created"] == 0 and second["skipped"] == 2
    assert len(repo.list()) == 2


def test_nested_paths_and_root_bookmarks_survive_round_trip(repo: BookmarkRepo) -> None:
    html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
    <DL><p>
      <DT><A HREF="https://example.test/root">根目录 &amp; 标题</A>
      <DT><H3>工作</H3><DL><p>
        <DT><H3>文档</H3><DL><p>
          <DT><A HREF="https://example.test/work">工作文档</A>
        </DL>
      </DL>
      <DT><H3>学习</H3><DL><p>
        <DT><H3>文档</H3><DL><p>
          <DT><A HREF="https://example.test/study">学习文档</A>
        </DL>
      </DL>
      <DT><H3>工作 / 文档</H3><DL><p>
        <DT><A HREF="https://example.test/literal">带斜杠的文件夹</A>
      </DL>
    </DL>"""
    assert repo.import_netscape(html)["groups_created"] == 3
    fresh = BookmarkRepo(repo.path.parent / "nested-roundtrip.db")
    try:
        exported = repo.export_netscape()
        expected = {(item.url, item.title): item.folder for item in parse_netscape(html)}
        actual = {(item.url, item.title): item.folder for item in parse_netscape(exported)}
        assert actual == expected
        assert fresh.import_netscape(exported)["created"] == 4
        root = fresh.find_by_url("https://example.test/root")
        assert root is not None and root["group_id"] is None
        assert fresh.import_netscape(exported)["skipped"] == 4
    finally:
        fresh.close()


def test_existing_database_keeps_groups_on_schema_upgrade(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8").replace("  folder_path TEXT,\n", ""))
        conn.execute("INSERT INTO bookmark_groups (id, name) VALUES (7, '原分组')")
        conn.execute(
            "INSERT INTO bookmarks (url, url_key, title, group_id, created_at) VALUES (?, ?, ?, 7, 1)",
            ("https://old.test/", "https://old.test/", "旧书签"),
        )
    conn.close()
    migrated = BookmarkRepo(path)
    try:
        assert migrated.list()[0]["group_id"] == 7
        assert parse_netscape(migrated.export_netscape())[0].folder == ("原分组",)
        assert migrated.import_netscape(netscape_html([("原分组", "新增", "https://new.test/")]))["groups_created"] == 0
    finally:
        migrated.close()


def test_import_rolls_back_on_write_failure(repo: BookmarkRepo) -> None:
    with sqlite3.connect(repo.path) as conn:
        conn.execute("""CREATE TRIGGER fail_import BEFORE INSERT ON bookmarks
            WHEN new.url = 'https://fail.test/' BEGIN SELECT RAISE(ABORT, 'test'); END""")
    conn.close()
    html = netscape_html([("新分组", "先写入", "https://ok.test/"), ("新分组", "后失败", "https://fail.test/")])
    with pytest.raises(sqlite3.IntegrityError):
        repo.import_netscape(html)
    assert repo.list() == [] and repo.groups() == []


def test_import_never_moves_existing_bookmark(repo: BookmarkRepo) -> None:
    manual = repo.create_group("手动")
    item, _ = repo.add("https://kept.test/a", title="我起的标题", group_id=manual["id"])
    result = repo.import_netscape(
        netscape_html([("导入分组", "导入标题", "https://kept.test/a")])
    )
    assert result["skipped"] == 1 and result["created"] == 0 and result["groups_created"] == 0
    kept = repo.get(item["id"])
    assert kept is not None
    assert kept["title"] == "我起的标题" and kept["group_id"] == manual["id"]
    assert [group["name"] for group in repo.groups()] == ["手动"]


def test_import_500_entries(repo: BookmarkRepo) -> None:
    entries = [(f"分组{i % 7}", f"标题 {i}", f"https://site{i}.test/page") for i in range(500)]
    result = repo.import_netscape(netscape_html(entries))
    assert result["created"] == 500 and result["total"] == 500
    assert len(repo.list(limit=1000)) == 500
    assert len(repo.groups()) == 7


def test_api_crud(bclient: TestClient) -> None:
    created = bclient.post("/api/bookmarks", json={"url": "https://example.com/a", "title": "示例"})
    assert created.status_code == 201
    body = created.json()
    assert body["deduplicated"] is False
    bookmark_id = body["item"]["id"]

    duplicate = bclient.post("/api/bookmarks", json={"url": "https://example.com/a?utm_medium=x"})
    assert duplicate.status_code == 200
    assert duplicate.json()["deduplicated"] is True

    listed = bclient.get("/api/bookmarks").json()
    assert listed["total"] == 1 and listed["fts"] in (True, False)

    group = bclient.post("/api/groups", json={"name": "待阅读"}).json()
    patched = bclient.patch(f"/api/bookmarks/{bookmark_id}", json={"group_id": group["id"]})
    assert patched.status_code == 200 and patched.json()["group_name"] == "待阅读"
    patched = bclient.patch(f"/api/bookmarks/{bookmark_id}", json={"note": "备注"})
    assert patched.status_code == 200 and patched.json()["note"] == "备注"
    assert patched.json()["group_id"] == group["id"]
    ungrouped = bclient.patch(f"/api/bookmarks/{bookmark_id}", json={"group_id": None})
    assert ungrouped.status_code == 200 and ungrouped.json()["group_id"] is None
    assert ungrouped.json()["note"] == "备注"
    assert bclient.get("/api/bookmarks", params={"group": group["id"]}).json()["total"] == 0

    assert bclient.delete(f"/api/bookmarks/{bookmark_id}").status_code == 204
    assert bclient.get("/api/bookmarks").json()["total"] == 0
    assert bclient.delete(f"/api/bookmarks/{bookmark_id}").status_code == 404


def test_api_rejects_bad_url(bclient: TestClient) -> None:
    response = bclient.post("/api/bookmarks", json={"url": "javascript:alert(1)"})
    assert response.status_code == 400


def test_api_save_with_tags(bclient: TestClient, repo: BookmarkRepo) -> None:
    body = {"url": "https://example.test/tagged", "tags": ["python", "python"]}
    assert bclient.post("/api/bookmarks", json=body).status_code == 201
    body["tags"] = ["文档"]
    assert bclient.post("/api/bookmarks", json=body).status_code == 200
    with sqlite3.connect(repo.path) as conn:
        assert {row[0] for row in conn.execute("SELECT tag FROM bookmark_tags")} == {"python", "文档"}
    conn.close()


def test_api_bookmark_pagination(bclient: TestClient, repo: BookmarkRepo) -> None:
    repo.import_netscape(netscape_html([("资料", f"资料 {i}", f"https://example.test/{i}") for i in range(205)]))
    first = bclient.get("/api/bookmarks").json()
    second = bclient.get("/api/bookmarks", params={"offset": 200, "limit": 10}).json()
    assert first["total"] == second["total"] == 205
    assert len(first["items"]) == 200 and len(second["items"]) == 5
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
    assert bclient.get("/api/bookmarks", params={"q": "资料 204"}).json()["total"] == 1
    assert bclient.get("/api/bookmarks", params={"limit": 201}).status_code == 422


def test_api_groups(bclient: TestClient) -> None:
    first = bclient.post("/api/groups", json={"name": "工作"})
    second = bclient.post("/api/groups", json={"name": "工作"})
    assert first.status_code == 201 and second.json()["id"] == first.json()["id"]
    assert [group["name"] for group in bclient.get("/api/groups").json()] == ["工作"]


def test_api_import_and_export(bclient: TestClient) -> None:
    html = netscape_html([("资料", "示例站", "https://example.com/a")])
    response = bclient.post(
        "/api/bookmarks/import",
        files={"file": ("bookmarks.html", io.BytesIO(html.encode("utf-8")), "text/html")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    exported = bclient.get("/api/bookmarks/export")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    assert 'HREF="https://example.com/a"' in exported.text


def test_api_empty_export_can_be_imported(bclient: TestClient) -> None:
    exported = bclient.get("/api/bookmarks/export")
    response = bclient.post("/api/bookmarks/import", files={"file": ("empty.html", exported.content)})
    assert response.status_code == 200 and response.json()["total"] == 0
    invalid = bclient.post("/api/bookmarks/import", files={"file": ("invalid.html", b"<article>text</article>")})
    assert invalid.status_code == 400


def test_dead_link_check_distinguishes_dead_unknown_and_live_pdf(bclient: TestClient, repo: BookmarkRepo) -> None:
    import httpx

    from app.core.fetch import SafeFetcher
    from app.deps import get_fetcher

    alive = bclient.post("/api/bookmarks", json={"url": "https://alive.test/a", "title": "活着"}).json()["item"]
    dead = bclient.post("/api/bookmarks", json={"url": "https://dead.test/b", "title": "挂了"}).json()["item"]
    limited, _ = repo.add("https://limited.test/c")
    repo.update(alive["id"], dead=1)
    repo.update(limited["id"], dead=1)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "dead.test":
            return httpx.Response(404, text="gone")
        if request.headers["host"] == "limited.test":
            return httpx.Response(429)
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    fetcher = SafeFetcher(
        timeout=0.5, max_bytes=200_000, transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"],
    )
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    try:
        result = bclient.post("/api/bookmarks/check", json={"ids": [alive["id"], dead["id"], limited["id"]]}).json()
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert result["checked"] == 3
    assert result["dead"] == result["unknown"] == 1
    flagged = {item["id"]: item["dead"] for item in result["items"]}
    assert flagged[dead["id"]] is True and flagged[alive["id"]] is False

    items = {item["id"]: item for item in bclient.get("/api/bookmarks").json()["items"]}
    assert items[dead["id"]]["dead"] == 1
    assert items[alive["id"]]["dead"] == 0
    assert items[limited["id"]]["dead"] == 1  # 无法确认时保留先前的标记


def test_dead_link_check_blocks_private_urls(bclient: TestClient) -> None:
    from app.deps import get_fetcher

    item = bclient.post("/api/bookmarks", json={"url": "http://127.0.0.1:8000/x", "title": "本地"}).json()["item"]

    from app.core.fetch import SafeFetcher

    app.dependency_overrides[get_fetcher] = lambda: SafeFetcher()
    try:
        result = bclient.post("/api/bookmarks/check", json={"ids": [item["id"]]}).json()
    finally:
        app.dependency_overrides.pop(get_fetcher, None)
    assert result["dead"] == 0 and result["unknown"] == 1
    assert result["items"][0]["status"] == "unknown"


def test_dead_link_check_honors_old_bookmark_ids_and_empty_selection(bclient: TestClient, repo: BookmarkRepo) -> None:
    import httpx

    from app.core.fetch import SafeFetcher
    from app.deps import get_fetcher

    old, _ = repo.add("https://old.test/item")
    repo.import_netscape(netscape_html([("资料", f"资料 {i}", f"https://example.test/{i}") for i in range(205)]))
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["host"])
        return httpx.Response(410)

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"])
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    try:
        empty = bclient.post("/api/bookmarks/check", json={"ids": []}).json()
        result = bclient.post("/api/bookmarks/check", json={"ids": [old["id"]]}).json()
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert empty["checked"] == 0 and seen == ["old.test"]
    assert result["checked"] == result["dead"] == 1
    assert repo.get(old["id"])["dead"] == 1
