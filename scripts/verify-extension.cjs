#!/usr/bin/env node
/** Unpacked extension test on Chromium / Edge / Chrome for Testing.
 * node scripts/verify-extension.cjs [baseUrl] [evidenceDirectory]
 * CS_CHROME_PATH / CS_BROWSER_CHANNEL selects the browser. Stable Chrome
 * manual loading and actual OS context-menu clicks are separate acceptance.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { randomUUID } = require("crypto");
const { ROOT, loadPlaywright, installable, findBookmark, cleanup, writeReport } = require("./browser-check.cjs");
const { chromium } = loadPlaywright();
const BASE = (process.argv[2] || process.env.CS_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const OUT = path.resolve(process.argv[3] || path.join(ROOT, "docs", "m9-evidence"));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "cs-ext-profile-"));
  const report = { scope: "unpacked-extension-automation", stable_chrome_manual: "not-tested",
    os_context_menu_click: "not-tested", headless: process.env.CS_HEADLESS === "true", checks: [] };
  const check = (name, ok, detail) => report.checks.push({ name, ok: !!ok, detail });
  const urls = ["popup", "background"].map((name) => `https://example.com/cs-${name}-${randomUUID()}`);
  let context, token;
  const errors = [];
  try {
    const executablePath = process.env.CS_CHROME_PATH || undefined;
    context = await chromium.launchPersistentContext(profile, {
      headless: process.env.CS_HEADLESS === "true",
      executablePath,
      channel: executablePath ? undefined : process.env.CS_BROWSER_CHANNEL || undefined,
      ignoreDefaultArgs: ["--disable-extensions"],
      viewport: { width: 1280, height: 900 },
      args: ["--disable-extensions-except=" + path.join(ROOT, "apps", "extension"),
        "--load-extension=" + path.join(ROOT, "apps", "extension"), "--no-first-run"],
    });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    report.browser = await cdp.send("Browser.getVersion");
    report.selected_browser = executablePath ? "explicit-executable" : process.env.CS_BROWSER_CHANNEL || "playwright-chromium";
    page.on("pageerror", (error) => errors.push(error.message));
    let worker = context.serviceWorkers().find((worker) => worker.url().startsWith("chrome-extension://"));
    if (!worker) worker = await context.waitForEvent("serviceworker", { predicate: (worker) => worker.url().startsWith("chrome-extension://"), timeout: 15000 });
    const id = new URL(worker.url()).host;
    check("extension service worker loaded", !!id, id);
    token = (await (await context.request.get(BASE + "/api/tools/bookmarklet")).json()).token;
    check("test URLs absent", !(await findBookmark(context.request, BASE, urls[0])) && !(await findBookmark(context.request, BASE, urls[1])), "fresh UUID URLs");
    await page.goto(`chrome-extension://${id}/options.html`);
    await page.fill("#api", BASE);
    await page.fill("#token", token);
    await page.getByRole("button", { name: "保存设置" }).click();
    await page.getByText("设置已保存", { exact: true }).waitFor();
    await page.fill("#token", "");
    await page.getByRole("button", { name: "测试连接" }).click();
    await page.getByText(/token 可用/).waitFor();
    check("options saved settings and verified stored token", true, "checked using an invalid bookmark URL, no write");
    await page.fill("#token", "deliberately-invalid");
    await page.getByRole("button", { name: "测试连接" }).click();
    await page.getByText("token 无效或没有添加权限").waitFor();
    check("options rejected invalid token", true, "server rejected authorization");
    await page.route(BASE + "/api/bookmarks", route => route.fulfill({ status: 500, json: { error: "test" } }));
    await page.fill("#token", "");
    await page.getByRole("button", { name: "测试连接" }).click();
    await page.getByText(/HTTP 500.*无法确认/).waitFor();
    await page.unroute(BASE + "/api/bookmarks");
    check("options did not treat HTTP 500 as valid token", true, "mocked upstream failure");
    const commands = await worker.evaluate(() => chrome.commands.getAll());
    check("Chrome registered save-page command", commands.some(command => command.name === "save-page"), "runtime command registration");
    await page.goto(`chrome-extension://${id}/popup.html`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#save");
    check("popup opened", true, "popup.html");
    await page.click("details summary");
    await page.fill("#api", BASE);
    await page.fill("#token", token);
    await page.click("#save-settings");
    await page.waitForFunction(() => /设置已保存/.test(document.querySelector("#status")?.textContent || ""));
    await page.fill("#url", urls[0]);
    await page.fill("#title", "扩展验收");
    await page.click("#save");
    await page.waitForFunction(() => /已收藏|失败/.test(document.querySelector("#status")?.textContent || ""));
    check("popup save succeeded", /已收藏/.test((await page.textContent("#status")) || ""), "status checked");
    const popupItem = await findBookmark(context.request, BASE, urls[0]);
    check("popup exact bookmark persisted", popupItem?.url === urls[0] && popupItem?.title === "扩展验收", "exact match");
    await page.fill("#token", ""); // keep credentials out of screenshots, even if details styling changes
    await page.click("details summary");
    await page.screenshot({ path: path.join(OUT, "extension.png") });
    const background = await worker.evaluate(async (url) => self.cleansearchSave(url, "后台验收"), urls[1]);
    check("background save function succeeded", background?.ok === true, "shared save function, not OS menu click");
    const backgroundItem = await findBookmark(context.request, BASE, urls[1]);
    check("background exact bookmark persisted", backgroundItem?.url === urls[1] && backgroundItem?.title === "后台验收", "exact match");
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    const manifest = await cdp.send("Page.getAppManifest");
    const installation = await cdp.send("Page.getInstallabilityErrors");
    report.installability = installation;
    report.manifest_errors = manifest.errors;
    check("manifest and CDP installability", installable(manifest, installation), "nonempty errors fail");
    check("no runtime errors", errors.length === 0, errors);
  } catch (error) {
    report.error = String(error).split("\n")[0];
  } finally {
    if (context && token) {
      try { await cleanup(context.request, BASE, urls); check("test bookmarks cleaned", true, "exact UUID URLs removed"); }
      catch (error) { check("test bookmarks cleaned", false, String(error)); }
    }
    if (context) await context.close();
    // Only this unique temporary profile is removed, never a user browser profile.
    if (path.dirname(profile) === path.resolve(os.tmpdir()) && path.basename(profile).startsWith("cs-ext-profile-")) {
      fs.rmSync(profile, { recursive: true, force: true });
    }
    writeReport(OUT, "extension", report);
  }
})();
