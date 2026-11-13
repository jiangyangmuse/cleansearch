"""日常 Bing 与快照/数据保留核对，不调用付费接口或模型。"""
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.request import Request, urlopen
import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
before = json.loads((OUT / "before.json").read_text(encoding="utf-8"))
db = Path(before["db_path"])
payloads = {}
source_checks = []
with sqlite3.connect(db.as_uri()+"?mode=ro", uri=True) as conn:
    for query in ("deepseek !b", "deepseek 官网 !b"):
        request = Request("http://127.0.0.1:8000/api/search", json.dumps({"q":query}).encode(), {"Content-Type":"application/json"})
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
        payloads[query] = body
        entries = body["official"]["entries"]
        ordinary = [item for group in body["groups"].values() for item in group]
        expected = [(e["id"],e["url"]) for e in entries if e["origin"]=="search"] + [(e["id"],e["url"]) for e in ordinary if not e["brand_warning"]]
        row = conn.execute("SELECT sources FROM search_sessions WHERE sid=?",(body["meta"]["sid"],)).fetchone()
        actual = [(s["result_id"],s["url"]) for s in json.loads(row[0])] if row else []
        assert actual == expected
        assert body["meta"]["engines"] == ["bing"] and all(e["engine"]==[] for e in entries if e["origin"]=="directory")
        source_checks.append({"query":query,"summary_sources":len(actual),"directory_excluded":True,"warning_excluded":True})
    tables = {}
    for name in ("bookmarks", "bookmark_groups", "bookmark_tags"):
        rows = conn.execute("SELECT * FROM "+name).fetchall()
        encoded = sorted(json.dumps(r,ensure_ascii=False,default=str) for r in rows)
        tables[name] = {"count":len(rows),"sha256":hashlib.sha256("\n".join(encoded).encode()).hexdigest()}
pids = {c.pid for c in psutil.net_connections(kind="tcp") if c.status=="LISTEN" and c.laddr.port==8000}
assert len(pids)==1
proc = psutil.Process(pids.pop())
env = proc.environ()
token = Path(env.get("API_TOKEN_PATH",str(ROOT/"data/api-token.txt")))
token = token if token.is_absolute() else ROOT/token
upstream = {c.pid for c in psutil.net_connections(kind="tcp") if c.status=="LISTEN" and c.laddr.port==8888}
result = {"pid":proc.pid,"db_preserved":tables==before["tables"],"token_preserved":hashlib.sha256(token.read_bytes()).hexdigest()==before["token_sha256"],
          "upstream_preserved":upstream=={before["searxng_pid"]},"model":env.get("LLM_MODEL"),"model_endpoint":env.get("LLM_BASE_URL"),
          "cache_enabled":env.get("CACHE_ENABLED"),"source_checks":source_checks}
assert all(result[k] for k in ("db_preserved","token_preserved","upstream_preserved"))
(OUT/"after-api.json").write_text(json.dumps(payloads,ensure_ascii=False,indent=2),encoding="utf-8")
(OUT/"preservation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=False))
