"""CI 用：等待服务就绪（轮询 /api/health），最多 30 秒。"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000") + "/api/health"
deadline = time.time() + 30
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if json.load(response).get("status") == "ok":
                print("ready")
                raise SystemExit(0)
    except Exception:
        pass
    time.sleep(0.25)
print("not ready", file=sys.stderr)
raise SystemExit(1)
