"""配置与归一化护栏测试：把 M0 验收报告里的两条建议固化成回归。

- Compose 不得把 SearXNG 发布到所有网卡（limiter 已关）
- settings.yml 必须显式开 json、关 limiter
- 结果 URL 只放行 http(s)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.normalize import is_renderable_url, normalise_result

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_compose_binds_searxng_to_loopback() -> None:
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8888:8080"' in text
    assert '"8888:8080"' not in text
    assert '"127.0.0.1:8000:8000"' in text


def test_searxng_settings_keep_json_and_limiter_off() -> None:
    text = (REPO_ROOT / "searxng" / "settings.yml").read_text(encoding="utf-8")
    assert "formats: [html, json]" in text
    assert "limiter: false" in text


@pytest.mark.parametrize(
    "bad",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "ftp://example.com/x",
        "mailto:a@example.com",
        "//example.com/no-scheme",
        "http://",
        "http://example.com\nnext",
        "https://example.com/a\x01b",
        "https://example.com/a\x7fb",
        "http://exa mple.com/",
        "http://example.com:99999/",
        "https://user:pass@example.com/",
        "https://@example.com/",
        r"https://actual.example\@displayed.example/a",
        "https://%65xample.com/a",
        "https://bad^host.example/a",
        "https://" + "a" * 2100 + "/",
    ],
)
def test_is_renderable_url_rejects(bad: str) -> None:
    assert is_renderable_url(bad) is False


@pytest.mark.parametrize(
    "good",
    [
        "http://example.com",
        "https://example.com/a?b=1",
        "https://xn--fiq228c.cn/",
        "http://127.0.0.1:8000/x",
        "https://[2001:db8::1]:443/docs",
    ],
)
def test_is_renderable_url_accepts(good: str) -> None:
    assert is_renderable_url(good) is True


def test_normalise_result_drops_non_http_urls() -> None:
    assert normalise_result({"url": "file:///etc/passwd", "title": "本地"}, 1) is None
    assert normalise_result({"url": "javascript:alert(1)", "title": "脚本"}, 1) is None
    assert normalise_result({"url": "", "title": "空"}, 1) is None
    kept = normalise_result({"url": "https://example.com/a", "title": "正常"}, 1)
    assert kept is not None and kept.url == "https://example.com/a"


def test_canonical_url_strips_credentials_and_tracking() -> None:
    from app.core.normalize import canonical_url

    assert canonical_url("https://user:pass@Example.com/a/?utm_source=x#y") == (
        "https://example.com/a"
    )
