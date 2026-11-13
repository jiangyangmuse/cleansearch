const assert = require("node:assert/strict");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");

const base = "http://127.0.0.1:18183";
const phrase = "Nintendo ds";

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const aiRequests = [];
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.addInitScript(() => {
      if (!localStorage.getItem("cs-search-history")) {
        localStorage.setItem("cs-search-history", JSON.stringify(["旧版搜索记录"]));
      }
    });
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    await page.route("**/api/translate", route => route.fulfill({ json: { text: phrase, model: "fixture" } }));
    await page.route("**/api/ai-search", route => {
      aiRequests.push(route.request().postDataJSON());
      return route.fulfill({ json: { provider: "fixture", results: [], cached: false } });
    });
    await page.goto(base);

    async function verifyLiteral(action) {
      const expected = page.waitForResponse(response => response.url() === base + "/api/search");
      await action();
      const response = await expected;
      assert.equal(response.status(), 200);
      assert.equal(response.request().postDataJSON().opts.literal, true);
      assert.equal((await response.json()).parsed.q, phrase);
      assert.equal(new URL(page.url()).searchParams.get("literal"), "1");
      assert.equal(aiRequests.length, 0);
    }

    const rail = page.getByRole("complementary", { name: "搜索辅助" });
    await rail.locator(".workspace-tools__toggles").getByRole("button", { name: "翻译" }).click();
    const translate = rail.getByRole("region", { name: "翻译", exact: true });
    await translate.getByRole("textbox", { name: "原文" }).fill("任意示例原文");
    await translate.getByRole("button", { name: "翻译", exact: true }).click();
    await verifyLiteral(() => translate.getByRole("button", { name: "搜索", exact: true }).click());
    await verifyLiteral(() => page.reload());
    await page.locator(".workspace-more > summary").click();
    await page.getByRole("button", { name: "搜索历史" }).click();
    await page.getByRole("link", { name: "旧版搜索记录" }).waitFor();
    await verifyLiteral(() => page.getByRole("link", { name: phrase, exact: true }).click());

    const input = page.getByRole("searchbox", { name: "搜索查询" });
    await input.clear();
    await input.fill(phrase);
    const manualAI = page.waitForResponse(response => response.url() === base + "/api/ai-search");
    const manualSearch = page.waitForResponse(response => response.url() === base + "/api/search");
    await page.getByRole("search").getByRole("button", { name: "搜索", exact: true }).click();
    assert.equal((await manualAI).status(), 200);
    assert.equal((await (await manualSearch).json()).parsed.q, "Nintendo");
    assert.equal(aiRequests.length, 1);
    assert.equal(new URL(page.url()).searchParams.has("literal"), false);
    assert.deepEqual(errors, []);
    console.log("PASS: translation preserves ds on submit, reload and history; legacy history and explicit ds still work");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
