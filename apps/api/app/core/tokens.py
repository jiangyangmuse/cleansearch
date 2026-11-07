"""本地共享 token：给 bookmarklet / 浏览器扩展这类跨域写入用。

单用户本机应用，token 只是阻止「任意网页静默往你书签里塞链接」，
不是账号体系；文件权限按用户目录默认即可。
"""

from __future__ import annotations

import hmac
import os
import secrets
from threading import Lock
from pathlib import Path

_TOKEN_LOCK = Lock()


def read_api_token(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def get_api_token(path: Path) -> str:
    with _TOKEN_LOCK:
        existing = read_api_token(path)
        if existing:
            return existing
        token = secrets.token_urlsafe(24)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = read_api_token(path)
            if existing:
                return existing
            raise OSError("Token file is empty") from None
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(token)
        return token


def token_matches(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.strip().encode("utf-8"), expected.encode("utf-8"))
