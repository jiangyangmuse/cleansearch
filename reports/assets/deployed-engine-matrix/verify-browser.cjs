const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const webRequire = createRequire(path.resolve("apps/web/package.json"));
const { chromium } = webRequire("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    const result = page.waitForResponse((response) => response.url().endsWith("/api/search"), { timeout: 60000 });
    await page.goto("http://127.0.0.1:8000/?q=deepseek");
    const response = await result;
    assert.equal(response.status(), 200);
    const payload = await response.json();
    assert.equal(payload.meta.provider, "searxng");
    const items = Object.values(payload.groups).flat();
    const homes = items.filter((item) => {
      const url = new URL(item.url);
      return ["deepseek.com", "www.deepseek.com"].includes(url.hostname) && ["/", "/en/", "/zh/", "/zh-CN/"].includes(url.pathname);
    });
    const evidence = { query: "deepseek", browser: browser.version(), mocked: false,
      meta: Object.fromEntries(Object.entries(payload.meta).filter(([key]) => key !== "sid")),
      homepage_candidates: homes.map((item) => ({ url: item.url, engine: item.engine, title: item.title })),
      chat_candidates: items.filter((item) => new URL(item.url).hostname === "chat.deepseek.com").map((item) => item.url),
      homepage_visible_by_default: false, nativeAndroid: false };
    if (homes.length) {
      const home = page.locator(`a[href=${JSON.stringify(homes[0].url)}]`).first();
      await home.waitFor({ state: "attached" });
      evidence.homepage_visible_by_default = await home.isVisible();
      if (evidence.homepage_visible_by_default) await home.scrollIntoViewIfNeeded();
    }
    await page.screenshot({ path: path.join(__dirname, "live-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    evidence.mobile_horizontal_overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    await page.screenshot({ path: path.join(__dirname, "live-mobile.png") });
    evidence.page_errors = errors;
    fs.writeFileSync(path.join(__dirname, "browser.json"), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
    assert.ok(homes.length && evidence.homepage_visible_by_default, "真实候选或默认页面未显示品牌首页，详见证据");
    assert.equal(evidence.mobile_horizontal_overflow, false);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
