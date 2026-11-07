"""Audit the hosted-CI/credits handoff without repeating model calls."""
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REPORT = "reports/completed/2026-11-08-0212-hosted-ci-credits.md"
errors = []


def git(*args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=ROOT).decode("utf-8-sig").replace("\r\n", "\n")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8-sig")


proof = json.loads(read("reports/assets/hosted-ci-credit/hosted-ci.json"))
sha = proof["verified_code_sha"]
run = proof["runs"][0]
if run["sha"] != sha or run["status"] != "completed" or run["conclusion"] != "success":
    errors.append("Hosted run and verified code do not match")
for job in proof["latest_jobs"]:
    if job["conclusion"] != "success" or any(s["conclusion"] != "success" for s in job["steps"]):
        errors.append("Hosted job/step did not pass")
step_names = {s["name"] for j in proof["latest_jobs"] for s in j["steps"]}
if "Browser acceptance validator tests" not in step_names or proof["hosted_api_tests"] != 323:
    errors.append("Current validator/API tests not covered")
changed_code = git("diff", sha, "--", "apps", "scripts", ".github", "docker-compose.yml", "searxng")
if changed_code:
    errors.append("Product code differs from hosted verified SHA")

tree = git("ls-tree", "-r", "--name-only", sha, "reports").splitlines()
old_reports = [p for p in tree if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", Path(p).name)]
for rel in old_reports:
    if read(rel) != git("show", sha + ":" + rel):
        errors.append("Historical report changed: " + rel)
old_rows = re.findall(r"(?m)^\| \d{8}-\d{4} \|.*$", git("show", sha + ":reports/INDEX.md"))
rows = re.findall(r"(?m)^\| \d{8}-\d{4} \|.*$", read("reports/INDEX.md"))
if any(rows.count(row) != 1 for row in old_rows):
    errors.append("Historical ledger row changed")
targets = []
for row in rows:
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    target = re.search(r"\]\(([^)]+)\)", cells[2]).group(1)
    targets.append(target)
    status = re.search(r"\|\s*状态\s*\|\s*(\S+)\s*\|", read("reports/" + target))
    if not status or status.group(1) != cells[4] or cells[5].strip("`") != target:
        errors.append("Ledger/header/path mismatch: " + target)
if targets[0] != REPORT.removeprefix("reports/") or "| 完成 |" not in rows[0]:
    errors.append("Current report must be completed and archived at ledger top")
files = {p.relative_to(ROOT / "reports").as_posix() for p in (ROOT / "reports").rglob("*.md")
         if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}-", p.name)}
if files != set(targets) or len(targets) != len(set(targets)):
    errors.append("Report files and ledger do not correspond")

docs = ["CONTRIBUTORS.md", "README.md", "docs/进展与欠账.md", "docs/决策与接口变更.md", "reports/INDEX.md", REPORT]
stats, links = {}, {}
for rel in docs:
    text = read(rel)
    stats[rel] = {"lines": len(text.splitlines()), "non_whitespace_chars": len(re.sub(r"\s", "", text))}
    prose = re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)
    count = 0
    for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", prose):
        parts = urlsplit(target.strip().strip("<>"))
        if parts.scheme or parts.netloc:
            continue
        dest = (ROOT / rel).parent / unquote(parts.path) if parts.path else ROOT / rel
        if not dest.exists():
            errors.append(f"Missing link: {rel} -> {target}")
        elif parts.fragment and dest.suffix == ".md":
            titles = re.findall(r"(?m)^#{1,6}\s+(.+)$", dest.read_text(encoding="utf-8-sig"))
            slugs = {re.sub(r"\s", "-", re.sub(r"[^\w\-\s]", "", t.lower().replace("`", ""))) for t in titles}
            if unquote(parts.fragment) not in slugs:
                errors.append(f"Missing heading: {rel} -> {target}")
        count += 1
    links[rel] = count
credits = read("CONTRIBUTORS.md")
if "| Codex | AI 协作工具 |" not in credits or "| DeepSeek Harness（DSH） | AI 协作工具 |" not in credits:
    errors.append("AI tool credits missing or mislabelled")
suite = ET.parse(HERE / "prepublish-api-tests.xml").getroot().find("testsuite")
if suite.attrib["tests"] != "323" or int(suite.attrib["failures"]) or int(suite.attrib["errors"]):
    errors.append("Local prepublication API regression did not pass")
tracked = git("ls-files").splitlines()
if any(p == ".env" or p.startswith("data/") or p.endswith((".pem", ".key")) for p in tracked):
    errors.append("Sensitive local configuration path tracked")

result = {"status": "pass" if not errors else "fail", "verified_code_sha": sha,
          "run_url": run["url"], "hosted_api_tests": 323, "local_api_tests": 323,
          "product_tree_matches_verified_commit": not changed_code,
          "credit_mode": "published project file; no fabricated GitHub account attribution",
          "historical_reports_preserved": len(old_reports), "historical_ledger_rows_preserved": len(old_rows),
          "ledger_reports": len(rows), "relative_links_checked": links, "artifacts": stats, "errors": errors}
(HERE / "document-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "artifacts"}, ensure_ascii=True, indent=2))
raise SystemExit(bool(errors))
