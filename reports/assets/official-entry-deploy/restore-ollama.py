"""为已选择且已安装的本地模型补齐缺失端点，仅改变 LLM_BASE_URL。"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.request import urlopen
import psutil

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
BACKUP = ROOT / "data/official-deploy-backup-20261108-1620"
ENDPOINT = "http://127.0.0.1:11434/v1"


def get(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


pids = {c.pid for c in psutil.net_connections(kind="tcp") if c.status == "LISTEN" and c.laddr.port == 8000}
assert len(pids) == 1
proc = psutil.Process(pids.pop())
command, cwd, env = proc.cmdline(), Path(proc.cwd()), proc.environ()
assert cwd.resolve() == (ROOT / "apps/api").resolve() and "uvicorn" in command and "app.main:app" in command
assert env.get("LLM_PROVIDER") == "openai" and not env.get("LLM_BASE_URL")
assert env.get("LLM_MODEL") in {m["name"] for m in get("http://127.0.0.1:11434/api/tags")["models"]}
dotenv = ROOT / ".env"
original = dotenv.read_bytes()
encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
text = original.decode(encoding)
updated, count = re.subn(r"(?m)^(LLM_BASE_URL=)[ \t]*(\r?)$", lambda m: m[1] + ENDPOINT + m[2], text)
assert count == 1, "项目端点不再为空，停止以避免覆盖并发配置"
backup = BACKUP / ".env-before-ollama"
assert not backup.exists()
backup.write_bytes(original)
assert proc.environ() == env and dotenv.read_bytes() == original
dotenv.write_bytes(updated.encode(encoding))
new_env = dict(env, LLM_BASE_URL=ENDPOINT)
proc.terminate()
proc.wait(timeout=15)
with (ROOT / "data/native-api-official-deploy.log").open("ab") as log:
    started = subprocess.Popen(command, cwd=cwd, env=new_env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        health = get("http://127.0.0.1:8000/api/health")
        if health["status"] == "ok":
            break
    except Exception:
        if started.poll() is not None:
            raise RuntimeError("API 启动失败，原配置备份保留；检查本地部署日志")
        time.sleep(.3)
else:
    raise RuntimeError("API 未就绪")
actual_env = psutil.Process(started.pid).environ()
changed = sorted(key for key in set(env) | set(actual_env) if env.get(key) != actual_env.get(key))
assert changed == ["LLM_BASE_URL"], "除了模型端点还有环境变更"
payload = {"old_pid": proc.pid, "new_pid": started.pid, "model": health["llm_model"],
           "changed_settings": changed, "endpoint": ENDPOINT, "other_environment_preserved": True,
           "dotenv_only_change": "LLM_BASE_URL: empty -> local Ollama", "backup": str(backup)}
(OUT / "model-endpoint-restored.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
