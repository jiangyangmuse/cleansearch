const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { chromium } = createRequire(path.resolve("apps/web/package.json"))("playwright");

const base = "http://127.0.0.1:18185";

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1060 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/favicon**", route => route.fulfill({ status: 404 }));
    const settingsPath = base + "/api/settings/engines";
    const state = await (await page.request.get(settingsPath)).json();
    assert((await page.request.put(settingsPath, {
      data: { revision: state.preferences.revision, default_engines: null, custom: [] },
    })).ok());

    await page.goto(base + "/settings#engine-settings");
    const panel = page.getByRole("region", { name: "搜索引擎" });
    const mode = panel.getByRole("switch", { name: "使用自选默认引擎" });
    await mode.check();
    const bing = panel.getByRole("switch", { name: "默认搜索使用 Bing", exact: true });
    for (const item of await panel.getByRole("switch", { name: /默认搜索使用/ }).all()) {
      if (await item.getAttribute("aria-label") !== "默认搜索使用 Bing" && await item.isChecked()) {
        await item.uncheck();
      }
    }
    assert.equal(await bing.isChecked(), true);
    assert.equal(await panel.getByRole("heading", { name: "中国大陆可直连" }).count(), 1);

    async function add(kind, name, code, targetLabel, target) {
      await panel.getByRole("button", { name: "添加搜索入口" }).click();
      await panel.getByLabel("入口名称").fill(name);
      await panel.getByLabel("搜索后缀").fill(code);
      await panel.getByLabel("入口类型").selectOption(kind);
      await panel.getByLabel(targetLabel).fill(target);
      await panel.getByRole("button", { name: "添加到列表" }).click();
    }
    await add("engine", "必应自定义", "bing2", "SearXNG 引擎名称", "bing");
    await add("region", "法语法国", "frfr", "语言或地区代码", "fr-FR");
    await add("website", "站内搜索示例", "portal", "搜索网址模板", "https://example.org/search?q={q}");
    assert.equal(await panel.getByRole("heading", { name: "自定义", exact: true }).count(), 1);
    assert.equal(await panel.getByRole("switch", { name: "默认搜索使用 必应自定义" }).isChecked(), true);
    await panel.getByRole("button", { name: "保存引擎设置" }).click();
    await panel.getByText("搜索引擎设置已保存").waitFor();
    await page.reload();
    await bing.waitFor();
    assert.equal(await bing.isChecked(), true);
    assert.equal(await panel.getByText("站内搜索示例", { exact: true }).count(), 1);
    await panel.screenshot({ path: path.join(__dirname, "settings.png") });

    await page.getByRole("link", { name: "返回搜索" }).click();
    const mainSearch = page.getByRole("search");
    const field = mainSearch.getByRole("searchbox", { name: "搜索查询" });
    async function submit(q) {
      const response = page.waitForResponse(res => res.url() === base + "/api/search");
      await field.fill(q);
      await mainSearch.getByRole("button", { name: "搜索", exact: true }).click();
      return response;
    }
    const ordinary = await (await submit("python 文档")).json();
    assert.deepEqual(ordinary.meta.engines, ["bing"]);
    const locale = await (await submit("python 文档 frfr")).json();
    assert.equal(locale.parsed.region, "fr-FR");
    assert.deepEqual(locale.meta.engines, ["bing"]);
    const explicit = await (await submit("python 文档 !bing2")).json();
    assert.equal(explicit.parsed.custom_code, "bing2");
    assert.deepEqual(explicit.meta.engines, ["bing"]);
    const external = await (await submit("机器 学习 portal")).json();
    const link = page.getByRole("link", { name: /在新标签页打开搜索/ });
    assert.equal(await link.getAttribute("href"), external.parsed.open_url);
    assert.equal(new URL(external.parsed.open_url).searchParams.get("q"), "机器 学习");
    assert.equal(await link.getAttribute("target"), "_blank");
    await page.locator(".workspace-engines > summary").click();
    await page.getByRole("button", { name: /站内搜索示例/ }).waitFor();
    const popup = page.locator(".workspace-engines .engines");
    assert.equal(await popup.getByText("中国大陆可直连", { exact: true }).count(), 1);
    assert.equal(await popup.getByText("自定义", { exact: true }).count(), 1);
    await page.screenshot({ path: path.join(__dirname, "search.png") });

    await page.getByRole("link", { name: "设置", exact: true }).click();
    await bing.uncheck();
    assert.equal(await panel.getByRole("switch", { name: "默认搜索使用 必应自定义" }).isChecked(), false);
    await panel.getByRole("button", { name: "保存引擎设置" }).click();
    await panel.getByText("搜索引擎设置已保存").waitFor();
    await page.getByRole("link", { name: "返回搜索" }).click();
    const paused = await submit("python 文档");
    assert.equal(paused.status(), 422);
    assert.equal((await paused.json()).error.code, "SEARCH_ENGINES_DISABLED");
    assert.equal((await submit("python 文档 !b")).status(), 200);

    const narrow = await browser.newPage({ viewport: { width: 390, height: 900 } });
    await narrow.goto(base + "/settings#engine-settings");
    await narrow.getByRole("heading", { name: "中国大陆可直连" }).waitFor();
    assert(await narrow.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    const evidence = { settingsPersisted: true, defaultSources: ordinary.meta.engines, locale: locale.parsed.region,
      customEngine: explicit.parsed.engine, website: external.parsed.open_url, paused: true, explicitWhilePaused: true,
      mainlandAndCustomGroups: true, narrowWidth: 390, browserErrors: errors };
    fs.writeFileSync(path.join(__dirname, "browser.json"), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
