"""风险跳转中转：/go?u=<base64url>&sig=<hmac>。

签名用本地 token 做 HMAC key，避免 /go 变成开放重定向。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import quote


def _b64encode(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str | None:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def sign_url(url: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), url.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:32]


def build_go_path(url: str, secret: str) -> str:
    return f"/go?u={_b64encode(url)}&sig={sign_url(url, secret)}"


def verify_go(u: str, sig: str, secret: str) -> str | None:
    if not sig or not sig.isascii():
        return None
    url = _b64decode(u)
    if not url:
        return None
    expected = sign_url(url, secret)
    if not hmac.compare_digest(expected, sig):
        return None
    return url


def escape(value: str) -> str:
    return quote(value, safe="")
