const assert = require("node:assert/strict");
const { writeFileSync } = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");

const base = "http://127.0.0.1:18183";
const example = [
  { label: "不可用测试模型", base_url: "http://127.0.0.1:11434/v1",
    model: "cleans-search-test-missing-model", features: ["translate"] },
  { label: "本地千问", base_url: "http://127.0.0.1:11434/v1",
    model: "qwen3.5-4b-local:latest", features: ["search", "summary"] },
];

async function submitSearch(page, text) {
  const box = page.getByRole("searchbox", { name: "搜索查询" });
  const result = page.waitForResponse(response => response.url() === base + "/api/search");
  await box.fill(text);
  await page.getByRole("search").getByRole("button", { name: "搜索", exact: true }).click();
  assert.equal((await result).status(), 200);
}

(async () => {
  const browser = await chromium.launch();
  const checks = {};
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, colorScheme: "light" });
    page.setDefaultTimeout(60000);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const status = await (await page.request.get(base + "/api/health")).json();
    assert.equal(status.provider, "fixture");
    const registry = base + "/api/settings/models";
    const start = await (await page.request.get(registry)).json();
    assert((await page.request.put(registry, {
      data: { revision: start.revision, models: [], assignments: {} },
    })).ok());
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    await page.goto(base);
    const header = page.getByRole("navigation", { name: "全站导航" });
    assert.equal(await header.getByRole("link", { name: "单页总结" }).getAttribute("href"), "/s");
    assert.equal(await header.getByRole("link", { name: "一键添加" }).getAttribute("href"), "/tools");
    await submitSearch(page, "python 文档");
    await page.reload();
    await page.locator(".workspace-more > summary").click();
    await page.getByRole("button", { name: "搜索历史" }).click();
    const history = page.locator("#workspace-history");
    const repeated = page.waitForResponse(response => response.url() === base + "/api/search");
    await history.getByRole("link", { name: "python 文档" }).click();
    assert.equal((await repeated).status(), 200);
    checks.history = true;

    await header.getByRole("link", { name: "设置" }).click();
    await page.locator(".model-settings > summary").click();
    await page.getByText("批量导入 JSON", { exact: true }).click();
    await page.getByRole("textbox", { name: "模型 JSON" }).fill(JSON.stringify(example));
    await page.getByRole("button", { name: "导入模型" }).click();
    const models = page.locator(".model-entry__fields");
    assert.equal(await models.count(), 2);
    await page.getByRole("combobox", { name: "翻译 默认模型" }).selectOption({ label: example[0].label });
    await page.getByRole("combobox", { name: "翻译 备选模型" }).selectOption({ label: "本地千问（未开启）" });
    await page.getByRole("combobox", { name: "AI 检索 默认模型" }).selectOption({ label: "本地千问" });
    await page.getByRole("combobox", { name: "AI 总结 默认模型" }).selectOption({ label: "本地千问" });
    await page.getByRole("button", { name: "保存模型配置" }).click();
    await page.getByText("模型配置已保存").waitFor();
    await page.reload();
    await page.locator(".model-settings > summary").click();
    const savedBackup = page.getByRole("combobox", { name: "翻译 备选模型" });
    await savedBackup.waitFor();
    assert.match(await savedBackup.locator("option:checked").textContent(), /本地千问/);
    assert.equal(await models.count(), 2);
    await page.screenshot({ path: path.join(__dirname, "models.png") });
    checks.registry = "batch import, persisted routing";

    await page.getByRole("link", { name: "返回搜索" }).click();
    const rail = page.getByRole("complementary", { name: "搜索辅助" });
    const translate = rail.getByRole("region", { name: "翻译", exact: true });
    async function startTranslation() {
      await rail.locator(".workspace-tools__toggles").getByRole("button", { name: "翻译", exact: true }).click();
      await translate.getByRole("textbox", { name: "原文" }).fill("Python documentation");
      const result = page.waitForResponse(response => response.url() === base + "/api/translate");
      await translate.getByRole("button", { name: "翻译", exact: true }).click();
      return result;
    }
    const denied = await startTranslation();
    assert.equal(denied.status(), 503);
    assert.equal((await denied.json()).error.code, "MODEL_FALLBACK_DISABLED");
    await translate.getByText("当前模型不可用，备选模型未开启此功能", { exact: true }).waitFor();
    await header.getByRole("link", { name: "设置" }).click();
    await page.locator(".model-settings > summary").click();
    await page.locator("fieldset.model-entry").nth(1).getByRole("checkbox", { name: "翻译", exact: true }).check();
    await page.getByRole("button", { name: "保存模型配置" }).click();
    await page.getByText("模型配置已保存").waitFor();
    await page.getByRole("link", { name: "返回搜索" }).click();
    const translated = await startTranslation();
    assert.equal(translated.status(), 200);
    const translation = await translated.json();
    assert.equal(translation.model, "本地千问");
    assert.match(translation.text, /文档|文件|文献/);
    const searched = page.waitForResponse(response => response.url() === base + "/api/search");
    await translate.getByRole("button", { name: "搜索", exact: true }).click();
    assert.equal((await searched).status(), 200);
    assert.equal(await page.getByRole("searchbox", { name: "搜索查询" }).inputValue(), translation.text);
    await page.screenshot({ path: path.join(__dirname, "translate.png") });
    checks.translation = { denied: "MODEL_FALLBACK_DISABLED", selected: translation.model, search: true };

    const aiRequest = page.waitForResponse(response => response.url() === base + "/api/ai-search", { timeout: 75000 });
    await submitSearch(page, "python 文档 ds");
    const aiResponse = await aiRequest;
    assert.equal(aiResponse.status(), 200);
    const ai = await aiResponse.json();
    assert.equal(ai.provider, "本地千问");
    assert(ai.results.length > 0);
    await rail.getByRole("region", { name: "AI 检索", exact: true }).waitFor();
    checks.ai = { selected: ai.provider, results: ai.results.length };

    const urls = ["https://www.python.org/about/", "https://docs.python.org/3/tutorial/index.html"];
    await rail.locator(".workspace-tools__toggles").getByRole("button", { name: "AI 总结", exact: true }).click();
    const summary = rail.getByRole("region", { name: "网页总结" });
    await summary.getByRole("textbox", { name: "网页链接" }).fill(urls.join("\n"));
    const batchRequest = page.waitForResponse(response => response.url() === base + "/api/pages/summarize", {
      timeout: Number(process.env.CS_BROWSER_BATCH_TIMEOUT_MS || 95000),
    });
    await summary.getByRole("button", { name: "抓取并总结" }).click();
    const batchResponse = await batchRequest;
    assert.equal(batchResponse.status(), 200);
    const batch = await batchResponse.json();
    assert.deepEqual(batch.pages.map(page => page.url), urls);
    const sources = batch.pages.filter(page => !page.error).length;
    if (sources > 0) {
      assert.equal(batch.model, "本地千问");
      await summary.getByText(batch.summary, { exact: true }).waitFor();
    } else {
      await summary.getByText("没有成功获取正文的网页。", { exact: true }).waitFor();
    }
    checks.batch = { requested: batch.pages.length, sources, errors: batch.pages.map(page => page.error || null) };
    await page.screenshot({ path: path.join(__dirname, "summary.png") });

    const narrow = await browser.newPage({ viewport: { width: 320, height: 850 } });
    await narrow.goto(base);
    await narrow.locator(".workspace-more > summary").click();
    assert(await narrow.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await narrow.getByRole("button", { name: "搜索历史" }).click();
    await narrow.getByText("暂无搜索历史。", { exact: true }).waitFor();
    checks.mobile = true;
    assert.deepEqual(errors, []);
    writeFileSync(path.join(__dirname, "browser.json"), JSON.stringify(checks, null, 2));
    console.log(JSON.stringify(checks, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
