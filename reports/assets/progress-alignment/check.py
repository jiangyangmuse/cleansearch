"""Documentation-only audit; run from the workspace with `python <this-file>`."""

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASELINE = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
DOCS = ["docs/进展与欠账.md", "README.md", "reports/INDEX.md"]
errors = []


def read(path):
    return path.read_text(encoding="utf-8-sig")


def prose(text):
    return re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)


def headings(text):
    used = {}
    result = set()
    for title in re.findall(r"(?m)^#{1,6}\s+(.+)$", prose(text)):
        slug = re.sub(r"[^\w\-\s]", "", title.lower().replace("`", ""))
        slug = re.sub(r"\s", "-", slug)
        n = used.get(slug, 0)
        used[slug] = n + 1
        result.add(f"{slug}-{n}" if n else slug)
    return result


def check_links(rel):
    count = 0
    path = ROOT / rel
    for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", prose(read(path))):
        target = target.strip().strip("<>")
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            continue
        dest = path.parent / unquote(parts.path) if parts.path else path
        if not dest.exists():
            errors.append(f"Missing link: {rel} -> {target}")
        elif parts.fragment and dest.suffix == ".md":
            if unquote(parts.fragment) not in headings(read(dest)):
                errors.append(f"Missing heading: {rel} -> {target}")
        count += 1
    return count


for rel, expected in BASELINE["reports"].items():
    path = ROOT / rel
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        errors.append(f"Historical report changed: {rel}")

rows = [line for line in read(ROOT / "reports/INDEX.md").splitlines()
        if re.match(r"^\| \d{8}-\d{4} \|", line)]
for old in BASELINE["index_rows"]:
    if rows.count(old) != 1:
        errors.append(f"Historical ledger row changed: {old.split('|')[1].strip()}")

targets = []
states = {}
for row in rows:
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    target = re.search(r"\]\(([^)]+)\)", cells[2]).group(1)
    targets.append(target)
    state = cells[4]
    states[state] = states.get(state, 0) + 1
    if cells[5].strip("`") != target:
        errors.append(f"Ledger paths differ: {target}")
    path = ROOT / "reports" / target
    if path.exists():
        status = re.search(r"\|\s*状态\s*\|\s*(\S+)\s*\|", read(path))
        if not status or status.group(1) != state:
            errors.append(f"Ledger/header state mismatch: {target}")
        if target.startswith("completed/") and state != "完成":
            errors.append(f"Incomplete report archived: {target}")

report_paths = {path.relative_to(ROOT / "reports").as_posix()
                for path in (ROOT / "reports").rglob("*.md")
                if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", path.name)}
if len(targets) != len(set(targets)):
    errors.append("Duplicate ledger report paths")
if set(targets) != report_paths:
    errors.append("Report files and ledger targets differ")

task_reports = [target for target in targets if target.endswith("-progress-alignment.md")]
if len(task_reports) != 1:
    errors.append("Expected one progress-alignment report")
else:
    DOCS.append("reports/" + task_reports[0])
    if "--final" in sys.argv:
        if targets[0] != task_reports[0] or not task_reports[0].startswith("completed/"):
            errors.append("Current task must be the archived top ledger report")
        if "| 完成 |" not in rows[0]:
            errors.append("Current task is not complete")
counts = {rel: check_links(rel) for rel in DOCS}
stats = {rel: {"lines": len(read(ROOT / rel).splitlines()),
               "non_whitespace_chars": len(re.sub(r"\s", "", read(ROOT / rel)))}
         for rel in DOCS}
summary = {
    "scope": "documentation-only; no business test or live API rerun",
    "historical_reports_preserved": len(BASELINE["reports"]),
    "historical_ledger_rows_preserved": len(BASELINE["index_rows"]),
    "ledger_reports": len(rows),
    "ledger_states": states,
    "archived_reports": sum(target.startswith("completed/") for target in targets),
    "root_reports": sum(not target.startswith("completed/") for target in targets),
    "top_report": targets[0],
    "relative_links_checked": counts,
    "artifacts": stats,
    "errors": errors,
}
(HERE / "validation.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
raise SystemExit(bool(errors))
