"""只重启已核对的原生 API；配置只在内存传递，书签与令牌先备份。"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
from urllib.request import urlopen

import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
BACKUP = ROOT / "data" / "bing-retrieval-backup-20261108-1708"


def get(path):
    with urlopen("http://127.0.0.1:8000" + path, timeout=3) as response:
        return json.load(response)


def listener(port):
    pids = {c.pid for c in psutil.net_connections(kind="tcp")
            if c.status == "LISTEN" and c.laddr.port == port}
    assert len(pids) == 1, f"{port} 归属不唯一"
    return psutil.Process(pids.pop())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def tables(db):
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        data = {}
        for table in ("bookmarks", "bookmark_groups", "bookmark_tags"):
            rows = conn.execute("SELECT * FROM " + table).fetchall()
            values = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
            data[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(values).encode()).hexdigest()}
        return data


proc = listener(8000)
command, cwd, env = proc.cmdline(), Path(proc.cwd()), proc.environ()
assert cwd.resolve() == (ROOT / "apps/api").resolve()
assert "uvicorn" in command and "app.main:app" in command
assert "--reload" not in command and "--workers" not in command
assert env.get("SEARCH_PROVIDER") == "searxng"
db = Path(env["DB_PATH"]).resolve()
assert db.is_relative_to(ROOT / "data") and db.is_file()
token = Path(env.get("API_TOKEN_PATH", str(ROOT / "data/api-token.txt")))
token = token.resolve() if token.is_absolute() else (ROOT / token).resolve()
assert token.is_relative_to(ROOT / "data") and token.is_file()
upstream_pid = listener(8888).pid
before_health = get("/api/health")
before_schema = get("/api/openapi.json")
config_keys = set(re.findall(r'(?:_env\w*|_path)\("([A-Z_]+)"', (ROOT / "apps/api/app/config.py").read_text(encoding="utf-8")))
source_paths = ["apps/api/app/core/aggregator.py", "apps/api/app/core/scoring.py", "apps/api/app/core/official.py", "apps/api/app/routers/search.py", "apps/api/app/schemas.py", "apps/web/dist/index.html"]
source_hashes = {path: digest(ROOT / path) for path in source_paths}
before = {"pid": proc.pid, "create_time": proc.create_time(), "db_path": str(db),
          "tables": tables(db), "token_sha256": digest(token), "searxng_pid": upstream_pid,
          "official_loaded": "official" in before_schema["components"]["schemas"]["SearchResponse"]["properties"],
          "source_hashes": source_hashes, "model": before_health["llm_model"], "provider": before_health["provider"]}
BACKUP.mkdir(parents=True, exist_ok=False)
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(BACKUP / "cs.db") as dst:
    src.backup(dst)
shutil.copy2(token, BACKUP / "api-token.txt")
assert tables(BACKUP / "cs.db") == before["tables"]
assert digest(BACKUP / "api-token.txt") == before["token_sha256"]
(OUT / "before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
# 在停止前再次确认进程、代码和数据未发生并发替换。
assert listener(8000).pid == proc.pid and proc.cmdline() == command and proc.environ() == env
assert {path: digest(ROOT / path) for path in source_paths} == source_hashes
assert tables(db) == before["tables"] and digest(token) == before["token_sha256"]
proc.terminate()
proc.wait(timeout=15)
with (ROOT / "data/native-api-official-deploy.log").open("ab") as log:
    started = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        health = get("/api/health")
        schema = get("/api/openapi.json")["components"]["schemas"]
        assert "official" in schema["SearchResponse"]["properties"]
        assert all(key in schema["OfficialLink"]["properties"] for key in ("id", "snippet", "risk", "go_url", "origin", "brand_warning"))
        break
    except Exception:
        if started.poll() is not None:
            raise RuntimeError("API 启动失败；原库和令牌备份保留，查看 data/native-api-official-deploy.log")
        time.sleep(.3)
else:
    raise RuntimeError("API 未就绪，检查日志；未迁移原库或令牌")
after_proc = listener(8000)
after_env = after_proc.environ()
after = {"old_pid": before["pid"], "new_pid": after_proc.pid, "healthy": health["status"] == "ok",
         "official_loaded": True, "provider": health["provider"], "model": health["llm_model"],
         "config_preserved": all(env.get(key) == after_env.get(key) for key in config_keys),
         "config_keys_checked": sorted(config_keys), "db_preserved": tables(db) == before["tables"],
         "token_preserved": digest(token) == before["token_sha256"],
         "searxng_preserved": listener(8888).pid == upstream_pid,
         "backup_dir": str(BACKUP), "cache_enabled": after_env.get("CACHE_ENABLED"),
         "source_hashes": {path: digest(ROOT / path) for path in source_paths}}
(OUT / "restart.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
assert all(after[key] for key in ("healthy", "config_preserved", "db_preserved", "token_preserved", "searxng_preserved"))
print(json.dumps({key: value for key, value in after.items() if key not in ("config_keys_checked", "source_hashes")}, ensure_ascii=False))
