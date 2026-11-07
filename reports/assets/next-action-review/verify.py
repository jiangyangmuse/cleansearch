"""Recheck this review's artifacts, links, ledger, and preserved history."""
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REPORT = "reports/2026-11-07-1659-next-action-review.md"
OUT = HERE / "validation.json"
OUT.write_text('{"status":"running"}\n', encoding="utf-8")
errors = []


def read(path):
    return path.read_text(encoding="utf-8-sig")


def git(*args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=ROOT).decode("utf-8-sig").replace("\r\n", "\n")


def headings(text):
    titles = re.findall(r"(?m)^#{1,6}\s+(.+)$", text)
    return {re.sub(r"\s", "-", re.sub(r"[^\w\-\s]", "", title.lower().replace("`", ""))) for title in titles}


docs = ["README.md", "docs/进展与欠账.md", "docs/决策与接口变更.md",
        "reports/INDEX.md", REPORT, "reports/assets/next-action-review/manual-quality.md"]
counts = {}
stats = {}
for rel in docs:
    text = read(ROOT / rel)
    stats[rel] = {"lines": len(text.splitlines()), "non_whitespace_chars": len(re.sub(r"\s", "", text))}
    text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)
    count = 0
    for link in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", text):
        parts = urlsplit(link.strip().strip("<>"))
        if parts.scheme or parts.netloc:
            continue
        dest = (ROOT / rel).parent / unquote(parts.path) if parts.path else ROOT / rel
        if not dest.exists():
            errors.append(f"Missing link: {rel} -> {link}")
        elif parts.fragment and dest.suffix == ".md" and unquote(parts.fragment) not in headings(read(dest)):
            errors.append(f"Missing heading: {rel} -> {link}")
        count += 1
    counts[rel] = count

old_index = git("show", "HEAD:reports/INDEX.md")
index = read(ROOT / "reports/INDEX.md")
old_rows = re.findall(r"(?m)^\| \d{8}-\d{4} \|.*$", old_index)
rows = re.findall(r"(?m)^\| \d{8}-\d{4} \|.*$", index)
if any(rows.count(row) != 1 for row in old_rows):
    errors.append("Historical ledger rows changed")
old_reports = [name for name in git("ls-tree", "-r", "--name-only", "HEAD", "reports").splitlines()
               if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", Path(name).name)]
for rel in old_reports:
    # Normalize Git checkout line endings, preserving report content exactly.
    if read(ROOT / rel) != git("show", "HEAD:" + rel):
        errors.append("Historical report changed: " + rel)
targets = []
for row in rows:
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    target = re.search(r"\]\(([^)]+)\)", cells[2]).group(1)
    targets.append(target)
    header = re.search(r"\|\s*状态\s*\|\s*(\S+)\s*\|", read(ROOT / "reports" / target))
    if not header or header.group(1) != cells[4] or cells[5].strip("`") != target:
        errors.append("Ledger/header/path mismatch: " + target)
files = {path.relative_to(ROOT / "reports").as_posix() for path in (ROOT / "reports").rglob("*.md")
         if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", path.name)}
if set(targets) != files or len(targets) != len(set(targets)):
    errors.append("Report files and ledger do not match")
if "--final" in sys.argv and (targets[0] != Path(REPORT).name or "| 部分完成 |" not in rows[0]):
    errors.append("Expected current partial report at ledger top, in reports root")

tests = ET.parse(HERE / "api-tests.xml").getroot().find("testsuite")
if int(tests.attrib["tests"]) < 1 or int(tests.attrib["failures"]) or int(tests.attrib["errors"]):
    errors.append("API JUnit failure")
summary = json.loads(read(HERE / "summary-12-reassessed.json"))
if len(summary["rows"]) != 12 or not all(row["assessment"]["passed"] for row in summary["rows"]):
    errors.append("Summary protocol/citation reassessment failure")
browser_checks = {}
for name in ("extension", "android-emulation"):
    data = json.loads(read(HERE / "browser" / f"{name}.json"))
    browser_checks[name] = len(data["checks"])
    if not data["passed"] or not all(check["ok"] for check in data["checks"]):
        errors.append("Browser automation failure: " + name)
gate = json.loads(read(HERE / "rdap-controls.json"))["fresh_reference_gate"]
load = json.loads(read(HERE / "rdap-concurrency.json"))
if load["peak_network_concurrency"] > 4 or load["active_after_completion"]:
    errors.append("RDAP concurrency failure")

# Scan only this task's changed/new source and artifacts, never echoing values.
secrets = []
env_file = ROOT / ".env"
if env_file.exists():
    for line in read(env_file).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            if key.strip().endswith("API_KEY") and len(value) >= 16:
                secrets.append(value.encode())
key_file = ROOT / "data/deepseek-api-key.txt"
if key_file.exists():
    value = read(key_file).strip().encode()
    if len(value) >= 16:
        secrets.append(value)
source_paths = git("diff", "--name-only", "HEAD").splitlines() + git("ls-files", "--others", "--exclude-standard").splitlines()
for rel in source_paths:
    path = ROOT / rel
    if path.is_file() and any(value in path.read_bytes() for value in secrets):
        errors.append("Configured credential found in changed artifact: " + rel)

result = {"acceptance_status": "partial", "automation_audit_passed": not errors,
          "historical_reports_preserved": len(old_reports), "historical_ledger_rows_preserved": len(old_rows),
          "ledger_reports": len(rows), "top_report": targets[0], "relative_links_checked": counts,
          "api_tests": int(tests.attrib["tests"]), "browser_checks": browser_checks,
          "summary_protocol": summary["summary"], "fresh_reference_gate": gate,
          "configured_credential_scan": "pass" if not any("credential" in e for e in errors) else "fail",
          "artifacts": stats, "errors": errors}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key != "artifacts"}, ensure_ascii=True, indent=2))
raise SystemExit(bool(errors))
