"""M9：书签标签与筛选。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.repo import BookmarkRepo
from app.main import app
from app.routers.bookmarks import get_repo


def test_tags_roundtrip_and_filter(tmp_path) -> None:
    repo = BookmarkRepo(tmp_path / "b.db")
    try:
        item, _ = repo.add("https://a.test/x", title="A", tags=["工作", "待读"])
        assert set(repo.get(item["id"])["tags"]) == {"工作", "待读"}
        repo.add("https://b.test/y", title="B", tags=["工作"])

        listed = repo.list()
        assert set(next(i for i in listed if i["id"] == item["id"])["tags"]) == {"工作", "待读"}

        assert {i["title"] for i in repo.list(tag="工作")} == {"A", "B"}
        assert [i["title"] for i in repo.list(tag="待读")] == ["A"]

        repo.update(item["id"], tags=["归档"])
        assert repo.get(item["id"])["tags"] == ["归档"]
        assert repo.tags() == [{"tag": "工作", "count": 1}, {"tag": "归档", "count": 1}]
    finally:
        repo.close()


def test_api_tag_filter_and_tag_list(client: TestClient, tmp_path) -> None:
    repo = BookmarkRepo(tmp_path / "api.db")
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        created = client.post(
            "/api/bookmarks", json={"url": "https://tag.test/a", "title": "带标签", "tags": ["资料"]}
        ).json()["item"]
        client.post("/api/bookmarks", json={"url": "https://tag.test/b", "title": "无标签"})

        listed = client.get("/api/bookmarks", params={"tag": "资料"}).json()
        assert [item["id"] for item in listed["items"]] == [created["id"]]
        assert listed["tags"] == [{"tag": "资料", "count": 1}]

        patched = client.patch(
            f"/api/bookmarks/{created['id']}", json={"tags": ["资料", "重要"]}
        ).json()
        assert set(patched["tags"]) == {"资料", "重要"}
    finally:
        app.dependency_overrides.pop(get_repo, None)
        repo.close()
