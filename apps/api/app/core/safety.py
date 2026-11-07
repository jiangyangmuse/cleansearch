"""安全过滤：本地黑名单 + 启发式风险分（M1 版，不含域名年龄）。

- 黑名单命中 → 直接拦截（dropped），计入 meta.filtered.risk；
- 其余按 TLD / URL 形状 / 形近字符打分，0.35 起标记「可疑」，0.6 起拦截；
- 域名年龄（RDAP）与三源实时 feed 按方案属于 M4，此处留接口不联网。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

BLOCK_THRESHOLD = 0.6
SUSPICIOUS_THRESHOLD = 0.35

SUSPICIOUS_TLDS = frozenset(
    {
        "zip", "mov", "top", "xyz", "tk", "icu", "cyou", "click", "link",
        "gq", "ml", "cf", "ga", "work", "loan", "men", "rest", "buzz",
    }
)

LONG_RANDOM_PATH = re.compile(r"/[A-Za-z0-9_-]{24,}")
IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


@dataclass(frozen=True)
class SafetyReport:
    blocked: bool
    risk: float
    reasons: tuple[str, ...] = ()


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _exact_url_key(url: str) -> tuple[str, str, int | None, str, str] | None:
    try:
        parts = urlsplit(url)
        scheme, host, port = parts.scheme.lower(), parts.hostname, parts.port
    except ValueError:
        return None
    if scheme not in ("http", "https") or not host or parts.username is not None:
        return None
    if (scheme, port) in (("http", 80), ("https", 443)):
        port = None
    # 锚点不会发送到站点；仍按完整路径和查询串匹配，避免扩大到同站其他页面。
    return scheme, host.lower(), port, parts.path.rstrip("/"), parts.query


class Blocklist:
    """纯文本黑名单：一行一个域名或完整 URL，# 开头为注释。

    域名按「自身或任意父域」匹配，因此 evil.test 同时覆盖 www.evil.test。
    """

    def __init__(self, path: Path | None = None, extra_paths: tuple[Path, ...] = ()) -> None:
        self._path = path
        self._extra_paths = tuple(p for p in extra_paths if p is not None)
        self._mtime: str | None = None
        self._revision = ""
        self._urls: set[tuple[str, str, int | None, str, str]] = set()
        self._hosts: set[str] = set()
        self.reload(force=True)

    @property
    def size(self) -> int:
        self.reload()
        return len(self._hosts) + len(self._urls)

    @property
    def revision(self) -> str:
        self.reload()
        return self._revision

    def reload(self, force: bool = False) -> None:
        paths = [p for p in (self._path, *self._extra_paths) if p is not None]
        if not paths:
            self._urls, self._hosts, self._mtime, self._revision = set(), set(), None, ""
            return
        stamps: list[str] = []
        for path in paths:
            try:
                stat = path.stat()
                stamps.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                stamps.append(f"{path.name}:missing")
        mtime = "|".join(stamps)
        if not force and mtime == self._mtime:
            return
        urls: set[tuple[str, str, int | None, str, str]] = set()
        hosts: set[str] = set()
        digest = hashlib.sha256()
        for path in paths:
            try:
                content = path.read_bytes()
            except OSError:
                continue
            digest.update(content)
            try:
                text = content.decode("utf-8-sig")
            except UnicodeError:
                continue
            for line in text.splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                if "://" in entry:
                    key = _exact_url_key(entry)
                    if key is not None:
                        urls.add(key)
                    continue
                host = entry.lower().strip().strip(".")
                if host:
                    hosts.add(host)
        self._urls, self._hosts, self._mtime = urls, hosts, mtime
        self._revision = digest.hexdigest()

    def match(self, url: str) -> str | None:
        self.reload()
        if self._urls and _exact_url_key(url) in self._urls:
            return "URL 命中黑名单"
        host = _host_of(url)
        if not host:
            return None
        labels = host.split(".")
        for index in range(len(labels) - 1):
            candidate = ".".join(labels[index:])
            if candidate in self._hosts:
                return f"域名命中黑名单 {candidate}"
        return None


class SafetyScorer:
    def __init__(self, blocklist: Blocklist) -> None:
        self._blocklist = blocklist

    @property
    def blocklist(self) -> Blocklist:
        return self._blocklist

    def evaluate(self, url: str) -> SafetyReport:
        hit = self._blocklist.match(url)
        if hit:
            return SafetyReport(blocked=True, risk=1.0, reasons=(hit,))

        risk = 0.0
        reasons: list[str] = []
        try:
            parts = urlsplit(url)
        except ValueError:
            return SafetyReport(blocked=True, risk=1.0, reasons=("URL 无法解析",))
        host = (parts.hostname or "").lower().rstrip(".")

        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        if tld in SUSPICIOUS_TLDS:
            risk += 0.15
            reasons.append(f"可疑顶级域 .{tld}")

        shape = self._url_shape(parts, host, url)
        if shape:
            risk += 0.10
            reasons.append(shape)

        lookalike = self._lookalike(host)
        if lookalike:
            risk += 0.10
            reasons.append(lookalike)

        risk = round(min(risk, 1.0), 3)
        return SafetyReport(blocked=risk >= BLOCK_THRESHOLD, risk=risk, reasons=tuple(reasons))

    @staticmethod
    def _url_shape(parts, host: str, url: str) -> str | None:
        if IPV4.match(host):
            return "IP 直连"
        try:
            labels = [label for label in host.split(".") if label]
        except ValueError:
            return None
        if len(labels) >= 5:
            return "子域层级过多"
        if len(url) > 180:
            return "URL 过长"
        if LONG_RANDOM_PATH.search(parts.path or ""):
            return "路径含长随机串"
        return None

    @staticmethod
    def _lookalike(host: str) -> str | None:
        if "xn--" in host:
            return "IDN 编码域名"
        label = host.split(".")[0] if "." in host else host
        if "0" in label and "o" in label:
            return "形近字符 0/o"
        if "rn" in label and "m" in label:
            return "形近字符 rn/m"
        if "1" in label and "l" in label:
            return "形近字符 1/l"
        return None