#!/usr/bin/env node
/** Desktop Chromium with a Pixel 7 profile, not Android OS or a real device.
 * node scripts/verify-android.cjs [baseUrl] [evidenceDirectory]
 * Use an isolated service/database. Only unique test bookmarks are removed.
 */
const fs = require("fs");
const path = require("path");
const { randomUUID } = require("crypto");
const { ROOT, loadPlaywright, installable, findBookmark, cleanup, writeReport } = require("./browser-check.cjs");
const { chromium, devices } = loadPlaywright();
const BASE = (process.argv[2] || process.env.CS_BASE_URL || process.env.CS_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const OUT = path.resolve(process.argv[3] || path.join(ROOT, "docs", "m10-evidence"));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const report = { scope: "desktop-chromium-pixel7-emulation", real_android: false,
    os_share_panel: "not-tested", os_install: "not-tested", checks: [] };
  const check = (name, ok, detail) => report.checks.push({ name, ok: !!ok, detail });
  let browser, context;
  const testUrl = `https://example.com/cs-mobile-${randomUUID()}`;
  const title = "移动分享验收";
  const errors = [];
  try {
    browser = await chromium.launch();
    report.browser_version = browser.version();
    context = await browser.newContext({ ...devices["Pixel 7"] });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    const href = await page.getAttribute('link[rel="manifest"]', "href");
    const response = await context.request.get(new URL(href, BASE).toString());
    const manifest = await response.json();
    const share = manifest.share_target || {};
    check("share_target declaration", response.ok() && share.action === "/bookmarks" && share.method === "GET", share.action);
    check("share parameter mapping", ["title", "text", "url"].every((key) => share.params?.[key] === key), share.params);
    check("unique URL absent before test", !(await findBookmark(context.request, BASE, testUrl)), "fresh UUID URL");
    for (const [name, values] of [
      ["url and title", { url: testUrl, title }],
      ["text-only URL", { text: testUrl, title }],
      ["URL in shared prose", { text: `参考文档：${testUrl}。`, title }],
    ]) {
      await page.goto(BASE + "/bookmarks?" + new URLSearchParams(values), { waitUntil: "networkidle" });
      check(name + " prefill", await page.inputValue('input[aria-label="新书签网址"]') === testUrl, name);
      check(name + " title", await page.inputValue('input[aria-label="新书签标题"]') === title, name);
      check(name + " URL parameters cleared", !/[?&](url|text|title)=/.test(page.url()), page.url());
    }
    const savedResponse = page.waitForResponse((r) => r.url() === BASE + "/api/bookmarks" && r.request().method() === "POST");
    await page.tap('.bm-add button[type="submit"]');
    const saved = await savedResponse;
    check("touch creates a new bookmark", saved.status() === 201, "HTTP " + saved.status());
    const item = await findBookmark(context.request, BASE, testUrl);
    check("exact URL and title persisted", item?.url === testUrl && item?.title === title, "exact match");
    await page.screenshot({ path: path.join(OUT, "android-emulation.png") });
    await page.goto(BASE + "/bookmarks?url=" + encodeURIComponent("javascript:alert(1)"), { waitUntil: "networkidle" });
    check("unsafe shared URL rejected", (await page.inputValue('input[aria-label="新书签网址"]')) === "", "javascript URL not prefilled");
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    const cdp = await context.newCDPSession(page);
    const parsed = await cdp.send("Page.getAppManifest");
    const installation = await cdp.send("Page.getInstallabilityErrors");
    report.installability = installation;
    report.manifest_errors = parsed.errors;
    check("manifest and CDP installability", installable(parsed, installation), "browser-level check only");
    check("no runtime errors", errors.length === 0, errors);
  } catch (error) {
    report.error = String(error).split("\n")[0];
  } finally {
    if (context) {
      try { await cleanup(context.request, BASE, [testUrl]); check("test bookmark cleaned", true, "exact UUID URL removed"); }
      catch (error) { check("test bookmark cleaned", false, String(error)); }
    }
    if (browser) await browser.close();
    writeReport(OUT, "android-emulation", report);
  }
})();
