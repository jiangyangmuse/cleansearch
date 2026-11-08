const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const webRequire = createRequire(path.resolve("apps/web/package.json"));
const { chromium } = webRequire("playwright");

(async () => {
  const base = process.argv[2] || "http://127.0.0.1:18172";
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const requests = [];
  let catalogReads = 0;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const catalog = await (await page.request.get(`${base}/api/engines`)).json();
  await page.route("**/api/engines", async (route) => {
    catalogReads += 1;
    const payload = structuredClone(catalog);
    payload.provider = "searxng";
    const google = payload.engines.find((item) => item.code === "g");
    Object.assign(google, { status: "cooldown", available: false, remaining_seconds: 60,
      last_error: "受控测试：主源拒绝", can_fallback: requests.length === 0, selectable: requests.length === 0 });
    await route.fulfill({ json: payload });
  });
  await page.route("**/api/search", async (route) => {
    const raw = route.request().postDataJSON();
    const response = await route.fetch();
    const body = await response.json();
    requests.push({ q: raw.q, parsed: body.parsed });
    await route.fulfill({ response, json: body });
  });
  try {
    await page.goto(base);
    const google = page.getByRole("button", { name: "Google g", exact: true });
    await google.waitFor();
    await page.locator('input[name="q"]').fill("python !b");
    assert.equal(await google.isEnabled(), true);
    assert.match(await google.getAttribute("title"), /可尝试回退/);
    await google.click();
    await page.waitForFunction(() => document.querySelector('button[title*="当前来源及回退来源均在冷却期"]')?.disabled);
    assert.equal(requests[0].q, "python !g");
    assert.equal(requests[0].parsed.q, "python");
    assert.equal(requests[0].parsed.engine, "google");
    const bing = page.getByRole("button", { name: "Bing b", exact: true });
    await bing.click();
    await page.waitForFunction(() => document.querySelector('input[name="q"]')?.value === "python !b");
    await page.waitForFunction(() => !document.querySelector('button[type="submit"]')?.disabled);
    await page.locator('input[name="q"]').fill("C g");
    await bing.click();
    await page.waitForFunction(() => !document.querySelector('button[type="submit"]')?.disabled);
    assert.equal(requests.at(-1).q, "C g !b");
    assert.equal(requests.at(-1).parsed.q, "C g");
    await page.locator('input[name="q"]').fill('"python');
    assert.equal(await bing.isDisabled(), true);
    await page.locator('input[name="q"]').fill("python !b");
    await page.screenshot({ path: path.join(__dirname, "browser-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: /^更多/ }).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(__dirname, "browser-mobile.png"), fullPage: true });
    assert.deepEqual(errors, []);
    const evidence = { passed: true, mode: "Playwright Chromium；目录受控，搜索由真实 fixture API 解析",
      catalogReads, requests, errors, desktop: "1280x900", mobile: "390x844", nativeAndroid: false };
    fs.writeFileSync(path.join(__dirname, "browser.json"), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
