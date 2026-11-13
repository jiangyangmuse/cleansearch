const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");
const base = "http://127.0.0.1:18179";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const aiCalls = [];
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (request.url() === base + "/api/ai-search") aiCalls.push(request.postDataJSON().q);
  });
  const main = () => page.waitForResponse(response => response.url() === base + "/api/search");
  const ai = () => page.waitForResponse(response => response.url() === base + "/api/ai-search");
  async function submit(q, useAI = false) {
    const responses = [main()];
    if (useAI) responses.push(ai());
    await page.getByRole("searchbox", { name: "搜索查询" }).fill(q);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    return Promise.all(responses.map(async request => {
      const response = await request;
      assert.equal(response.status(), 200);
      return response.json();
    }));
  }

  try {
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    await page.goto(base);
    const toggle = page.getByRole("switch", { name: "日常 AI 检索" });
    assert.equal(await toggle.getAttribute("aria-checked"), "false");
    await submit("nexon");
    await page.locator('.official a[href="https://www.nexon.com/main/en"]').waitFor();
    assert.equal(aiCalls.length, 0);

    const [ordinary, deepseek] = await submit("明日方舟 ds", true);
    assert.equal(ordinary.parsed.q, "明日方舟");
    assert.equal(deepseek.provider, "DeepSeek");
    assert.equal(deepseek.cached, true);
    await page.locator('.official a[href="https://ak.hypergryph.com/"]').waitFor();
    const panel = page.getByRole("region", { name: "AI 检索" });
    await panel.getByRole("heading", { name: /^百科/ }).waitFor();
    await panel.getByRole("heading", { name: /^应用下载/ }).waitFor();
    const left = await page.locator(".layout__results").boundingBox();
    const right = await panel.boundingBox();
    assert.ok(right.x >= left.x + left.width);
    await page.screenshot({ path: path.join(__dirname, "desktop.png") });

    await toggle.click();
    const [, automatic] = await submit("明日方舟", true);
    assert.equal(automatic.cached, true);
    const reload = [main(), ai()];
    await page.reload();
    await Promise.all(reload);
    assert.equal(await toggle.getAttribute("aria-checked"), "true");
    await panel.getByRole("heading", { name: /^百科/ }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await panel.scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(__dirname, "mobile.png") });
    await toggle.click();
    await panel.waitFor({ state: "detached" });
    await submit("nexon");
    assert.equal(aiCalls.length, 3);

    // 视频未必出现在每次线上响应里，向结果页回放三个确定的类别。
    const sample = deepseek.results[0];
    const categories = [
      ["encyclopedia", "验收百科", "https://zh.wikipedia.org/wiki/Arknights"],
      ["download", "验收下载", "https://apps.apple.com/cn/app/arknights/id1454663939"],
      ["video", "验收视频", "https://www.bilibili.com/video/BV123"],
    ];
    await page.route(base + "/api/search", route => route.fulfill({
      json: {
        ...ordinary,
        official: null,
        groups: { strong: categories.map(([category, title, url], i) => ({
          ...sample, id: `r_${i + 1}`, category, title, url, display_url: url,
        })), related: [], weak: [] },
        meta: { ...ordinary.meta, total: 3, upstream_total: 3, official: 0, directory: 0 },
      },
    }));
    await submit("分类验收");
    for (const [name, title] of [["百科", "验收百科"], ["应用下载", "验收下载"], ["视频", "验收视频"]]) {
      await page.getByRole("region", { name, exact: true }).getByRole("link", { name: title }).waitFor();
      assert.equal(await page.getByRole("link", { name: title, exact: true }).count(), 1);
    }
    await toggle.click();
    const paged = main();
    await page.getByRole("button", { name: "下一页", exact: true }).click();
    await paged;
    const previous = main();
    await page.getByRole("button", { name: "上一页", exact: true }).click();
    await previous;
    assert.equal(aiCalls.length, 3);
    assert.deepEqual(errors, []);
    const result = { browser: browser.version(), aiCalls, aiCache: true, realOfficial: ["明日方舟", "nexon"],
      desktopSidebar: true, mobileNoOverflow: true, controlledCategories: 3, pageErrors: errors };
    fs.writeFileSync(path.join(__dirname, "browser.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
