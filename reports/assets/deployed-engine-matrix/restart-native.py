"""重启已核对的本项目原生 API；环境只在内存传递，不落盘或输出密钥。"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--label", default="initial", choices=("initial", "final"))
parser.add_argument("--restore-cache", action="store_true")
args = parser.parse_args()
prefix = "native" if args.label == "initial" else "native-final"
connections = [c for c in psutil.net_connections(kind="tcp") if c.status == "LISTEN" and c.laddr.port == 8000]
assert len({c.pid for c in connections}) == 1, "8000 进程归属不唯一"
proc = psutil.Process(connections[0].pid)
command, cwd, env = proc.cmdline(), Path(proc.cwd()), proc.environ()
assert cwd.resolve() == (ROOT / "apps/api").resolve() and "uvicorn" in command and "app.main:app" in command, "不是预期项目 API"
db = Path(env["DB_PATH"])
assert db.is_absolute() and db.is_relative_to(ROOT / "data"), "原生库不在本项目 data 中"
backup_dir = ROOT / "data/deploy-backup-20261108-1447" / prefix
backup_dir.mkdir(parents=True, exist_ok=True)
source = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
backup = sqlite3.connect(backup_dir / "cs.db")
source.backup(backup)
tables = {}
for name in ("bookmarks", "bookmark_groups", "bookmark_tags"):
    rows = backup.execute("SELECT * FROM " + name).fetchall()
    encoded = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    tables[name] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest()}
backup.close()
source.close()
token_path = Path(env.get("API_TOKEN_PATH", "data/api-token.txt"))
if not token_path.is_absolute():
    token_path = ROOT / token_path
token_hash = hashlib.sha256(token_path.read_bytes()).hexdigest() if token_path.exists() else None
before = {"db_path": str(db), "tables": tables, "token_sha256": token_hash, "old_pid": proc.pid,
          "command": command, "cwd": str(cwd), "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
(OUT / f"{prefix}-before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
if args.restore_cache:
    values = [line.split("=", 1)[1].strip() for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
              if line.strip().startswith("CACHE_ENABLED=")]
    assert len(values) == 1 and values[0].lower() in {"true", "false"}
    env["CACHE_ENABLED"] = values[0]
proc.terminate()
proc.wait(timeout=15)
with (ROOT / "data/native-api-deploy.log").open("ab") as log:
    started = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        with urlopen("http://127.0.0.1:8000/api/health", timeout=2) as response:
            health = json.load(response)
        with urlopen("http://127.0.0.1:8000/api/engines", timeout=2) as response:
            catalog = json.load(response)
        assert "selectable" in catalog["engines"][0]
        (OUT / f"{prefix}-restart.json").write_text(json.dumps({"old_pid": proc.pid, "launcher_pid": started.pid,
            "health": health, "preserved_env_except": ["CACHE_ENABLED"] if args.restore_cache else [],
            "cache_enabled": env.get("CACHE_ENABLED"), "preserved_db_path": str(db)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"healthy": True, "old_pid": proc.pid, "new_pid": started.pid,
                          "bookmarks": health["bookmarks"], "catalog_routes": len(catalog["engines"])}, ensure_ascii=False))
        break
    except Exception:
        time.sleep(0.3)
else:
    raise RuntimeError("重启未就绪；查看 data/native-api-deploy.log，原库与备份均保留")
