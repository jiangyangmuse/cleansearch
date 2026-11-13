const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");

const base = "http://127.0.0.1:18187";
const reply = {
  model: "测试模型",
  groups: [
    { label: "官方教程", query: "Python 官方教程", error: null, results: [{
      id: "conversation_1_1", url: "https://docs.python.org/3/tutorial/", display_url: "docs.python.org",
      title: "Python Tutorial", snippet: "Official documentation", engine: ["fixture"], risk: 0, reasons: [],
    }] },
    { label: "中文视频", query: "Python 中文入门视频", error: null, results: [] },
  ],
};

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const requests = [];
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    await page.route("**/api/conversation-search", route => {
      requests.push(route.request().postDataJSON());
      return route.fulfill({ json: reply });
    });
    const daily = [];
    await page.route("**/api/ai-search", route => {
      daily.push(route.request().postDataJSON().q);
      return route.fulfill({ json: { provider: "测试 AI 检索", results: [], cached: false } });
    });
    await page.goto(base);
    const nav = page.getByRole("navigation", { name: "搜索分类" });
    const rail = page.getByRole("complementary", { name: "搜索辅助" });
    const chat = nav.getByRole("button", { name: "AI", exact: true });
    const chatButton = rail.getByRole("button", { name: "AI 对话搜索", exact: true });
    const buttons = await rail.locator(".workspace-tools__toggles button").allTextContents();
    assert.match(buttons.at(-2), /翻译/);
    assert.match(buttons.at(-1), /AI 对话/);
    await chatButton.click();
    const quick = rail.getByRole("region", { name: "AI 对话搜索入口" });
    await quick.getByRole("textbox").fill("想自学 Python，找教程和视频");
    await quick.getByRole("button", { name: "对话搜索" }).click();
    const main = page.getByRole("main");
    await main.getByRole("link", { name: "Python Tutorial" }).waitFor();
    assert.equal(await chat.getAttribute("aria-current"), "page");
    assert.equal(new URL(page.url()).searchParams.get("category"), "conversation");
    assert.equal(await main.getByRole("heading", { name: "官方教程" }).count(), 1);
    assert.equal(await main.getByRole("heading", { name: "中文视频" }).count(), 1);
    await main.getByRole("textbox", { name: "搜索需求" }).fill("视频只要中文");
    await main.getByRole("button", { name: "对话搜索" }).click();
    await main.getByRole("region", { name: "第 2 轮搜索" }).getByRole("link", { name: "Python Tutorial" }).waitFor();
    assert.deepEqual(requests[1].history, [{ message: requests[0].message, directions: ["官方教程", "中文视频"] }]);
    await page.screenshot({ path: path.join(__dirname, "conversation.png") });
    await nav.getByRole("button", { name: "首页" }).click();
    const form = page.getByRole("search");
    const query = form.getByRole("searchbox");
    for (const text of ["python ds", "python 文档"]) {
      if (!text.endsWith(" ds")) await page.getByRole("switch", { name: "日常 AI 检索" }).check();
      await query.fill(text);
      const searched = page.waitForResponse(response => response.url() === base + "/api/search");
      await form.getByRole("button", { name: "搜索", exact: true }).click();
      assert.equal((await searched).status(), 200);
      await rail.getByRole("region", { name: "AI 检索", exact: true }).getByText("测试 AI 检索").waitFor();
      assert.equal(await nav.getByRole("button", { name: "首页" }).getAttribute("aria-current"), "page");
    }
    assert.deepEqual(daily, ["python ds", "python 文档"]);
    await chat.click();
    await main.getByRole("region", { name: "第 2 轮搜索" }).waitFor();
    assert.equal(await rail.getByRole("region", { name: "AI 检索", exact: true }).count(), 0);
    await main.getByRole("button", { name: "新对话" }).click();
    assert.equal(await main.getByRole("region", { name: "第 1 轮搜索" }).count(), 0);
    await page.reload();
    await main.getByRole("heading", { name: "AI 对话搜索" }).waitFor();
    assert.equal(daily.length, 2);
    await page.setViewportSize({ width: 320, height: 850 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log("PASS: sidebar placement, auto-switch, two groups, follow-up, daily AI and ds isolation, retained turns, reset, 320px");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
