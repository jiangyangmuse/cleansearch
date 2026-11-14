"""可分发入口：把 API + 前端产物打包成单目录，双击即可在本机跑起来。

打包后 `sys.executable` 位于发行目录根部，数据与静态资源都相对它定位；
所有路径都在 import app 之前写好（`app.config` 在 import 时就读环境变量）。
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _free_port(preferred: int) -> int:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_upstream(base_url: str, timeout: float = 150.0) -> bool:
    """等 SearXNG 起来：首次拉镜像可能要一两分钟，先轮询再启动服务。"""
    import urllib.request

    probe = base_url.rstrip("/") + "/search?q=test&format=json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(probe, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - 未就绪时的任何异常都只表示"再等等"
            time.sleep(2)
    return False


def main() -> None:
    base = _base_dir()
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)

    # 默认值全部指向发行目录；已存在的环境变量优先，方便高级用户覆盖。
    os.environ.setdefault("SEARCH_PROVIDER", "fixture")
    os.environ.setdefault("DB_PATH", str(data / "cs.db"))
    os.environ.setdefault("API_TOKEN_PATH", str(data / "api-token.txt"))
    os.environ.setdefault("FAVICON_DIR", str(data / "favicons"))
    os.environ.setdefault("FEED_OUTPUT_PATH", str(data / "blocklist-feeds.txt"))
    os.environ.setdefault("BLOCKLIST_PATH", str(base / "resources" / "blocklist.txt"))
    os.environ.setdefault("WEB_DIST", str(base / "web"))
    os.environ.setdefault("API_HOST", "127.0.0.1")
    # 打包版用纯 asyncio 事件循环，避免依赖 uvloop/httptools 的编译产物
    os.environ.setdefault("UVICORN_LOOP", "asyncio")

    if os.environ.get("SEARXNG_WAIT") == "1":
        upstream = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8891")
        print(f"等待 SearXNG 就绪：{upstream}（最多 150 秒）…")
        if _wait_upstream(upstream):
            print("SearXNG 已就绪，开始真实搜索模式。")
        else:
            print("SearXNG 150 秒内没起来，先以当前配置启动；搜索会返回上游不可用。")

    port = _free_port(int(os.environ.get("API_PORT", "8000")))
    url = f"http://127.0.0.1:{port}/"
    print(f"CleanSearch 正在启动：{url}")
    print("关闭这个窗口即停止服务。数据保存在 data/ 目录。")

    if os.environ.get("CLEANSEARCH_NO_BROWSER", "") != "1":
        threading.Thread(
            target=lambda: (time.sleep(2.0), webbrowser.open(url)), daemon=True
        ).start()

    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
