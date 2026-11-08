"""隔离 API：两次公开查询验证真实付费兜底；不读取或输出凭据。"""

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18173"


def search(q, page=1):
    request = Request(f"{BASE}/api/search", data=json.dumps({"q": q, "page": page}).encode(),
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=25)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


rows = []
for q, page in [("python 文档 !g", 1), ("python 文档 !g", 1),
                ("attention is all you need !sc", 1), ("python 文档 !g", 2)]:
    status, body = search(q, page)
    row = {"q": q, "page": page, "http": status}
    if status == 200:
        row.update({"parsed": body["parsed"], "meta": body["meta"],
                    "urls": [item["url"] for group in body["groups"].values() for item in group][:3]})
    else:
        row["error"] = body["error"]
    rows.append(row)
Path(__file__).with_name("live-api.json").write_text(json.dumps({
    "scope": "受控断开 SearXNG（本机 port 1），真实 Serper；非 13 引擎在线重验", "rows": rows,
}, ensure_ascii=False, indent=2), encoding="utf-8")
assert all(row["http"] == 200 and row["meta"]["engines"] == ["serper"] for row in rows[:3]), rows
assert not rows[0]["meta"]["cached"] and rows[1]["meta"]["cached"], rows
assert rows[3]["http"] == 503 and rows[3]["error"]["code"] == "UPSTREAM_UNAVAILABLE", rows
print(json.dumps([{key: row.get(key) for key in ("q", "page", "http")} |
                  {"total": row.get("meta", {}).get("total"), "cached": row.get("meta", {}).get("cached")}
                  for row in rows], ensure_ascii=False))
