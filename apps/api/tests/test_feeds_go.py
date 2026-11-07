"""M9：黑名单 feed 刷新与 /go 风险中转。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.feeds import merge_into, parse_feed, refresh
from app.core.fetch import SafeFetcher
from app.core.redirect import build_go_path, sign_url, verify_go
from app.core.safety import Blocklist

FEED_TEXT = """# comment
https://evil.example/path
bad-domain.test
duckduckgo.com/?q=1
not a domain
"""


def make_fetcher(body: str) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/plain"})

    return SafeFetcher(
        timeout=0.5, transport=httpx.MockTransport(handler), resolver=lambda host: ["93.184.216.34"]
    )


def test_parse_feed_filters_noise() -> None:
    entries = parse_feed(FEED_TEXT)
    assert "https://evil.example/path" in entries
    assert "bad-domain.test" in entries
    assert "duckduckgo.com/?q=1" in entries
    assert all("<" not in entry for entry in entries)
    assert "not" not in entries


def test_merge_and_blocklist_pickup(tmp_path: Path) -> None:
    base = tmp_path / "base.txt"
    base.write_text("base.test\n", encoding="utf-8")
    feeds = tmp_path / "feeds.txt"
    merge_into(feeds, {"evil.example", "https://tracker.example/x"})

    blocklist = Blocklist(base, extra_paths=(feeds,))
    assert blocklist.match("https://evil.example/landing")
    assert blocklist.match("https://sub.evil.example/landing")
    assert blocklist.match("https://tracker.example/x")
    assert not blocklist.match("https://tracker.example/other")
    assert blocklist.match("https://base.test/a")


async def test_refresh_reports_sources(tmp_path: Path) -> None:
    output = tmp_path / "out.txt"
    results = await refresh(["https://feed.example/list.txt"], output, make_fetcher(FEED_TEXT))
    assert results[0].ok and results[0].entries >= 2
    assert "bad-domain.test" in output.read_text(encoding="utf-8")


def test_sign_and_verify() -> None:
    url = "https://evil.example/a?b=1"
    sig = sign_url(url, "secret")
    assert verify_go(build_go_path(url, "secret").split("u=")[1].split("&")[0], sig, "secret") == url
    assert verify_go(build_go_path(url, "secret").split("u=")[1].split("&")[0], sig + "0", "secret") is None


def test_go_page_renders_and_rejects_tampering(client: TestClient) -> None:
    from app.config import get_settings
    from app.core.tokens import get_api_token

    secret = get_api_token(get_settings().api_token_path)
    url = "https://login.secure.verify.xn--80ak6aa92e.top/pay"
    path = build_go_path(url, secret)
    ok = client.get(path)
    assert ok.status_code == 200
    assert ".top" in ok.text and "仍要访问" in ok.text

    tampered = client.get(path.replace("sig=", "sig=0"))
    assert tampered.status_code == 403
    invalid_signature = path.rsplit("=", 1)[0] + "=" + quote("无效")
    assert client.get(invalid_signature).status_code == 403
    invalid_url = build_go_path("https://[broken", secret)
    assert client.get(invalid_url).status_code == 403


def test_search_marks_suspicious_results_with_go_url(client: TestClient) -> None:
    body = client.post(
        "/api/search", json={"q": "账号验证", "opts": {"fixture": "risky"}}
    ).json()
    results = [item for group in body["groups"].values() for item in group]
    suspicious = [item for item in results if item["risk"] >= 0.35]
    clean = [item for item in results if item["risk"] < 0.35]
    assert suspicious and suspicious[0]["go_url"] and suspicious[0]["go_url"].startswith("/go?u=")
    assert all(item["go_url"] is None for item in clean)


def test_refresh_endpoint_without_urls_is_400(client: TestClient, monkeypatch) -> None:
    from dataclasses import replace

    import app.routers.tools as tools_router
    from app.config import get_settings

    monkeypatch.setattr(
        tools_router, "get_settings", lambda: replace(get_settings(), feed_urls=())
    )
    response = client.post("/api/tools/refresh-feeds", json={})
    assert response.status_code == 400
    assert "FEED_URLS" in response.json()["detail"]
