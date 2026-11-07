"""M4 受控抓取：SSRF 白名单、重定向复检、大小/类型/超时限额。"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.core.fetch import (
    FetchBlocked,
    FetchFailed,
    FetchTimeout,
    SafeFetcher,
    is_public_ip,
    validate_public_url,
)

PUBLIC = ["93.184.216.34"]


def make_fetcher(handler, resolver=lambda host: PUBLIC, **kwargs) -> SafeFetcher:
    options = {"timeout": 0.5, "max_bytes": 1000, "max_redirects": 2}
    options.update(kwargs)
    return SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolver, **options)


def test_is_public_ip_classification() -> None:
    for address in ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"):
        assert is_public_ip(address)
    for address in (
        "127.0.0.1", "10.1.2.3", "192.168.1.5", "169.254.169.254", "::1", "fd00::1", "224.0.0.1",
        "100.64.0.1", "::ffff:100.64.0.1", "64:ff9b::7f00:1", "2002:7f00:1::1",
    ):
        assert not is_public_ip(address)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://router.local/",
        "http://example.com:99999/",
        "http://user:pass@example.com/",
    ],
)
def test_validate_public_url_rejects(url: str) -> None:
    with pytest.raises(FetchBlocked):
        validate_public_url(url)


async def test_blocks_private_resolution() -> None:
    fetcher = SafeFetcher(resolver=lambda host: ["10.0.0.8"])
    with pytest.raises(FetchBlocked):
        await fetcher.fetch("https://internal.example/")


async def test_blocks_mixed_resolution() -> None:
    fetcher = SafeFetcher(resolver=lambda host: ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(FetchBlocked):
        await fetcher.fetch("https://rebind.example/")


async def test_redirect_to_private_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/latest/meta-data/"})

    fetcher = make_fetcher(handler, resolver=lambda host: PUBLIC if "example" in host else ["127.0.0.1"])
    with pytest.raises(FetchBlocked):
        await fetcher.fetch("https://example.com/redirect")


async def test_redirect_to_public_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "https://example.com/final"})
        return httpx.Response(200, text="<p>终点</p>", headers={"content-type": "text/html"})

    page = await make_fetcher(handler).fetch("https://example.com/start")
    assert page.url == "https://example.com/final" and "终点" in page.text


async def test_connects_only_to_validated_addresses_and_keeps_origin() -> None:
    resolved = []
    requests = []

    def resolver(host: str) -> list[str]:
        resolved.append(host)
        return ["93.184.216.34", "1.1.1.1"] if host == "example.com" else ["8.8.8.8"]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.host, request.headers["host"], request.extensions["sni_hostname"]))
        if request.url.host == "93.184.216.34":
            raise httpx.ConnectError("address unavailable", request=request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://other.example/done"})
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    page = await make_fetcher(handler, resolver).fetch("https://example.com:8443/start")
    assert resolved == ["example.com", "other.example"]
    assert requests == [
        ("93.184.216.34", "example.com:8443", "example.com"),
        ("1.1.1.1", "example.com:8443", "example.com"),
        ("8.8.8.8", "other.example", "other.example"),
    ]
    assert page.url == "https://other.example/done"


async def test_dns_and_trickled_body_share_overall_deadline() -> None:
    def slow_dns(host: str) -> list[str]:
        time.sleep(0.1)
        return PUBLIC

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        pytest.fail("DNS deadline elapsed before any request")

    with pytest.raises(FetchTimeout):
        await make_fetcher(unexpected_request, slow_dns, timeout=0.03).fetch("https://example.com/dns")

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10):
                await asyncio.sleep(0.01)
                yield b"text"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=SlowBody(), headers={"content-type": "text/plain"})

    with pytest.raises(FetchTimeout):
        await make_fetcher(handler, timeout=0.04).fetch("https://example.com/slow")


async def test_size_limit_truncates() -> None:
    body = "x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    page = await make_fetcher(handler, max_bytes=1000).fetch("https://example.com/big")
    assert page.truncated is True
    assert page.bytes_read == 1000


async def test_rejects_binary_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    with pytest.raises(FetchFailed):
        await make_fetcher(handler).fetch("https://example.com/a.pdf")


async def test_probe_accepts_binary_and_fetch_rejects_compression_before_reading() -> None:
    class UnreadBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail("expected to return before reading the body")
            yield b""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        content_type = "application/pdf" if request.url.path.endswith("pdf") else "text/html"
        return httpx.Response(200, stream=UnreadBody(), headers={
            "content-type": content_type, "content-encoding": "gzip",
        })

    fetcher = make_fetcher(handler)
    assert await fetcher.probe("https://example.com/a.pdf") == 200
    with pytest.raises(FetchFailed, match="压缩"):
        await fetcher.fetch("https://example.com/compressed")


async def test_http_error_raises_with_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="gone")

    with pytest.raises(FetchFailed) as excinfo:
        await make_fetcher(handler).fetch("https://example.com/missing")
    assert excinfo.value.status == 404


async def test_timeout_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchTimeout):
        await make_fetcher(handler).fetch("https://example.com/slow")


async def test_too_many_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/loop"})

    with pytest.raises(FetchFailed) as excinfo:
        await make_fetcher(handler, max_redirects=2).fetch("https://example.com/loop")
    assert "重定向" in excinfo.value.message


async def test_success_returns_text_and_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>正文</html>", headers={"content-type": "text/html; charset=utf-8"})

    page = await make_fetcher(handler).fetch("https://example.com/a")
    assert page.status == 200 and page.content_type == "text/html" and "<html>" in page.text


async def test_extra_cidr_allows_benchmark_range() -> None:
    body = "<html><body>代理回落的地址</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    blocked = make_fetcher(handler, resolver=lambda host: ["198.18.0.186"])
    with pytest.raises(FetchBlocked):
        await blocked.fetch("https://docs.example.org/")

    allowed = SafeFetcher(
        timeout=0.5,
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["198.18.0.186"],
        extra_cidrs=["198.18.0.0/15"],
    )
    page = await allowed.fetch("https://docs.example.org/")
    assert "代理回落" in page.text

    unsafe = make_fetcher(handler, resolver=lambda host: ["127.0.0.1"], extra_cidrs=["0.0.0.0/0"])
    with pytest.raises(FetchBlocked):
        await unsafe.fetch("https://docs.example.org/")
