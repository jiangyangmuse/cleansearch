"""CI 冒烟：与 scripts/smoke.ps1 对齐的跨平台版本（不依赖 PowerShell）。

在 fixture 形态下验证：三态搜索、分档、缓存、后缀路由、黑名单、零结果、
上游不可用、SSE 总结与引用、书签只读、SSRF 拦截、跨域 token、同源首页。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"} if data else {}
    if headers:
        hdrs.update(headers)
    request = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    def decode(raw: bytes):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None  # 首页是 HTML，调用方只看状态码

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, decode(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, decode(exc.read())


def search(body: dict):
    return call("POST", "/api/search", body)


status, health = call("GET", "/api/health")
check("health 200", status == 200 and health["status"] == "ok",
      f"provider={health['provider']} web_built={health['web_built']} blocklist={health['blocklist_rules']}")

_, hit = search({"q": "python 文档"})
check("有结果", hit["meta"]["status"] == "ok" and hit["meta"]["upstream_total"] >= 10,
      f"total={hit['meta']['total']} upstream={hit['meta']['upstream_total']}")

groups = hit["groups"]
check("三档分组", all(len(groups[key]) >= 1 for key in ("strong", "related", "weak")),
      "/".join(str(len(groups[key])) for key in ("strong", "related", "weak")))

_, cached = search({"q": "python 文档"})
check("缓存命中", cached["meta"]["cached"] is True, f"cached={cached['meta']['cached']}")

_, routed = search({"q": "python 文档 g"})
check("后缀路由", routed["parsed"]["engine"] == "google" and routed["parsed"]["router"] == "suffix",
      f"engine={routed['parsed']['engine']} router={routed['parsed']['router']}")

_, guarded = search({"q": "C g"})
check("C g 不误触发", guarded["parsed"]["router"] == "default", f"router={guarded['parsed']['router']}")

_, risky = search({"q": "账号验证", "opts": {"fixture": "risky"}})
check("黑名单拦截", risky["meta"]["filtered"]["risk"] == 1,
      f"risk={risky['meta']['filtered']['risk']} upstream={risky['meta']['upstream_total']}")

_, empty = search({"q": "test", "opts": {"fixture": "empty"}})
check("零结果", empty["meta"]["status"] == "empty" and empty["meta"]["total"] == 0, f"total={empty['meta']['total']}")

status, failure = search({"q": "test", "opts": {"fixture": "error"}})
check("上游不可用", status == 503 and failure["error"]["code"] == "UPSTREAM_UNAVAILABLE",
      f"status={status} code={failure['error']['code'] if failure else ''}")

sid = hit["meta"]["sid"]
with urllib.request.urlopen(f"{BASE}/api/summarize?sid={sid}&mode=fast", timeout=60) as response:
    raw = response.read().decode("utf-8", "replace")
events = [(name, json.loads(data)) for name, data in re.findall(r"(?m)^event: (\w+)\r?\ndata: ([^\r\n]+)", raw)]
cites = [data for name, data in events if name == "cite"]
tokens = [data for name, data in events if name == "token"]
errors = [data for name, data in events if name == "error"]
result_ids = {item["id"] for group in groups.values() for item in group}
text = "".join(item["t"] for item in tokens)
references = [int(value) for value in re.findall(r"\[(\d+)\]", text)]
cite_indexes = {item["i"] for item in cites}
ok = (
    len(events) >= 4
    and events[0][0] == "meta"
    and events[0][1]["model"] == health["llm_model"]
    and events[-1][0] == "done"
    and not errors
    and cites
    and all(item["result_id"] in result_ids for item in cites)
    and references
    and all(value in cite_indexes for value in references)
)
check("侧栏总结 SSE", ok,
      f"provider={health['llm_provider']} model={health['llm_model']} cites={len(cites)} chunks={len(tokens)}")

status, _ = call("GET", "/api/summarize?sid=s_none&mode=fast")
check("过期快照 404", status == 404, f"status={status}")

status, bookmarks = call("GET", "/api/bookmarks?limit=1")
check("书签接口", status == 200 and "total" in bookmarks and "fts" in bookmarks,
      f"total={bookmarks['total']} fts={bookmarks['fts']}")

status, _ = call("POST", "/api/page/summarize", {"url": "http://127.0.0.1:8000/x"})
check("内网地址拦截", status == 403, f"status={status}")

status, _ = call("POST", "/api/bookmarks", {"url": "https://example.com/x"}, headers={"Origin": "http://evil.test"})
check("跨域 token 拦截", status == 401, f"status={status}")

status, _ = call("GET", "/")
check("同源首页", status == 200, f"status={status}")

for item in results:
    print(f"{item['check']:<14} {'True' if item['ok'] else 'False':<5} {item['detail']}")

failed = [item["check"] for item in results if not item["ok"]]
if failed:
    print("\n冒烟失败：" + ", ".join(failed))
    raise SystemExit(1)
print("\n冒烟通过")