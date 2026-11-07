// Shared browser acceptance helpers; no credential is written to evidence.
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

function loadPlaywright() {
  return require(require.resolve("playwright", {
    paths: [path.join(ROOT, "apps", "web"), ROOT],
  }));
}

function installable(manifest, response) {
  return !!manifest.data && Array.isArray(manifest.errors) && manifest.errors.length === 0
    && Array.isArray(response.installabilityErrors) && response.installabilityErrors.length === 0;
}

async function findBookmark(request, base, url) {
  for (let offset = 0; ; offset += 200) {
    const response = await request.get(`${base}/api/bookmarks?limit=200&offset=${offset}`);
    if (!response.ok()) throw new Error("Bookmark read HTTP " + response.status());
    const body = await response.json();
    const item = body.items.find((item) => item.url === url);
    if (item) return item;
    if (!body.items.length || offset + body.items.length >= body.total) return null;
  }
}

async function cleanup(request, base, urls) {
  for (const url of urls) {
    const item = await findBookmark(request, base, url);
    if (!item) continue;
    const response = await request.delete(`${base}/api/bookmarks/${item.id}`, {
      // Token requests intentionally have only capture permission. Cleanup is
      // same-origin management, matching the web app's normal delete request.
      headers: { Origin: base },
    });
    if (response.status() !== 204) throw new Error("Cleanup HTTP " + response.status());
    if (await findBookmark(request, base, url)) throw new Error("Cleanup did not remove test bookmark");
  }
}

function writeReport(out, name, report) {
  fs.mkdirSync(out, { recursive: true });
  report.completed_at = new Date().toISOString();
  report.passed = report.checks.every((item) => item.ok) && !report.error;
  fs.writeFileSync(path.join(out, name + ".json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 1));
  console.log(report.passed ? `ALL PASS (${report.checks.length})` : "FAILED");
  process.exitCode = report.passed ? 0 : 1;
}

module.exports = { ROOT, loadPlaywright, installable, findBookmark, cleanup, writeReport };
