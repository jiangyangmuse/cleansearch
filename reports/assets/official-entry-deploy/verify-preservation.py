"""部署最终只读核对；只保存计数/摘要、配置名与公开的模型名。"""
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.request import urlopen
import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
before = json.loads((OUT / "before.json").read_text(encoding="utf-8"))
db = Path(before["db_path"])
tables = {}
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
    for table in ("bookmarks", "bookmark_groups", "bookmark_tags"):
        rows = conn.execute("SELECT * FROM " + table).fetchall()
        encoded = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
        tables[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest()}
pids = {c.pid for c in psutil.net_connections(kind="tcp") if c.status == "LISTEN" and c.laddr.port == 8000}
assert len(pids) == 1
proc = psutil.Process(pids.pop())
env = proc.environ()
token = Path(env.get("API_TOKEN_PATH", str(ROOT / "data/api-token.txt")))
token = token if token.is_absolute() else ROOT / token
token_preserved = hashlib.sha256(token.read_bytes()).hexdigest() == before["token_sha256"]
with urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
    health = json.load(response)
with urlopen("http://127.0.0.1:8000/api/openapi.json", timeout=3) as response:
    schema = json.load(response)
with urlopen("http://127.0.0.1:8000/", timeout=3) as response:
    index_hash = hashlib.sha256(response.read()).hexdigest()
upstream_pids = {c.pid for c in psutil.net_connections(kind="tcp") if c.status == "LISTEN" and c.laddr.port == 8888}
summary = json.loads((OUT / "summary-live.json").read_text(encoding="utf-8"))
models = [e["data"]["model"] for e in summary["events"] if e["event"] == "meta"]
result = {"final_pid": proc.pid, "db_path": str(db), "tables": tables,
          "tables_preserved": tables == before["tables"], "token_preserved": token_preserved,
          "searxng_preserved": upstream_pids == {before["searxng_pid"]},
          "provider": health["provider"], "official_loaded": "official" in schema["components"]["schemas"]["SearchResponse"]["properties"],
          "actual_summary_models": models, "configured_model": health["llm_model"],
          "model_endpoint": env.get("LLM_BASE_URL"), "cache_enabled": env.get("CACHE_ENABLED"),
          "index_matches_build": index_hash == hashlib.sha256((ROOT / "apps/web/dist/index.html").read_bytes()).hexdigest(),
          "review_sources_unchanged": all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == value for p, value in before["source_hashes"].items())}
assert all(result[key] for key in ("tables_preserved", "token_preserved", "searxng_preserved", "official_loaded", "index_matches_build", "review_sources_unchanged"))
assert models == [health["llm_model"]] and models[0] != "stub-extractive"
(OUT / "preservation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
