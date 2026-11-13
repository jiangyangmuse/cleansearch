const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");

const base = "http://127.0.0.1:18181";
const artifacts = __dirname;
const examples = [
  { id: "check_encyclopedia", title: "Python 百科示例", url: "https://zh.wikipedia.org/wiki/Python", category: "encyclopedia" },
  { id: "check_video", title: "Python 视频示例", url: "https://www.bilibili.com/video/BVtest", category: "video" },
  { id: "check_download", title: "Python 应用下载示例", url: "https://www.python.org/downloads/", category: "download" },
].map(item => ({
  display_url: new URL(item.url).hostname, engine: ["fixture"], risk: 0, score: 0.8,
  reasons: [], snippet: "用于验证搜索结果的分类显示。", ...item,
}));

async function submit(page, query) {
  const response = page.waitForResponse(res => res.url().endsWith("/api/search"));
  await page.getByRole("searchbox", { name: "搜索查询" }).fill(query);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  assert.equal((await response).status(), 200);
}

async function assertNoOverflow(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
}

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const checks = {};
  try {
    const desktop = await browser.newContext({ viewport: { width: 1440, height: 960 }, colorScheme: "light" });
    const downloads = await desktop.request.get(base + "/api/bookmarks?q=Python%20%E5%BA%94%E7%94%A8%E4%B8%8B%E8%BD%BD%E7%A4%BA%E4%BE%8B");
    assert(downloads.ok());
    for (const item of (await downloads.json()).items.filter(item => item.url === examples[2].url)) {
      assert((await desktop.request.delete(base + "/api/bookmarks/" + item.id)).ok());
    }
    for (const bookmark of [
      { title: "Python 官方网站", url: "https://www.python.org/" },
      { title: "MDN Web Docs", url: "https://developer.mozilla.org/zh-CN/" },
    ]) {
      const response = await desktop.request.post(base + "/api/bookmarks", { data: bookmark });
      assert(response.ok());
    }
    const page = await desktop.newPage();
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    await page.goto(base);
    const nav = page.getByRole("navigation", { name: "搜索分类" });
    const shortcuts = page.getByRole("region", { name: "书签快捷栏" });
    const toggle = shortcuts.getByRole("button", { name: "书签快捷栏" });
    await shortcuts.getByRole("link", { name: /MDN Web Docs/ }).waitFor();
    assert.equal(await toggle.getAttribute("aria-expanded"), "true");
    const left = await nav.boundingBox();
    const center = await page.getByRole("searchbox", { name: "搜索查询" }).boundingBox();
    const right = await shortcuts.boundingBox();
    assert(left.x + left.width < center.x && center.x + center.width < right.x);
    await assertNoOverflow(page);
    await page.screenshot({ path: path.join(artifacts, "desktop.png") });
    await toggle.click();
    assert.equal(await toggle.getAttribute("aria-expanded"), "false");
    assert.equal(await shortcuts.getByRole("link", { name: /MDN Web Docs/ }).isVisible(), false);
    await page.reload();
    assert.equal(await toggle.getAttribute("aria-expanded"), "false");
    await toggle.click();
    await shortcuts.getByRole("link", { name: /MDN Web Docs/ }).waitFor();
    checks.desktop = "left/center/right, bookmark collapse, saved state and re-open";

    const aiCalls = [];
    await page.route("**/api/ai-search", async route => {
      aiCalls.push(route.request().postDataJSON().q);
      await route.fulfill({ json: { provider: "DeepSeek", cached: false, results: [
        { ...examples[0], id: "ai_replay", title: "AI 检索示例" },
      ] } });
    });
    await page.route("**/api/search", async route => {
      const response = await route.fetch();
      const body = await response.json();
      if (response.ok() && body.meta.total > 0) {
        body.groups.strong.unshift(...examples);
        body.meta.total += examples.length;
      }
      await route.fulfill({ response, json: body });
    });
    const rail = page.getByRole("complementary", { name: "搜索辅助" });
    const aiToggle = rail.getByRole("button", { name: "AI 检索", exact: true });
    await aiToggle.click();
    await rail.getByText(/单次启用/).waitFor();
    assert.deepEqual(aiCalls, []);
    await aiToggle.click();
    await submit(page, "python 文档");
    await page.getByRole("link", { name: examples[0].title }).waitFor();
    assert.deepEqual(aiCalls, []);
    for (const [label, index] of [["百科", 0], ["视频", 1], ["下载", 2]]) {
      await nav.getByRole("button", { name: label, exact: true }).click();
      assert.equal(await nav.getByRole("button", { name: label, exact: true }).getAttribute("aria-current"), "page");
      await page.getByRole("link", { name: examples[index].title }).waitFor();
      for (const item of examples.filter(item => item !== examples[index])) {
        assert.equal(await page.getByRole("link", { name: item.title }).count(), 0);
      }
    }
    await page.reload();
    await page.getByRole("link", { name: examples[2].title }).waitFor();
    assert(new URL(page.url()).searchParams.get("category") === "download");
    await page.keyboard.press("j");
    assert.equal(await page.evaluate(() => document.activeElement.id), "result-check_download");
    const saved = page.waitForResponse(res => res.url().endsWith("/api/bookmarks") && res.request().method() === "POST");
    await page.locator("#result-check_download").getByRole("button", { name: "收藏", exact: true }).click();
    assert((await saved).ok());
    await shortcuts.getByRole("link", { name: /Python 应用下载示例/ }).waitFor();
    checks.categories = "three category views, reload, keyboard focus and save refresh";

    await nav.getByRole("button", { name: "首页" }).click();
    await submit(page, "python 文档 ds");
    await rail.getByRole("link", { name: "AI 检索示例" }).waitFor();
    assert.deepEqual(aiCalls, ["python 文档 ds"]);
    await page.screenshot({ path: path.join(artifacts, "results.png") });
    await aiToggle.click();
    assert.equal(await rail.getByRole("link", { name: "AI 检索示例" }).count(), 0);
    await aiToggle.click();
    await rail.getByRole("link", { name: "AI 检索示例" }).waitFor();
    assert.equal(aiCalls.length, 1);
    const summaryToggle = rail.getByRole("button", { name: "AI 总结", exact: true });
    await summaryToggle.click();
    const summary = rail.getByRole("region", { name: "AI 总结" });
    await summary.getByRole("button", { name: "生成总结" }).click();
    await summary.locator(".citation").first().waitFor();
    await nav.getByRole("button", { name: "视频" }).click();
    await summary.locator(".citation").first().click();
    assert.equal(await nav.getByRole("button", { name: "首页" }).getAttribute("aria-current"), "page");
    await page.locator(".card--flash").waitFor();
    checks.ai = "suffix, manual open does not bill, collapse preserves results, real fixture SSE citation";

    await page.getByRole("link", { name: "设置", exact: true }).click();
    assert.equal(new URL(page.url()).pathname, "/settings");
    await page.getByRole("heading", { name: "设置", exact: true }).waitFor();
    await page.getByRole("radio", { name: "深色" }).check();
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.getByRole("radio", { name: "浅色" }).check();
    const daily = page.getByRole("switch", { name: "日常 AI 检索" });
    await daily.check();
    await page.reload();
    assert.equal(await daily.isChecked(), true);
    await page.screenshot({ path: path.join(artifacts, "settings.png") });
    await page.getByRole("link", { name: "返回搜索" }).click();
    assert.equal(await page.getByRole("switch", { name: "日常 AI 检索" }).isChecked(), true);
    await submit(page, "python 文档");
    await rail.getByRole("link", { name: "AI 检索示例" }).waitFor();
    assert.deepEqual(aiCalls, ["python 文档 ds", "python 文档"]);
    await page.getByRole("navigation", { name: "全站导航" }).getByRole("link", { name: "书签" }).click();
    assert.equal(new URL(page.url()).pathname, "/bookmarks");
    assert.equal(await page.locator(".workspace").count(), 0);
    await page.getByText("Python 应用下载示例", { exact: true }).waitFor();
    checks.settings = "direct route, themes, persistent AI switch shared with search, bookmark route";

    for (const width of [320, 390, 920]) {
      const context = await browser.newContext({ viewport: { width, height: 850 }, colorScheme: "light" });
      const mobile = await context.newPage();
      mobile.on("pageerror", error => errors.push(error.message));
      await mobile.goto(base);
      await assertNoOverflow(mobile);
      const bookmarkToggle = mobile.getByRole("button", { name: "书签快捷栏" });
      if (width <= 390) assert.equal(await bookmarkToggle.getAttribute("aria-expanded"), "false");
      await mobile.getByRole("button", { name: "AI 检索", exact: true }).click();
      await mobile.getByText(/单次启用/).waitFor();
      await assertNoOverflow(mobile);
      if (width === 390) await mobile.screenshot({ path: path.join(artifacts, "mobile.png") });
      await context.close();
    }
    checks.responsive = "320, 390 and 920px with no horizontal overflow";
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(artifacts, "browser.json"), JSON.stringify({ checks, errors }, null, 2));
    console.log(JSON.stringify(checks, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
