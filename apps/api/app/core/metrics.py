"""轻量观测：按路由分组的请求计数、错误率与延迟分位。

进程内环形缓冲，不落盘；多 worker 时各进程独立统计（文档已注明）。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

WINDOW = 2000


def group_of(path: str) -> str:
    if path.startswith("/api/bookmarks"):
        return "/api/bookmarks"
    if path.startswith("/api/summarize"):
        return "/api/summarize"
    if path.startswith("/api/page/"):
        return "/api/page"
    if path.startswith("/api/tools"):
        return "/api/tools"
    if path.startswith("/api/search"):
        return "/api/search"
    if path == "/api/metrics":
        return "/api/metrics"
    if path.startswith("/api/"):
        return "/api/other"
    return "web"


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(ratio * (len(ordered) - 1)))))
    return round(ordered[index], 1)


@dataclass
class Sample:
    at: float
    group: str
    status: int
    ms: float


class Metrics:
    def __init__(self, window: int = WINDOW) -> None:
        self._samples: deque[Sample] = deque(maxlen=window)
        self._lock = threading.Lock()
        self.started_at = time.time()

    def record(self, path: str, status: int, ms: float) -> None:
        with self._lock:
            self._samples.append(Sample(time.time(), group_of(path), status, ms))

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)
        groups: dict[str, list[Sample]] = defaultdict(list)
        for sample in samples:
            groups[sample.group].append(sample)
        by_group = {}
        for name, items in sorted(groups.items()):
            latencies = [item.ms for item in items]
            errors = sum(1 for item in items if item.status >= 400)
            by_group[name] = {
                "count": len(items),
                "errors": errors,
                "error_rate": round(errors / len(items), 3) if items else 0.0,
                "p50_ms": percentile(latencies, 0.5),
                "p95_ms": percentile(latencies, 0.95),
            }
        overall = [item.ms for item in samples]
        return {
            "uptime_seconds": int(time.time() - self.started_at),
            "window": len(samples),
            "p50_ms": percentile(overall, 0.5),
            "p95_ms": percentile(overall, 0.95),
            "groups": by_group,
        }


_METRICS = Metrics()


def get_metrics() -> Metrics:
    return _METRICS


class RequestMetricsMiddleware:
    """响应正文发送完成后记账，流式响应包含生成和传输耗时。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        completed = False

        async def observe(message: Message) -> None:
            nonlocal status, completed
            kind = message["type"]
            if kind == "http.response.start":
                status = message["status"]
            await send(message)
            if kind == "http.response.pathsend" or (
                kind == "http.response.body" and not message.get("more_body", False)
            ):
                completed = True
                get_metrics().record(scope["path"], status, (time.perf_counter() - started) * 1000)

        try:
            await self.app(scope, receive, observe)
        except Exception:
            if not completed:
                get_metrics().record(scope["path"], 500, (time.perf_counter() - started) * 1000)
            raise
