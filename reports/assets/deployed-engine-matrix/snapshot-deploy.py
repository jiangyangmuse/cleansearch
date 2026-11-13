"""只输出正式书签表计数/摘要与 token 摘要，不输出行内容或凭据。"""

import argparse
import json
import subprocess
from pathlib import Path

CODE = r'''
import hashlib, json, sqlite3
from pathlib import Path
source = sqlite3.connect('file:/data/cs.db?mode=ro', uri=True)
target = sqlite3.connect('/tmp/cs-deploy-snapshot.db')
source.backup(target)
source.close()
tables = {}
for name in ('bookmarks', 'bookmark_groups', 'bookmark_tags'):
    rows = target.execute('SELECT * FROM ' + name).fetchall()
    encoded = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    tables[name] = {'count': len(rows), 'sha256': hashlib.sha256('\n'.join(encoded).encode()).hexdigest()}
target.close()
token = Path('/data/api-token.txt')
print(json.dumps({'tables': tables, 'token_sha256': hashlib.sha256(token.read_bytes()).hexdigest() if token.exists() else None}))
'''

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", required=True)
parser.add_argument("--backup-dir")
parser.add_argument("--read-volume", action="store_true", help="容器未运行时只读挂载原卷核对")
args = parser.parse_args()
command = ["docker", "run", "--rm", "--network", "none", "--mount",
           "type=volume,source=llq_bookmarks,target=/data,readonly", "llq-api", "python", "-c", CODE] if args.read_volume else ["docker", "exec", "cs-api", "python", "-c", CODE]
assert not (args.read_volume and args.backup_dir), "只读核对时不导出备份"
result = subprocess.run(command,
                        capture_output=True, text=True, check=True)
payload = json.loads(result.stdout)
Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
if args.backup_dir:
    backup = Path(args.backup_dir)
    backup.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "cp", "cs-api:/tmp/cs-deploy-snapshot.db", str(backup / "cs.db")], check=True)
print(json.dumps({"tables": {name: item["count"] for name, item in payload["tables"].items()},
                  "token_present": payload["token_sha256"] is not None}))
