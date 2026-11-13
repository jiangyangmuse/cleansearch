"""前端 Web Vitals 与搜索耗时上报：进程内环形缓冲，供 /api/metrics 查看。"""

from __future__ import annotations

import threading
import time
from collections import deque

_MAX_SAMPLES = 200
_samples: deque[dict] = deque(maxlen=_MAX_SAMPLES)
_lock = threading.Lock()


def record_vitals(sample: dict) -> None:
    entry = {"at": int(time.time()), **sample}
    with _lock:
        _samples.append(entry)


def vitals_snapshot() -> dict:
    with _lock:
        recent = list(_samples)[-20:]
        total = len(_samples)
    return {"count": total, "recent": recent}
