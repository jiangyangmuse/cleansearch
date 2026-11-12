"""受控抓取：只访问公网 http(s)，重定向目标逐跳复检，限制大小与耗时。

每跳只连接已经验证的地址，HTTP Host 和 TLS 证书校验仍使用原域名。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import httpx

from app.core.normalize import is_renderable_url

DEFAULT_TIMEOUT = 2.5
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/xml",
    "text/xml",
)
USER_AGENT = "CleanSearch/0.2 (+local; M4)"
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal", "metadata"}
BENCHMARK_RANGE = ipaddress.ip_network("198.18.0.0/15")
IPV6_TRANSITION_RANGES = tuple(ipaddress.ip_network(cidr) for cidr in (
    "64:ff9b::/96", "64:ff9b:1::/48", "2001::/32", "2002::/16",
))


class FetchError(Exception):
    code = "FETCH_ERROR"

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class FetchBlocked(FetchError):
    code = "FETCH_BLOCKED"


class FetchTooLarge(FetchError):
    code = "FETCH_TOO_LARGE"


class FetchTimeout(FetchError):
    code = "FETCH_TIMEOUT"


class FetchFailed(FetchError):
    code = "FETCH_FAILED"


@dataclass
class FetchedPage:
    url: str
    status: int
    content_type: str
    text: str
    bytes_read: int
    truncated: bool
    raw: bytes = b""  # favicon 之类的二进制响应走这里


ALLOWABLE_RANGES = (
    ipaddress.ip_network("198.18.0.0/15"),   # RFC 2544 benchmark
    ipaddress.ip_network("2001:2::/48"),     # RFC 5180 benchmark
)


def is_public_ip(value: str, allowed=()) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    # 显式放行只对「bench 网段」生效：本机代理会把公网解析到 198.18/2001:2::，
    # 但不能让 0.0.0.0/0 这类宽网段把内网也放进来。
    if allowed and any(ip in network for network in ALLOWABLE_RANGES) and any(
        ip in network for network in allowed
    ):
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id or ip.is_site_local or any(ip in network for network in IPV6_TRANSITION_RANGES):
            return False
        if ip.ipv4_mapped:
            return is_public_ip(str(ip.ipv4_mapped), allowed)
    return ip.is_global and not (ip.is_multicast or ip.is_reserved)


def parse_networks(cidrs) -> tuple:
    networks = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP, flags=socket.AI_ADDRCONFIG)
    return list(dict.fromkeys(info[4][0] for info in infos))


def validate_public_url(url: str) -> httpx.URL:
    """只放行公网 http(s)：协议、主机、内网地址、端口都要过。"""
    if not is_renderable_url(url):
        raise FetchBlocked("只允许主机明确且不含凭证的 HTTP(S) 链接")
    try:
        target = httpx.URL(url.strip())
    except (httpx.InvalidURL, ValueError) as exc:
        raise FetchBlocked("URL 无法解析") from exc
    host = target.raw_host.decode("ascii")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local"):
        raise FetchBlocked(f"拒绝内网主机名：{host}")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not is_public_ip(str(literal)):
        raise FetchBlocked(f"拒绝非公网地址：{host}")
    return target


class SafeFetcher:
    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver=default_resolver,
        extra_cidrs=(),
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self._transport = transport
        self._resolver = resolver
        # 仅供「本机网络经透明代理回落私有/bench 网段」时显式放行，默认关闭
        self._allowed = parse_networks(extra_cidrs)

    def clone_with_timeout(self, timeout: float) -> "SafeFetcher":
        """复制一份限额相同、超时更长的抓取器（拉取较大的 feed 文件用）。"""
        return SafeFetcher(
            timeout=timeout,
            max_bytes=self.max_bytes,
            max_redirects=self.max_redirects,
            transport=self._transport,
            resolver=self._resolver,
            extra_cidrs=tuple(str(network) for network in self._allowed),
        )

    async def _public_addresses(self, url: httpx.URL) -> list[str]:
        host = url.raw_host.decode("ascii")
        try:
            return [str(ipaddress.ip_address(host))]  # 字面 IP 已在 URL 校验时检查
        except ValueError:
            pass
        try:
            addresses = await asyncio.to_thread(self._resolver, host)
        except OSError as exc:
            raise FetchFailed(f"域名解析失败：{host}") from exc
        if not addresses:
            raise FetchFailed(f"域名无解析结果：{host}")
        blocked = [address for address in addresses if not is_public_ip(address, self._allowed)]
        if blocked:
            raise FetchBlocked(f"拒绝非公网地址：{host} → {', '.join(blocked[:3])}")
        return list(dict.fromkeys(str(ipaddress.ip_address(address)) for address in addresses))

    async def pin_public_target(self, url: str) -> tuple[httpx.URL, str, str]:
        """供已授权的公网模型调用复用 DNS 校验与连接地址固定。"""
        target = validate_public_url(url)
        addresses = await self._public_addresses(target)
        return target.copy_with(host=addresses[0]), target.netloc.decode("ascii"), target.raw_host.decode("ascii")

    async def fetch(
        self,
        url: str,
        max_bytes: int | None = None,
        allowed_types: set[str] | frozenset[str] | None = None,
    ) -> FetchedPage:
        return await self._walk(
            url, max_bytes if max_bytes is not None else self.max_bytes, allowed_types
        )

    async def probe(self, url: str) -> int:
        """死链检测只读响应状态，任何媒体类型都可以是有效链接。"""
        return (await self._walk(url, None)).status

    async def _walk(
        self, url: str, limit: int | None, allowed_types=None
    ) -> FetchedPage:
        current = url
        try:
            async with asyncio.timeout(self.timeout):
                for _ in range(self.max_redirects + 1):
                    target = validate_public_url(current)
                    addresses = await self._public_addresses(target)
                    result = await self._request(target, addresses, limit, allowed_types)
                    if isinstance(result, FetchedPage):
                        return result
                    current = result
                raise FetchFailed("重定向次数过多", status=310)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise FetchTimeout(f"抓取超时（{self.timeout:g}s）") from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise FetchFailed(f"抓取失败：{exc.__class__.__name__}") from exc

    async def _request(
        self, url: httpx.URL, addresses: list[str], limit: int | None, allowed_types=None
    ) -> FetchedPage | str:
        headers = {
            "Host": url.netloc.decode("ascii"),
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5" if limit is not None else "*/*",
            "Accept-Encoding": "identity",
        }
        extensions = {"sni_hostname": url.raw_host.decode("ascii")}
        # 每跳独立连接，且不使用会替客户端重新解析目标的环境代理。
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self._transport, follow_redirects=False, trust_env=False
        ) as client:
            for index, address in enumerate(addresses):
                try:
                    async with client.stream(
                        "GET", url.copy_with(host=address), headers=headers, extensions=extensions,
                    ) as response:
                        return await self._read_response(url, response, limit, allowed_types)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if index == len(addresses) - 1:
                        raise
        raise FetchFailed("没有可用的连接地址")

    async def _read_response(
        self, url: httpx.URL, response: httpx.Response, limit: int | None, allowed_types=None
    ) -> FetchedPage | str:
        status = response.status_code
        if status in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise FetchFailed("重定向缺少 Location", status=status)
            return str(url.join(location))
        if not 200 <= status < 300:
            raise FetchFailed(f"上游返回 {status}", status=status)
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if limit is None:
            return FetchedPage(str(url), status, content_type, "", 0, False)
        permitted = allowed_types or ALLOWED_CONTENT_TYPES
        if content_type not in permitted:
            raise FetchFailed(f"不支持的内容类型：{content_type or '未声明'}")
        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
            raise FetchFailed("正文抓取不接受压缩响应")
        buffer = bytearray()
        truncated = False
        async for chunk in response.aiter_bytes():
            remaining = limit - len(buffer)
            buffer.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
                break
        raw = bytes(buffer)
        text = raw.decode(response.encoding or "utf-8", "replace")
        return FetchedPage(str(url), status, content_type, text, len(buffer), truncated, raw)
