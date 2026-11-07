"""一键添加：bookmarklet、token 鉴权与跨域收口。"""

from __future__ import annotations

import json
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.tokens import get_api_token, token_matches

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIL = {"Origin": "https://evil.example"}


def test_token_file_is_created_once(tmp_path: Path) -> None:
    path = tmp_path / "api-token.txt"
    first = get_api_token(path)
    second = get_api_token(path)
    assert first == second and len(first) >= 24
    assert path.read_text(encoding="utf-8").strip() == first


def test_token_matches_rejects_empty_and_wrong() -> None:
    assert token_matches("abc", "abc")
    assert not token_matches("abc", "abd")
    assert not token_matches("", "abc")
    assert not token_matches(None, "abc")
    assert not token_matches("é", "abc")


def test_concurrent_first_token_reads_return_one_value(tmp_path: Path) -> None:
    path = tmp_path / "api-token.txt"
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(get_api_token, [path] * 16))
    assert len(set(tokens)) == 1 and path.read_text(encoding="utf-8") == tokens[0]


def test_bookmarklet_payload(client: TestClient) -> None:
    response = client.get("/api/tools/bookmarklet", headers={"Host": "[::1]:8000"})
    body = response.json()
    assert body["code"].startswith("javascript:")
    assert body["token"] in body["code"]
    assert "X-CS-Token" in body["code"]
    assert "/api/bookmarks" in body["code"]
    assert body["api"] == "http://[::1]:8000"
    assert response.headers["cache-control"] == "no-store"


def test_non_loopback_host_cannot_read_token(client: TestClient) -> None:
    response = client.get("/api/tools/bookmarklet", headers={"Host": "rebind.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HOST_FORBIDDEN"
    assert "token" not in response.json()


def test_cross_origin_write_requires_token(client: TestClient) -> None:
    response = client.post(
        "/api/bookmarks", json={"url": "https://blocked.test/a"}, headers=EVIL
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_REQUIRED"
    assert response.headers["access-control-allow-origin"] == "*"


def test_cross_origin_write_with_token_succeeds(client: TestClient) -> None:
    token = client.get("/api/tools/bookmarklet").json()["token"]
    url = "https://allowed.test/a"
    headers = {**EVIL, "X-CS-Token": token}
    response = client.post(
        "/api/bookmarks", json={"url": url}, headers=headers,
    )
    try:
        assert response.status_code == 201, response.text
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.json() == {"deduplicated": False}
        duplicate = client.post("/api/bookmarks", json={"url": url, "title": "来自扩展"}, headers=headers)
        assert duplicate.status_code == 200 and duplicate.json() == {"deduplicated": True}
        item = next(item for item in client.get("/api/bookmarks").json()["items"] if item["url"] == url)
        assert item["title"] is None
    finally:
        for item in client.get("/api/bookmarks").json()["items"]:
            if item["url"] == url:
                client.delete(f"/api/bookmarks/{item['id']}")


def test_wrong_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/bookmarks",
        json={"url": "https://blocked.test/b"},
        headers={**EVIL, "X-CS-Token": "not-the-token"},
    )
    assert response.status_code == 401


def test_token_cannot_read_edit_or_delete_bookmarks(client: TestClient) -> None:
    token = client.get("/api/tools/bookmarklet").json()["token"]
    url = "https://protected.test/a"
    saved = client.post("/api/bookmarks", json={"url": url, "title": "原书签"}).json()["item"]
    path = f"/api/bookmarks/{saved['id']}"
    headers = {**EVIL, "X-CS-Token": token}
    try:
        assert client.get("/api/bookmarks", headers=headers).status_code == 403
        assert client.get("/api/bookmarks/export", headers=headers).status_code == 403
        assert client.patch(path, json={"title": "被更改"}, headers=headers).status_code == 403
        assert client.delete(path, headers=headers).status_code == 403
        assert client.post("/api/bookmarks", json={"url": url, "note": "被更改"}, headers=headers).status_code == 403
        assert client.delete(path, headers={"X-CS-Token": token}).status_code == 403
        assert saved in client.get("/api/bookmarks").json()["items"]
    finally:
        client.delete(path)


def test_preflight_allows_token_header(client: TestClient) -> None:
    response = client.options(
        "/api/bookmarks",
        headers={
            **EVIL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-cs-token",
        },
    )
    assert response.status_code == 204
    assert "x-cs-token" in response.headers["access-control-allow-headers"]
    denied = client.options("/api/bookmarks", headers={**EVIL, "Access-Control-Request-Method": "DELETE"})
    assert denied.status_code == 403 and "access-control-allow-origin" not in denied.headers


def test_other_api_is_not_cross_origin_readable(client: TestClient) -> None:
    response = client.get("/api/health", headers=EVIL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CORS_FORBIDDEN"


def test_same_origin_is_not_guarded(client: TestClient) -> None:
    response = client.post(
        "/api/bookmarks",
        json={"url": "https://same-origin.test/a"},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert response.status_code in (200, 201), response.text
    client.delete(f"/api/bookmarks/{response.json()['item']['id']}")


def test_pwa_manifest_has_share_target() -> None:
    manifest = json.loads(
        (REPO_ROOT / "apps" / "web" / "public" / "manifest.webmanifest").read_text(encoding="utf-8")
    )
    target = manifest["share_target"]
    assert target["action"] == "/bookmarks"
    assert target["method"] == "GET"
    assert set(target["params"]) >= {"title", "url"}
    sizes = set()
    for icon in manifest["icons"]:
        data = (REPO_ROOT / "apps" / "web" / "public" / icon["src"].lstrip("/")).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        sizes.add(struct.unpack(">II", data[16:24]))
    assert {(192, 192), (512, 512)} <= sizes


def test_index_links_manifest() -> None:
    html = (REPO_ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")
    assert "manifest.webmanifest" in html


def test_extension_manifest_is_mv3() -> None:
    directory = REPO_ROOT / "apps" / "extension"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert any("127.0.0.1" in host for host in manifest["host_permissions"])
    assert (directory / manifest["action"]["default_popup"]).is_file()
    assert (directory / "popup.js").is_file()
    assert "X-CS-Token" in (directory / "popup.js").read_text(encoding="utf-8")
