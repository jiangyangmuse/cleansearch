// 浏览器验收脚本：P0 语义/抽屉/分组/触控/标题层级 + P1 统计条折叠与加载骨架。
// 用法：node scripts/audit-ui.cjs [--base http://127.0.0.1:8000] [--out reports/assets/ui-audit] [--channel chrome]
// --test-bookmark-writes 仅用于隔离数据库，执行真实收藏、删除和 HTML 导入。
const fs = require("fs");
const path = require("path");
const http = require("node:http");
const https = require("node:https");
const { randomUUID } = require("node:crypto");
const { ROOT, cleanup, loadPlaywright, writeReport } = require("./browser-check.cjs");

function loadAxe() {
  return require(require.resolve("@axe-core/playwright", {
    paths: [path.join(ROOT, "apps", "web"), ROOT],
  })).AxeBuilder;
}

async function axeScan(page, label) {
  const AxeBuilder = loadAxe();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = result.violations.filter(item => item.impact === "serious" || item.impact === "critical");
  check(`axe serious/critical 为 0（${label}）`, serious.length === 0,
    serious.map(item => `${item.id}×${item.nodes.length}`).join(" · ") || `violations=${result.violations.length}`);
}

const argv = process.argv.slice(2);
function arg(name, fallback) {
  const index = argv.indexOf("--" + name);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
}

const BASE = arg("base", process.env.AUDIT_BASE || "http://127.0.0.1:8000").replace(/\/+$/, "");
const OUT = path.resolve(ROOT, arg("out", "reports/assets/ui-audit"));
const CHANNEL = arg("channel", undefined);
const TEST_BOOKMARK_WRITES = argv.includes("--test-bookmark-writes");
const QUERIES = ["python", "linux 内核", "rust", "中文分词"];

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: !!ok, detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " · " + detail : ""}`);
}

const READY = ".workspace-results .results-body:not([inert]):not([aria-busy]) .pager, " +
  ".workspace-results > .pager, .workspace-results > .state--empty, .workspace-results > .state--error";

async function compactStats(page) {
  return page.locator(".metabar").evaluate(bar => {
    const metrics = bar.querySelector(".metabar__summary");
    const items = Array.from(metrics.children, item => item.getBoundingClientRect());
    const toggle = bar.querySelector("summary").getBoundingClientRect();
    return {
      height: bar.getBoundingClientRect().height,
      singleLine: items.every(item => Math.abs((item.top + item.bottom) / 2 - (items[0].top + items[0].bottom) / 2) <= 1),
      fits: items.every(item => item.right <= toggle.left),
      toggleHeight: toggle.height,
    };
  });
}

async function runSearch(page, query) {
  await page.fill('input[name="q"]', "");
  await page.fill('input[name="q"]', query);
  await page.press('input[name="q"]', "Enter");
  await page.waitForSelector(READY, { timeout: 60000 });
  return page.evaluate(() => {
    const meta = document.querySelector(".metabar")?.innerText ?? "";
    const match = /展示\s*(\d+)\s*条/.exec(meta);
    return { total: match ? Number(match[1]) : 0, empty: !!document.querySelector(".state--empty") };
  });
}

/** 确定性搜索响应：交互类断言不依赖真实上游条数（方案 §4.7）。 */
function makeSearchFixture(query) {
  const results = Array.from({ length: 10 }, (_, index) => ({
    id: `fx${index + 1}`,
    url: `https://example${index + 1}.test/page`,
    display_url: `example${index + 1}.test › page`,
    title: `固定样本结果 ${index + 1}：${query}`,
    snippet: `第 ${index + 1} 条固定样本摘要，用于把筛选交互与真实上游解耦。`,
    engine: ["fixture"],
    score: Number((0.9 - index * 0.05).toFixed(3)),
    risk: 0,
    reasons: [],
    favicon: null,
    published: null,
    read_minutes: null,
  }));
  return {
    parsed: { q: query, engine: "default", region: null, router: "default", expanded: [] },
    groups: { strong: results.slice(0, 6), related: results.slice(6, 9), weak: results.slice(9) },
    official: null,
    meta: {
      status: "ok", engines: ["fixture"], unresponsive: [], provider: "fixture", cached: false,
      ms: 12, total: results.length, upstream_total: results.length,
      filtered: { dup: 0, risk: 0 }, official: 0, directory: 0, sid: "fixture-sid",
    },
  };
}

async function searchWithResults(page) {
  let last = 0;
  for (const query of QUERIES) {
    const result = await runSearch(page, query);
    last = result.total;
    if (result.total > 0) return { query, total: result.total };
  }
  throw new Error("fixture 查询未返回结果，最后一条 total=" + last + "；请核对 fixture 配置和默认引擎设置。");
}

async function boxTop(page, selector) {
  const box = await page.locator(selector).first().boundingBox();
  return box ? box.y : null;
}

async function mockSummary(page, resultId) {
  let requests = 0;
  await page.route("**/api/summarize?*", route => {
    requests++;
    const events = [
      ["meta", { model: "audit-stub" }],
      ["cite", { i: 1, result_id: resultId, title: "固定引用" }],
      ["token", { t: "固定总结 [1]" }],
      ["done", { partial: false, ms: 1 }],
    ];
    return route.fulfill({ contentType: "text/event-stream",
      body: events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("") });
  });
  return () => requests;
}

async function auditPwa(browser) {
  const builtWorker = await fetch(BASE + "/sw.js").then(response => response.text());
  const originalVersion = builtWorker.match(/cs-shell-\$\{"([a-f0-9]{20})"\}/)?.[1];
  if (!originalVersion) throw new Error("生产 Service Worker 缺少构建版本");
  let version = originalVersion;
  let breakPrecache = false;
  const shareFollowups = [];
  const server = http.createServer((request, response) => {
    if (request.url === "/sw.js") {
      response.writeHead(200, { "Content-Type": "text/javascript", "Cache-Control": "no-store" });
      response.end(builtWorker.replace(originalVersion, version));
      return;
    }
    if (breakPrecache && request.url.startsWith("/assets/")) {
      response.writeHead(503).end();
      return;
    }
    if (request.method === "GET" && request.url.startsWith("/bookmarks")) shareFollowups.push(request.url);
    const upstream = new URL(request.url, BASE);
    const transport = upstream.protocol === "https:" ? https : http;
    const forwarded = transport.request(upstream, { method: request.method, headers: request.headers }, result => {
      response.writeHead(result.statusCode, result.headers);
      result.pipe(response);
    });
    forwarded.on("error", () => response.writeHead(502).end());
    request.pipe(forwarded);
  });
  await new Promise((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  try {
    const page = await context.newPage();
    await page.goto(origin + "/");
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    const files = await page.evaluate(async () => (await (await caches.open((await caches.keys()).find(key => key.startsWith("cs-shell-")))).keys())
      .map(request => new URL(request.url).pathname));
    check("首次激活已缓存 HTML、入口脚本、样式和离线页", ["/index.html", "/offline.html"].every(path => files.includes(path)) &&
      files.some(path => /^\/assets\/.*\.js$/.test(path)) && files.some(path => /^\/assets\/.*\.css$/.test(path)), `${files.length} 个文件`);

    const metadata = await page.evaluate(async () => {
      const manifest = await (await fetch("/manifest.webmanifest")).json();
      const link = document.querySelector('link[rel="search"]');
      const description = await fetch(link.href);
      const xml = new DOMParser().parseFromString(await description.text(), "text/xml");
      return { manifest, template: xml.querySelector("Url")?.getAttribute("template"), type: description.headers.get("content-type") };
    });
    const manifest = metadata.manifest;
    check("manifest 保留应用 ID、显示模式、分类与快捷方式", manifest.id === "/" && manifest.display_override.length > 0 &&
      manifest.categories.length > 0 && manifest.shortcuts.length >= 4, "");
    check("manifest 提供 maskable 图标与 POST 分享", manifest.icons.some(icon => icon.purpose === "maskable") &&
      manifest.share_target.method === "POST" && manifest.share_target.action === "/share", "");
    check("OpenSearch 使用当前端口的绝对搜索模板和正确 MIME", metadata.template === origin + "/?q={searchTerms}" &&
      metadata.type.startsWith("application/opensearchdescription+xml"), "");

    await context.setOffline(true);
    const offline = await context.newPage();
    await offline.goto(origin + "/settings");
    // 路由已改成 lazy 分包，离线时也要等 React 拉分包并渲染
    const offlineHeading = offline.getByRole("heading", { name: "安装与离线" });
    const offlineRendered = await offlineHeading.waitFor({ timeout: 15000 }).then(() => true).catch(() => false);
    check("真实断网时未访问过的设置页仍能加载完整应用壳", offlineRendered && await offlineHeading.isVisible(), "");
    check("断网时 API 和 /go 不读取缓存壳", await offline.evaluate(async () => {
      const results = await Promise.allSettled([fetch("/api/health"), fetch("/go?url=https://example.test/")]);
      return results.every(result => result.status === "rejected");
    }), "");
    await offline.goto(origin + "/not-a-route");
    check("未知路径离线时显示独立离线页", (await offline.title()).includes("离线"), "");
    await offline.close();
    await context.setOffline(false);

    await page.evaluate(() => {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = "/share";
      form.enctype = "multipart/form-data";
      for (const [name, value] of Object.entries({ title: "分享标题", text: "说明 https://example.test/shared" })) {
        const input = document.createElement("input");
        input.name = name;
        input.value = value;
        form.append(input);
      }
      document.body.append(form);
      form.submit();
    });
    await page.waitForURL(url => url.pathname === "/bookmarks");
    const urlInput = page.getByLabel("新书签网址");
    await urlInput.waitFor();
    await page.waitForURL(origin + "/bookmarks");
    check("真实 multipart 导航分享在窄屏展开并预填", await urlInput.inputValue() === "https://example.test/shared" &&
      await page.getByLabel("新书签标题").inputValue() === "分享标题", "");
    const hasCleanGet = shareFollowups.length > 0 && shareFollowups.every(url => url === "/bookmarks");
    check("分享内容不进入后续 GET 或停留在地址栏", hasCleanGet && page.url() === origin + "/bookmarks",
      `GETs=${shareFollowups.length} clean=${hasCleanGet}`);

    await page.goto(origin + "/settings");
    await page.getByRole("heading", { name: "安装与离线" }).waitFor();
    await page.evaluate(() => {
      const event = new Event("beforeinstallprompt", { cancelable: true });
      event.prompt = async () => { throw new DOMException("Prompt unavailable", "InvalidStateError"); };
      window.dispatchEvent(event);
    });
    await page.getByRole("button", { name: "安装到桌面" }).click();
    check("浏览器安装提示失败可恢复并提示菜单入口", await page.getByText("安装未完成，可从浏览器菜单重试").isVisible(), "");

    const findUpdate = () => page.evaluate(async () => (await navigator.serviceWorker.getRegistration()).update());
    breakPrecache = true;
    version = "bbbbbbbbbbbbbbbbbbbb";
    const failedInstall = page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration();
      return new Promise(resolve => registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker.addEventListener("statechange", () => { if (worker.state === "redundant") resolve(true); });
      }, { once: true }));
    });
    await findUpdate();
    await failedInstall;
    check("新版资源缺失时保留旧 worker 和完整离线壳", await page.evaluate(async ([bad, original]) => {
      const keys = await caches.keys();
      return !keys.includes(`cs-shell-${bad}`) && keys.includes(`cs-shell-${original}`) && !!navigator.serviceWorker.controller;
    }, [version, originalVersion]), "");

    breakPrecache = false;
    version = "cccccccccccccccccccc";
    await findUpdate();
    const toast = page.locator(".update-toast");
    await toast.getByRole("button", { name: "稍后再说" }).click();
    check("稍后关闭提示并保留真实等待中的版本", await toast.count() === 0 &&
      await page.evaluate(async () => !!(await navigator.serviceWorker.getRegistration()).waiting), "");
    await page.reload();
    await toast.getByRole("button", { name: "立即更新" }).waitFor();
    check("新页面能发现已处于 waiting 的真实版本", await toast.isVisible(), "");
    await Promise.all([page.waitForEvent("domcontentloaded"), toast.getByRole("button", { name: "立即更新" }).click()]);
    await page.waitForFunction(async version => {
      const keys = await caches.keys();
      return keys.filter(key => key.startsWith("cs-shell-")).join() === `cs-shell-${version}` &&
        !!navigator.serviceWorker.controller && !document.querySelector(".update-toast");
    }, version);
    check("确认后新版真实接管并重新加载，旧缓存已清除", true, "");
  } finally {
    await context.close();
    await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
  }
}

async function auditCards(context, query) {
  const cards = await context.newPage();
  const url = "https://example.test:8443/%E6%96%87%E6%A1%A3/%E2%80%AEexample";
  const shortSnippet = "开发者参考手册包含安装配置、开发工具、调试排查与部署运行说明。".repeat(3);
  let saved = null;
  await cards.addInitScript(() => {
    navigator.share = async payload => {
      window.auditShare = payload;
      if (window.auditShareError) throw new DOMException("share error", window.auditShareError);
    };
  });
  await cards.route("**/api/bookmarks", async route => {
    if (route.request().method() !== "POST") return route.continue();
    saved = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: { item: { id: 1 }, deduplicated: false } });
  });
  await cards.route("**/api/search", route => {
    const item = {
      id: "audit-card", url, display_url: "unrelated.test › forged",
      title: "学C++开发、C# 和 Node.js 入门，另有 Node.jsx 与 XC++", snippet: shortSnippet,
      engine: ["google", "bing", "duckduckgo", "brave"], score: 1, risk: 0.4,
      reasons: ["测试风险原因"], favicon: null, published: "2026-11-13", read_minutes: null,
      go_url: "/go?u=audit&sig=audit",
    };
    return route.fulfill({ json: {
      parsed: { q: query, engine: "default", region: null, router: "default", expanded: [] },
      groups: { strong: [item, { ...item, id: "audit-long", title: "长摘要样本", snippet: shortSnippet.repeat(7) }], related: [], weak: [] },
      official: null, meta: { status: "ok", provider: "fixture", cached: false, ms: 10, total: 2,
        upstream_total: 2, engines: [], unresponsive: [], filtered: { dup: 0, risk: 0 }, official: 0, directory: 0, sid: "audit-cards" },
    } });
  });
  try {
    await cards.goto(BASE + "/?q=" + encodeURIComponent(query));
    const first = cards.locator("#result-audit-card");
    const long = cards.locator("#result-audit-long");
    await first.waitFor();
    const marks = await first.locator(".card__title mark").allTextContents();
    check("技术词高亮保留符号且避开词内命中", marks.join("|") === "C++|C#|Node.js", marks.join("|"));
    const breadcrumb = await first.locator(".card__url").innerText();
    check("面包屑使用实际域名和端口并保留双向控制符编码",
      breadcrumb === "example.test:8443 › 文档 › %E2%80%AEexample", breadcrumb);
    const engines = await first.locator(".card__tags .card__tag").allTextContents();
    check("引擎标签两项加准确的 +N", engines.join("|") === "google|bing|+2", engines.join("|"));
    const hrefs = await first.locator("a[href]").evaluateAll(links => links.map(link => link.getAttribute("href")));
    check("标题和操作入口均保留风险确认中转", hrefs.length === 2 && hrefs.every(href => href === "/go?u=audit&sig=audit"), "");

    const menu = first.locator("details");
    const trigger = menu.locator("summary");
    const nextTrigger = long.locator("details > summary");
    await trigger.press("Enter");
    await nextTrigger.press("Space");
    check("键盘打开另一张卡片时只保留一个操作菜单",
      await cards.locator(".card__actions[open]").count() === 1 && await long.locator("details[open]").count() === 1, "");
    await long.getByRole("button", { name: "复制链接" }).focus();
    await cards.keyboard.press("Escape");
    check("Esc 从操作项关闭并归还焦点", await nextTrigger.evaluate(node => node === document.activeElement && !node.parentElement.open), "");
    const share = menu.getByRole("button", { name: "分享" });
    await cards.evaluate(() => { window.auditShareError = "AbortError"; });
    await trigger.press("Enter");
    await share.press("Enter");
    await menu.locator("button").first().waitFor({ state: "hidden" });
    check("取消分享保持静默并归还焦点", await first.locator(".card__action-status").textContent() === "" &&
      await trigger.evaluate(node => node === document.activeElement) && await cards.evaluate(() => window.auditShare.url) === url, "");
    check("分享文案携带标题、换行和原链接", await cards.evaluate(() => {
      const { title, text, url } = window.auditShare;
      return Boolean(title) && text === `${title}\n${url}`;
    }), "");
    await cards.evaluate(() => { window.auditShareError = "NotAllowedError"; });
    await trigger.press("Enter");
    await share.press("Enter");
    await first.getByRole("status").getByText("分享链接失败", { exact: true }).waitFor({ timeout: 5000 });
    check("分享失败给出可见反馈", await trigger.evaluate(node => node === document.activeElement), "");
    await trigger.press("Enter");
    await menu.getByRole("button", { name: "复制链接" }).press("Enter");
    await first.getByRole("status").getByText("已复制链接", { exact: true }).waitFor({ timeout: 5000 });
    check("复制成功可见、可播报并归还焦点", await cards.evaluate(() => navigator.clipboard.readText()) === url &&
      await trigger.evaluate(node => node === document.activeElement && !node.parentElement.open), "");
    await cards.evaluate(() => {
      navigator.clipboard.writeText = () => Promise.reject(new DOMException("denied", "NotAllowedError"));
    });
    await trigger.press("Enter");
    await menu.getByRole("button", { name: "复制链接" }).press("Enter");
    await first.getByRole("status").getByText("复制链接失败", { exact: true }).waitFor({ timeout: 5000 });
    check("剪贴板被拒时显示失败并保留焦点", await trigger.evaluate(node => node === document.activeElement), "");
    await first.focus();
    await cards.keyboard.press("b");
    await menu.getByRole("button", { name: "已收藏" }).waitFor({ timeout: 5000 });
    check("b 快捷键显示收藏结果并发送原链接", saved?.url === url &&
      await trigger.evaluate(node => node === document.activeElement && node.parentElement.open), "");
    await cards.keyboard.press("Escape");

    const shortToggle = first.getByRole("button", { name: "展开摘要" });
    check("桌面三行以内的摘要不显示展开入口", await shortToggle.count() === 0, `chars=${shortSnippet.length}`);
    const longToggle = long.getByRole("button", { name: /展开摘要|收起摘要/ });
    await longToggle.waitFor();
    const collapsed = await long.locator(".card__snippet").evaluate(node => ({
      fitsThreeLines: node.scrollHeight > node.clientHeight && Math.abs(node.clientHeight / parseFloat(getComputedStyle(node).lineHeight) - 3) < 0.1,
      id: node.id,
    }));
    check("长摘要默认 clamp 到 3 行", collapsed.fitsThreeLines && await longToggle.getAttribute("aria-controls") === collapsed.id, "");
    await longToggle.press("Enter");
    check("展开摘要后显示全文", await long.locator(".card__snippet").evaluate(node => node.clientHeight === node.scrollHeight) &&
      await longToggle.getAttribute("aria-expanded") === "true", "");
    await longToggle.press("Space");
    await cards.setViewportSize({ width: 320, height: 720 });
    await shortToggle.waitFor({ timeout: 5000 });
    const bounds = await shortToggle.boundingBox();
    check("320px 下 120 字以内的摘要截断也能展开", shortSnippet.length < 120 && bounds.width >= 24 && bounds.height >= 24,
      `chars=${shortSnippet.length} size=${bounds.width}×${bounds.height}`);
    await shortToggle.press("Enter");
    check("窄屏展开恢复完整摘要", await first.locator(".card__snippet").evaluate(node => node.scrollHeight === node.clientHeight), "");
  } finally {
    await cards.close();
  }
}

async function checkFixtureServer() {
  const response = await fetch(BASE + "/api/health", { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`/api/health 返回 HTTP ${response.status}`);
  const health = await response.json();
  if (health.provider !== "fixture") {
    throw new Error(`完整浏览器审计需要 fixture，当前 provider=${health.provider}。真实 SearXNG 请运行 node scripts/verify-filters.cjs ${BASE}`);
  }
  if (!health.web_built) throw new Error("fixture 实例缺少前端构建，请先运行 npm --prefix apps/web run build");
}

(async () => {
  await checkFixtureServer();
  fs.mkdirSync(OUT, { recursive: true });
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ channel: CHANNEL });
  const report = { base: BASE, started_at: new Date().toISOString(), checks, screenshots: [] };
  try {
    // —— 桌面：历史 / 页码 / 标题 ——
    const desktop = await browser.newContext({
      viewport: { width: 1440, height: 900 }, locale: "zh-CN", serviceWorkers: "block",
      permissions: ["clipboard-read", "clipboard-write"],
    });
    const page = await desktop.newPage();
    await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    const first = await searchWithResults(page);
    const firstQuery = first.query;
    const secondQuery = QUERIES.find(item => item !== firstQuery) ?? "CleanSearch";
    const second = await runSearch(page, secondQuery);
    const titleSecond = await page.title();
    await page.goBack();
    await page.waitForSelector(READY, { timeout: 60000 });
    const afterBack = await page.evaluate(() => ({
      q: (document.querySelector('input[name="q"]') || {}).value ?? "",
      url: window.location.search,
      title: document.title,
      cards: document.querySelectorAll(".workspace [id^='result-']").length,
    }));
    check("后退回到上一次查询",
      afterBack.q === firstQuery && afterBack.url.includes("q=" + encodeURIComponent(firstQuery).replace(/%20/g, "+")),
      `url=${afterBack.url} input=${afterBack.q} 期望=${firstQuery}`);
    check("结果页标题含查询词", afterBack.title.includes(firstQuery), `title=${afterBack.title}`);
    check("第二次查询后标题跟着换", titleSecond.includes(secondQuery), `title=${titleSecond} 期望含 ${secondQuery}`);

    await page.locator(".workspace-nav__item", { hasText: "百科" }).click();
    await page.locator(".workspace-more > summary").click();
    await page.getByRole("button", { name: "搜索历史" }).click();
    await page.locator("#workspace-history").getByRole("link", { name: secondQuery, exact: true }).click();
    await page.waitForSelector(READY, { timeout: 60000 });
    await page.goBack();
    const historyBack = new URL(page.url()).searchParams;
    check("从分类重搜历史词只新增一条历史",
      historyBack.get("category") === "encyclopedia" && historyBack.get("q") === firstQuery,
      historyBack.toString());
    await page.goForward();
    await page.waitForSelector(READY, { timeout: 60000 });
    check("前进恢复重搜关键词", await page.locator('input[name="q"]').inputValue() === secondQuery, page.url());
    await runSearch(page, firstQuery);

    // 页码进 URL 且刷新后仍在第 2 页
    const pagerNext = page.locator(".workspace-results .pager button", { hasText: "下一页" }).first();
    const canPage = await pagerNext.isEnabled().catch(() => false);
    if (canPage) {
      await pagerNext.click();
      await page.waitForFunction(() => new URLSearchParams(location.search).get("page") === "2", null, { timeout: 60000 });
      await page.waitForSelector(READY, { timeout: 60000 });
      const pagedTitle = await page.title();
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForSelector(READY, { timeout: 60000 });
      const afterReload = await page.evaluate(() => ({
        url: window.location.search,
        label: document.querySelector(".pager__label")?.textContent ?? "",
      }));
      check("第 2 页刷新后仍在第 2 页",
        afterReload.url.includes("page=2") && afterReload.label.startsWith("第 2 页"),
        `url=${afterReload.url} label=${afterReload.label}`);
      check("翻页后标题标注页码", pagedTitle.includes("第 2 页"), `title=${pagedTitle}`);
    } else {
      check("第 2 页刷新后仍在第 2 页", false, "下一页不可用");
    }

    await runSearch(page, firstQuery);

    // 标题层级、跳转链接、播报区
    const a11y = await page.evaluate(() => ({
      h1: document.querySelectorAll("h1").length,
      h2Across: document.querySelectorAll("h2").length,
      cardTitleTags: Array.from(document.querySelectorAll(".card__title")).map(node => node.tagName),
      skip: !!document.querySelector('a.skip-link[href="#main"]'),
      main: !!document.querySelector("main#main"),
      live: document.querySelector('main > [role="status"][aria-live]')?.textContent ?? "",
    }));
    check("结果页只有一个 h1", a11y.h1 === 1, `h1=${a11y.h1}`);
    check("结果卡标题降为 h3", a11y.cardTitleTags.length > 0 && a11y.cardTitleTags.every(tag => tag === "H3"),
      a11y.cardTitleTags.slice(0, 3).join(","));
    check("存在 skip link 与 main#main", a11y.skip && a11y.main, `skip=${a11y.skip} main=${a11y.main}`);
    check("搜索结果有 aria-live 播报", /找到 \d+ 条结果/.test(a11y.live), `live=${a11y.live}`);
    await axeScan(page, "结果页");

    // —— P1-1 统计条折叠 ——
    const metaBar = await page.evaluate(() => {
      const bar = document.querySelector(".metabar");
      const sid = document.querySelector(".metabar__sid");
      const more = document.querySelector(".metabar__more");
      const visible = sid && typeof sid.checkVisibility === "function"
        ? sid.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true })
        : !!sid && sid.getBoundingClientRect().width > 0;
      return {
        height: bar?.getBoundingClientRect().height ?? 0,
        text: bar?.innerText ?? "",
        open: !!more?.open,
        sidVisible: !!visible,
        sidText: sid?.textContent ?? "",
        detailsText: more?.querySelector(".metabar__details")?.textContent ?? "",
      };
    });
    const desktopStats = await compactStats(page);
    check("统计条压成一行", desktopStats.height <= 44 && desktopStats.singleLine && desktopStats.fits,
      `h=${Math.round(desktopStats.height)}`);
    check("sid 默认收进「检索详情」", !metaBar.open && !metaBar.sidVisible && !metaBar.text.includes("sid"),
      `open=${metaBar.open} sidVisible=${metaBar.sidVisible} text=${metaBar.text.replace(/\s+/g, " ").slice(0, 60)}`);
    check("检索详情含上游/去重/引擎/sid",
      ["上游", "去重", "引擎", "sid"].every(key => metaBar.detailsText.includes(key)), "");
    const statsToggle = page.locator(".metabar__more > summary");
    await statsToggle.focus();
    const statsBefore = await statsToggle.boundingBox();
    await page.keyboard.press("Enter");
    const statsAfter = await statsToggle.boundingBox();
    const metaOpened = await page.evaluate(() => {
      const sid = document.querySelector(".metabar__sid");
      return {
        open: !!document.querySelector(".metabar__more")?.open,
        sidVisible: sid && typeof sid.checkVisibility === "function"
          ? sid.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true }) : false,
      };
    });
    check("展开检索详情后 sid 可见", metaOpened.open && metaOpened.sidVisible,
      `open=${metaOpened.open} sidVisible=${metaOpened.sidVisible}`);
    check("检索详情展开时按钮位置和焦点保持不变",
      Math.abs(statsBefore.y - statsAfter.y) <= 1 && Math.abs(statsBefore.x - statsAfter.x) <= 1 &&
      await statsToggle.evaluate(node => node === document.activeElement),
      `y=${statsBefore.y}→${statsAfter.y}`);
    await page.keyboard.press("Space");
    check("检索详情可用 Space 收起", await statsToggle.evaluate(node => !node.parentElement.open), "");

    // —— P1-3 结果高亮与卡片降噪 ——
    const cardStats = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll(".workspace .card"));
      const marks = Array.from(document.querySelectorAll(".workspace mark.hl"));
      const tagGroups = Array.from(document.querySelectorAll(".card__tags"));
      const overflowTagGroup = tagGroups.find(group => group.querySelector(".card__tag--more"));
      const urls = Array.from(document.querySelectorAll(".card__url")).map(node => ({
        text: (node.textContent ?? "").trim(),
        title: node.getAttribute("title") ?? "",
      }));
      const flags = Array.from(document.querySelectorAll(".card__flags")).find(group =>
        group.querySelector(".card__tag") && group.querySelector(".card__risk"));
      const flagTops = flags ? Array.from(flags.children).map(node => node.getBoundingClientRect().top) : [];
      return {
        cards: cards.length,
        marks: marks.length,
        markedTitles: document.querySelectorAll(".card__title mark.hl").length,
        markedSnippets: document.querySelectorAll(".card__snippet mark.hl").length,
        markText: marks[0]?.textContent ?? "",
        markBg: marks[0] ? getComputedStyle(marks[0]).backgroundColor : "",
        maxTags: Math.max(0, ...tagGroups.map(group => group.querySelectorAll(".card__tag").length)),
        moreBadge: overflowTagGroup?.querySelector(".card__tag--more")?.textContent ?? "",
        moreTitle: overflowTagGroup?.querySelector(".card__tag--more")?.getAttribute("title") ?? "",
        urlSample: urls[0] ?? null,
        urlHasScheme: urls.some(item => item.text.includes("://")),
        flagSameLine: flagTops.length > 1 ? Math.max(...flagTops) - Math.min(...flagTops) <= 2 : true,
        actions: document.querySelectorAll(".card__actions").length,
        menuOpen: !!document.querySelector(".card__actions[open]"),
      };
    });
    check("标题/摘要命中查询词并高亮", cardStats.markedTitles > 0 && cardStats.marks > 0,
      `titles=${cardStats.markedTitles} snippets=${cardStats.markedSnippets} first=${cardStats.markText}`);
    check("高亮词与查询一致（不区分大小写）",
      cardStats.markText.toLowerCase() === firstQuery.toLowerCase(),
      `mark=${cardStats.markText} query=${firstQuery}`);
    check("高亮有可见底色", !!cardStats.markBg && cardStats.markBg !== "rgba(0, 0, 0, 0)" && cardStats.markBg !== "transparent",
      `bg=${cardStats.markBg}`);
    check("引擎标签最多 2 个 + N", cardStats.maxTags <= 3, `maxTags=${cardStats.maxTags} more=${cardStats.moreBadge}`);
    check("+N 数量与引擎总数一致", (() => {
      if (!cardStats.moreBadge) return true;
      const total = cardStats.moreTitle ? cardStats.moreTitle.split(" / ").length : 0;
      return total > 2 && cardStats.moreBadge === `+${total - 2}`;
    })(), `badge=${cardStats.moreBadge} title=${cardStats.moreTitle}`);
    check("域名显示为面包屑（无协议头）", !!cardStats.urlSample && !cardStats.urlHasScheme,
      `${cardStats.urlSample?.text} ← ${cardStats.urlSample?.title}`);
    check("发布时间与风险提示同一行", cardStats.flagSameLine, "");
    check("操作收进卡片菜单且默认收起", cardStats.actions === cardStats.cards && !cardStats.menuOpen,
      `actions=${cardStats.actions} cards=${cardStats.cards} open=${cardStats.menuOpen}`);

    const firstMenu = page.locator(".card__actions").first();
    await firstMenu.locator("summary").click();
    const menuItems = await firstMenu.evaluate(node => ({
      labels: Array.from(node.querySelectorAll(".card__actions-menu :is(button, a)")).map(item => item.textContent.trim()),
      expanded: node.open,
    }));
    check("卡片菜单含收藏/复制/打开",
      ["收藏", "复制", "打开链接"].every(key => menuItems.labels.some(label => label.includes(key))),
      menuItems.labels.join(" | "));
    await page.locator(".workspace-nav").click({ position: { x: 6, y: 6 } });
    check("点外部收起卡片菜单", await page.locator(".card__actions[open]").count() === 0, "");

    await page.locator(".card__actions").first().locator("summary").click();
    await page.locator(".card__actions-menu button").filter({ hasText: "复制链接" }).first().click();
    const clipboard = await page.evaluate(async () => {
      try { return await navigator.clipboard.readText(); } catch { return ""; }
    });
    check("复制链接写入剪贴板", /^https?:\/\//.test(clipboard), clipboard.slice(0, 60));

    await auditCards(desktop, "C++ C# Node.js");
    // —— P1-5 分页信息与 [ ] 快捷键（用可控第 2 页，固定样本第 2 页为空）——
    const pagerPage = await desktop.newPage();
    await pagerPage.route("**/api/search", async route => {
      const body = route.request().postDataJSON();
      const response = await route.fetch({ postData: { ...body, page: 1 } });
      const json = await response.json();
      if (body.page === 2 || body.page === 10) {
        json.official = null;
        const item = Object.values(json.groups).flat()[0];
        json.groups = { strong: item ? [{ ...item, category: "video" }] : [], related: [], weak: [] };
        json.meta = { ...json.meta, total: json.groups.strong.length, official: 0, sid: "audit-pager-2" };
      } else if (body.page === 3) {
        json.official = null;
        json.groups = { strong: [], related: [], weak: [] };
        json.meta = { ...json.meta, total: 0, official: 0, status: "empty" };
      }
      return route.fulfill({ response, json });
    });
    await pagerPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await pagerPage.waitForSelector(READY, { timeout: 60000 });
    const pagerState = await pagerPage.evaluate(() => ({
      tops: document.querySelectorAll(".pager--top").length,
      bottoms: document.querySelectorAll(".pager--bottom").length,
      topLabel: (document.querySelector(".pager--top .pager__label")?.textContent ?? "").trim(),
      bottomLabel: (document.querySelector(".pager--bottom .pager__label")?.textContent ?? "").trim(),
    }));
    check("顶部与底部各有一组分页", pagerState.tops === 1 && pagerState.bottoms === 1,
      `top=${pagerState.tops} bottom=${pagerState.bottoms}`);
    check("分页显示当前页与本页条数", /^第 1 页 · 本页 \d+ 条$/.test(pagerState.topLabel) && pagerState.topLabel === pagerState.bottomLabel,
      `top=${pagerState.topLabel} bottom=${pagerState.bottomLabel}`);
    await pagerPage.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await pagerPage.keyboard.press("]");
    await pagerPage.waitForFunction(() => new URLSearchParams(location.search).get("page") === "2", null, { timeout: 30000 });
    await pagerPage.waitForSelector(READY, { timeout: 30000 });
    const afterBracket = await pagerPage.evaluate(() => ({
      page: new URLSearchParams(location.search).get("page"),
      top: document.querySelector(".workspace-results")?.getBoundingClientRect().top ?? -1,
      label: (document.querySelector(".pager--top .pager__label")?.textContent ?? "").trim(),
      cards: document.querySelectorAll(".workspace [id^='result-']").length,
      expectedTop: Math.max(parseFloat(getComputedStyle(document.querySelector(".workspace-results")).scrollMarginTop),
        document.querySelector(".workspace-results").getBoundingClientRect().top +
        scrollY - (document.documentElement.scrollHeight - innerHeight)),
    }));
    check("] 翻到下一页", afterBracket.page === "2" && afterBracket.cards > 0,
      `page=${afterBracket.page} cards=${afterBracket.cards} label=${afterBracket.label}`);
    check("翻页后滚回结果区顶部", afterBracket.top >= 0 && Math.abs(afterBracket.top - afterBracket.expectedTop) <= 2,
      `results top=${Math.round(afterBracket.top)}`);
    check("不等长的第 2 页只显示本页实际条数", afterBracket.label === "第 2 页 · 本页 1 条",
      afterBracket.label);
    await pagerPage.reload({ waitUntil: "domcontentloaded" });
    await pagerPage.waitForSelector(READY);
    check("刷新直入第 2 页时条数一致", await pagerPage.locator(".pager--top .pager__label").innerText() === afterBracket.label, "");
    await pagerPage.getByRole("button", { name: "百科", exact: true }).click();
    check("分类本页无匹配仍可继续翻页", await pagerPage.locator(".pager--top .pager__label").innerText() === "第 2 页 · 本页无结果" &&
      await pagerPage.locator(".pager--top").getByRole("button", { name: "下一页" }).isEnabled(), "");
    await pagerPage.getByRole("button", { name: "首页", exact: true }).click();
    await pagerPage.keyboard.press("]");
    await pagerPage.locator(".state--empty").waitFor();
    check("空页显示真实状态并禁用下一页", await pagerPage.locator(".pager--top .pager__label").innerText() === "第 3 页 · 本页无结果" &&
      await pagerPage.getByRole("button", { name: "下一页" }).isDisabled(), "");
    await pagerPage.keyboard.press("]");
    check("空页的下一页快捷键与按钮一致", new URL(pagerPage.url()).searchParams.get("page") === "3", pagerPage.url());
    await pagerPage.keyboard.press("[");
    await pagerPage.waitForSelector(READY);
    check("空页可用上一页快捷键恢复结果", new URL(pagerPage.url()).searchParams.get("page") === "2" &&
      await pagerPage.locator(".pager--top .pager__label").innerText() === afterBracket.label, pagerPage.url());
    await pagerPage.keyboard.press("[");
    await pagerPage.waitForFunction(() => !new URLSearchParams(location.search).get("page"), null, { timeout: 30000 });
    await pagerPage.waitForSelector(READY, { timeout: 30000 });
    check("[ 回到上一页", !new URL(pagerPage.url()).searchParams.get("page"), pagerPage.url());
    await pagerPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery) + "&page=10");
    await pagerPage.waitForSelector(READY);
    await pagerPage.keyboard.press("]");
    check("第 10 页的下一页按钮与快捷键均到达上限", new URL(pagerPage.url()).searchParams.get("page") === "10" &&
      await pagerPage.locator(".pager--top").getByRole("button", { name: "下一页" }).isDisabled(), "");
    await pagerPage.close();

    // —— P1-6 搜索建议 ——
    await page.locator(".workspace-nav__item").first().click();
    await page.keyboard.press("Control+k");
    const focusedByShortcut = await page.evaluate(() => document.activeElement?.getAttribute("name"));
    check("Ctrl/Cmd+K 聚焦搜索框", focusedByShortcut === "q", `active=${focusedByShortcut}`);
    await page.fill('input[name="q"]', "");
    await page.waitForSelector('.suggest[role="listbox"]', { timeout: 8000 });
    const suggestState = await page.evaluate(() => ({
      options: document.querySelectorAll(".suggest__item").length,
      firstLabel: (document.querySelector(".suggest__label")?.textContent ?? "").trim(),
      firstHint: (document.querySelector(".suggest__hint")?.textContent ?? "").trim(),
      expanded: document.querySelector('input[name="q"]')?.getAttribute("aria-expanded"),
    }));
    check("聚焦/输入时给出搜索建议", suggestState.options > 0 && suggestState.expanded === "true",
      `options=${suggestState.options} first=${suggestState.firstLabel} (${suggestState.firstHint})`);
    await page.keyboard.press("ArrowDown");
    const activeDescendant = await page.evaluate(() =>
      document.querySelector('input[name="q"]')?.getAttribute("aria-activedescendant"));
    check("方向键选择建议（aria-activedescendant）", !!activeDescendant, `id=${activeDescendant}`);
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => !document.querySelector(".suggest"), null, { timeout: 15000 });
    await page.waitForSelector(READY, { timeout: 30000 });
    const chosen = await page.evaluate(() => ({
      q: new URLSearchParams(location.search).get("q") ?? "",
      closed: !document.querySelector(".suggest"),
    }));
    check("Enter 采纳建议并直接搜索", chosen.closed && chosen.q.length > 0 &&
      chosen.q.toLowerCase().includes(suggestState.firstLabel.toLowerCase().slice(0, 6)),
      `q=${chosen.q} 期望含 ${suggestState.firstLabel}`);
    await page.keyboard.press("Control+k");
    await page.waitForSelector(".suggest", { timeout: 8000 });
    await page.keyboard.press("Escape");
    const escapeState = await page.evaluate(() => ({
      closed: !document.querySelector(".suggest"),
      focus: document.activeElement?.getAttribute("name"),
    }));
    check("Esc 收起建议且不丢焦点", escapeState.closed && escapeState.focus === "q",
      `closed=${escapeState.closed} focus=${escapeState.focus}`);
    const suggestionsPage = await desktop.newPage();
    await suggestionsPage.route("**/api/engines", async route => {
      const response = await route.fetch();
      const catalog = await response.json();
      await route.fulfill({ json: { ...catalog, engines: catalog.engines.map(engine =>
        engine.code === "b" ? { ...engine, selectable: true } : engine) } });
    });
    await suggestionsPage.addInitScript(() => {
      localStorage.setItem("cs-search-history", JSON.stringify([{ query: "Python ds", literal: true }]));
    });
    let unexpectedAI = 0;
    await suggestionsPage.route("**/api/ai-search", route => {
      unexpectedAI++;
      return route.fulfill({ json: { provider: "audit-stub", results: [] } });
    });
    await suggestionsPage.goto(BASE + "/");
    const field = suggestionsPage.getByRole("combobox", { name: "搜索查询" });
    await field.focus();
    check("空输入的建议没有孤立引擎后缀", await suggestionsPage.getByRole("option", { name: /引擎后缀/ }).count() === 0, "");
    await field.fill("Python d");
    await field.press("Escape");
    await field.press("ArrowDown");
    const selected = await field.evaluate(node => document.getElementById(node.getAttribute("aria-activedescendant"))?.textContent);
    check("Esc 后方向键可重开并选中原建议", selected?.includes("Python ds") && await field.inputValue() === "Python d", selected);
    await field.dispatchEvent("compositionstart", { bubbles: true });
    const ime = await field.evaluate(node => node.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Enter", bubbles: true, cancelable: true, isComposing: true,
    })));
    check("输入法组合期间 Enter 交由输入法处理", ime && await field.inputValue() === "Python d" &&
      await field.getAttribute("aria-expanded") === "false", "");
    await field.dispatchEvent("compositionend", { bubbles: true });
    await field.press("ArrowDown");
    const literalRequest = suggestionsPage.waitForRequest(request => new URL(request.url()).pathname === "/api/search");
    await field.press("Enter");
    const literalBody = (await literalRequest).postDataJSON();
    await suggestionsPage.waitForSelector(READY);
    check("历史建议提交原查询并保留字面模式", literalBody.q === "Python ds" && literalBody.opts.literal === true &&
      new URL(suggestionsPage.url()).searchParams.get("literal") === "1" && unexpectedAI === 0, JSON.stringify(literalBody.opts));
    await field.fill("python !b");
    const engine = suggestionsPage.getByRole("option", { name: /引擎后缀 !b(?:\s|$)/ });
    await engine.waitFor();
    await engine.click();
    await suggestionsPage.waitForSelector(READY);
    check("点选引擎前缀补全保留查询正文", new URL(suggestionsPage.url()).searchParams.get("q") === "python !b" &&
      !new URL(suggestionsPage.url()).searchParams.has("literal"), suggestionsPage.url());
    await suggestionsPage.close();
    await page.locator(".workspace-nav__item").first().click();
    // —— P1-7 快捷键面板 ——
    const keyboardInvoker = page.locator(".workspace-nav__item").first();
    await keyboardInvoker.focus();
    await page.keyboard.press("?");
    await page.waitForSelector(".shortcuts-dialog[open]", { timeout: 8000 });
    const shortcuts = await page.evaluate(() => ({
      title: document.querySelector(".shortcuts-dialog__head h2")?.textContent ?? "",
      text: (document.querySelector(".shortcuts-dialog__body")?.innerText ?? "").replace(/\s+/g, " "),
      groups: document.querySelectorAll(".shortcuts-dialog__body section").length,
      modal: document.querySelector(".shortcuts-dialog")?.matches(":modal") ?? false,
    }));
    check("? 打开快捷键面板（模态）", shortcuts.title.includes("键盘快捷键") && shortcuts.modal && shortcuts.groups >= 3,
      `title=${shortcuts.title} groups=${shortcuts.groups}`);
    check("面板列出 g h / g b / [ ] / Ctrl K",
      ["g h", "g b", "[ ]", "⌘ K"].every(key => shortcuts.text.includes(key)),
      shortcuts.text.replace(/\s+/g, " ").slice(0, 80));
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector(".shortcuts-dialog[open]"), null, { timeout: 8000 });
    check("Esc 关闭面板并把焦点还给键盘调用处", await keyboardInvoker.evaluate(node => node === document.activeElement), "");
    const shortcutButton = page.getByRole("button", { name: /全部快捷键/ });
    await shortcutButton.press("Enter");
    const shortcutDialog = page.getByRole("dialog", { name: "键盘快捷键" });
    await shortcutDialog.waitFor();
    const modalUrl = page.url();
    await page.keyboard.press("g");
    await page.keyboard.press("b");
    await page.keyboard.press("]");
    check("快捷键面板打开时屏蔽背景导航和翻页", page.url() === modalUrl && await shortcutDialog.isVisible(), "");
    await shortcutDialog.getByRole("button", { name: "关闭" }).click();
    await page.waitForFunction(() => !document.querySelector(".shortcuts-dialog[open]"));
    check("按钮关闭面板并归还调用按钮焦点", await shortcutButton.evaluate(node => node === document.activeElement), "");
    await shortcutButton.click();
    await shortcutDialog.waitFor();
    await page.mouse.click(10, 10);
    await page.waitForFunction(() => !document.querySelector(".shortcuts-dialog[open]"));
    check("点击原生遮罩关闭快捷键面板", await shortcutButton.evaluate(node => node === document.activeElement), "");
    await page.evaluate(() => delete HTMLDialogElement.prototype.closedBy);
    await shortcutButton.press("Enter");
    await shortcutDialog.evaluate(node => node.removeAttribute("closedby"));
    await page.mouse.click(10, 10);
    await page.waitForFunction(() => !document.querySelector(".shortcuts-dialog[open]"));
    check("不支持 closedby 时仍可点击遮罩关闭", await shortcutButton.evaluate(node => node === document.activeElement), "");
    // 等原生 close 事件与 React 更新完成，再验证全局快捷键。
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.locator(".workspace-results").focus();
    await page.keyboard.press("g");
    await page.keyboard.press("b");
    await page.waitForURL(/\/bookmarks$/, { timeout: 15000 });
    check("g b 打开书签页", /\/bookmarks$/.test(page.url()), page.url());
    await page.goBack();
    await page.waitForSelector(READY, { timeout: 30000 });

    // —— P1-8 书签状态持久化与撤销 ——
    const bmk = await desktop.newPage();
    let savedBookmarkId = 42;
    let statusUrls = [];
    let undoAttempts = 0;
    let deleteUrl;
    let saveAttempts = 0;
    let releaseSave;
    let releaseLookup;
    let lookupAfterSave = 0;
    await bmk.route("**/api/bookmarks/42/result?*", route => {
      deleteUrl = new URL(route.request().url()).searchParams.get("url");
      if (++undoAttempts === 1) return route.fulfill({ status: 503, json: { detail: "固定失败" } });
      savedBookmarkId = 0;
      return route.fulfill({ status: 204 });
    });
    await bmk.route("**/api/bookmarks/status*", route => {
      const urls = new URL(route.request().url()).searchParams.getAll("urls");
      statusUrls = urls;
      const snapshot = savedBookmarkId ? Object.fromEntries(urls.slice(0, 2).map(url => [url, savedBookmarkId])) : {};
      if (savedBookmarkId === 43) lookupAfterSave++;
      if (releaseLookup === undefined && !savedBookmarkId) {
        return new Promise(resolve => { releaseLookup = resolve; }).then(() => route.fulfill({ json: snapshot })).catch(() => {});
      }
      return route.fulfill({ json: snapshot });
    });
    await bmk.route("**/api/bookmarks", async route => {
      if (route.request().method() === "POST") {
        saveAttempts++;
        await new Promise(resolve => { releaseSave = resolve; });
        savedBookmarkId = 43;
        return route.fulfill({ status: 201, json: { item: { id: 43 }, deduplicated: false } });
      }
      return route.continue();
    });
    const firstUrl = "https://example.test/bookmark";
    await bmk.route("**/api/search", async route => {
      const response = await route.fetch();
      const json = await response.json();
      const sample = Object.values(json.groups).flat()[0];
      json.groups = { strong: [
        { ...sample, id: "audit-bookmark-first", url: firstUrl, category: null },
        { ...sample, id: "audit-bookmark-alias", url: `${firstUrl}?utm_source=audit`, category: null },
      ], related: [], weak: [] };
      json.official = null;
      json.meta = { ...json.meta, official: 0, total: 2 };
      return route.fulfill({ response, json });
    });
    await bmk.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    const card = bmk.locator("#result-audit-bookmark-first");
    const aliasCard = bmk.locator("#result-audit-bookmark-alias");
    await bmk.waitForFunction(() => document.querySelectorAll(".card__undo").length === 2);
    const statusState = await card.evaluate(card => ({
      label: card.querySelector(".card__save")?.textContent ?? "",
      pressed: card.querySelector(".card__save")?.getAttribute("aria-pressed"),
      disabled: card.querySelector(".card__save")?.disabled,
      undo: !!card.querySelector(".card__undo"),
    }));
    check("已收藏的结果卡启动即显示已在书签",
      statusState.label === "已在书签" && statusState.pressed === "true" && statusState.disabled,
      `label=${statusState.label} pressed=${statusState.pressed}`);
    check("已收藏时给出撤销入口", statusState.undo, "");
    check("批量状态查询只带 http(s) 且不超过 40 个",
      statusUrls.length === 2 && statusUrls.every(url => /^https?:\/\//.test(url)), `urls=${statusUrls.length}`);
    await card.locator(".card__actions summary").click();
    await card.locator(".card__undo").click();
    await card.getByText("撤销收藏失败，请重试", { exact: true }).waitFor();
    check("撤销失败保留书签状态并允许重试", await card.locator(".card__save").isDisabled() &&
      await card.getByRole("button", { name: "撤销收藏" }).isEnabled(), "");
    await card.getByRole("button", { name: "撤销收藏" }).press("Enter");
    await card.locator(".card__undo").waitFor({ state: "detached" });
    const undone = await card.evaluate(card => ({
      label: card.querySelector(".card__save")?.textContent ?? "",
      undo: !!card.querySelector(".card__undo"),
    }));
    check("撤销后同步同一书签的两张卡并核对请求网址", undone.label === "收藏" && !undone.undo &&
      await aliasCard.locator(".card__undo").count() === 0 && deleteUrl === firstUrl, JSON.stringify(undone));
    check("键盘撤销后聚焦收藏按钮", await card.locator(".card__save").evaluate(node => node === document.activeElement), "");
    const saveRequest = bmk.waitForRequest(request => request.method() === "POST" && new URL(request.url()).pathname === "/api/bookmarks");
    await card.locator(".card__save").click();
    await saveRequest;
    const optimistic = await card.evaluate(card => card.querySelector(".card__save")?.textContent ?? "");
    await card.locator(".card__save").evaluate(button => button.click());
    check("收藏等待响应时乐观展示，禁止重复保存和提前撤销", optimistic === "已收藏" &&
      await card.locator(".card__save").isDisabled() && await card.locator(".card__undo").count() === 0 && saveAttempts === 1, "");
    releaseSave();
    await card.locator(".card__undo").waitFor();
    await bmk.waitForFunction(() => document.querySelector("#result-audit-bookmark-alias .card__undo"));
    releaseLookup?.();
    check("重收藏后旧的空状态响应不能覆盖新状态", await card.locator(".card__save").innerText() === "已收藏" &&
      await aliasCard.locator(".card__save").textContent() === "已在书签" && lookupAfterSave > 0 && saveAttempts === 1, "");
    await bmk.close();
    // —— P1-9/P1-10 错误态产品化与空态/分类提示 ——
    const statePage = await desktop.newPage();
    let failNetwork = true;
    await statePage.route("**/api/health", route => route.fulfill({ json: { provider: "searxng", status: "ok" } }));
    await statePage.route("**/api/search", route => failNetwork ? route.abort("failed") : route.continue());
    await statePage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await statePage.waitForSelector(".state--error", { timeout: 30000 });
    const netError = await statePage.evaluate(() => ({
      title: document.querySelector(".state--error h2")?.textContent ?? "",
      actions: Array.from(document.querySelectorAll(".state--error .state__actions > *")).map(node => node.textContent.trim()),
      settings: document.querySelector(".state--error .state__actions a")?.getAttribute("href") ?? "",
      diagnostics: !!document.querySelector(".state--error .state__diagnostics"),
    }));
    check("断网错误标题产品化", netError.title.includes("本机搜索服务未连接"), netError.title);
    check("错误态给出重试与打开设置", netError.actions.some(t => t.includes("重试")) &&
      netError.settings.includes("/settings"), `actions=${netError.actions.join("/")} href=${netError.settings}`);
    check("非 debug 时不展示诊断详情", !netError.diagnostics, `details=${netError.diagnostics}`);
    check("错误状态通过已挂载的状态区播报", (await statePage.locator('main > [role="status"]').textContent()).includes(netError.title), "");
    failNetwork = false;
    await statePage.getByRole("button", { name: "重试", exact: true }).press("Enter");
    await statePage.locator(".results-body:not([aria-busy]) .pager").first().waitFor();
    check("网络恢复后重试成功并聚焦分页", await statePage.locator(".pager__label").first().evaluate(node => node === document.activeElement), "");
    failNetwork = true;

    await statePage.goto(BASE + "/?debug=1&q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await statePage.waitForSelector(".state--error .state__diagnostics", { timeout: 30000 });
    const diagClosed = await statePage.evaluate(() => !!document.querySelector(".state--error .state__diagnostics")?.open);
    await statePage.locator(".state--error .state__diagnostics > summary").click();
    const diag = await statePage.evaluate(() => {
      const box = document.querySelector(".state--error .state__diagnostics");
      return { open: !!box?.open, text: box?.innerText.replace(/\s+/g, " ") ?? "" };
    });
    check("?debug=1 才显示诊断详情且默认收起", !diagClosed && diag.open && diag.text.includes("错误码"),
      `closed=${diagClosed} text=${diag.text.slice(0, 40)}`);
    check("诊断详情含上游排查命令", /curl|SEARCH_PROVIDER/.test(diag.text), diag.text.slice(-40));
    await statePage.reload();
    await statePage.locator(".state__diagnostics > summary").waitFor();
    check("诊断开关在刷新后保留", new URL(statePage.url()).searchParams.get("debug") === "1", "");

    await statePage.unroute("**/api/search");
    let errorCode = "SEARCH_ENGINES_DISABLED";
    await statePage.route("**/api/search", route => route.fulfill({
      status: errorCode === "SEARCH_ENGINES_DISABLED" ? 422 : 502,
      json: { error: { code: errorCode, message: "internal-host-audit" , retryable: errorCode !== "SEARCH_ENGINES_DISABLED" } },
    }));
    await statePage.goto(BASE + "/?q=quiet");
    await statePage.getByRole("heading", { name: "普通搜索已暂停" }).waitFor();
    check("关闭全部默认引擎时提供修改查询和设置", await statePage.getByRole("button", { name: "重试", exact: true }).count() === 0 &&
      await statePage.getByRole("button", { name: "换关键词" }).isVisible() && await statePage.getByRole("link", { name: "打开设置" }).isVisible(), "");
    errorCode = "UPSTREAM_BAD_RESPONSE";
    await statePage.setViewportSize({ width: 320, height: 740 });
    await statePage.goto(BASE + "/?q=quiet");
    await statePage.getByRole("heading", { name: "搜索服务返回了无效响应" }).waitFor();
    check("非诊断模式隐藏上游原始消息且窄屏无横向溢出", await statePage.getByText("internal-host-audit").count() === 0 &&
      await statePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "");
    let aiRetries = 0;
    await statePage.route("**/api/ai-search", route => {
      aiRetries++;
      return route.fulfill({ json: { provider: "audit-stub", results: [] } });
    });
    await statePage.goto(BASE + "/?q=quiet+ds");
    await statePage.getByRole("heading", { name: "搜索服务返回了无效响应" }).waitFor();
    await statePage.getByText("audit-stub", { exact: true }).waitFor({ state: "attached" });
    const retryResponse = statePage.waitForResponse(response => new URL(response.url()).pathname === "/api/search");
    await statePage.getByRole("button", { name: "重试", exact: true }).press("Enter");
    await retryResponse;
    await statePage.getByRole("heading", { name: "搜索服务返回了无效响应" }).waitFor();
    check("普通搜索失败后的重试不重复请求 AI 检索", aiRetries === 1, `AI requests=${aiRetries}`);
    await statePage.setViewportSize({ width: 1440, height: 900 });

    // 空结果 + 引擎后缀 + 分类计数都用可控响应
    const emptyPayload = ({ q, opts }) => {
      const known = opts.literal ? null : /\s+(!?g)$/i.exec(q);
      return {
        parsed: { q: known ? q.slice(0, known.index) : q, engine: known ? "google" : "default", region: null,
          router: known ? (known[1].startsWith("!") ? "bang" : "suffix") : "default", expanded: [] },
        groups: { strong: [], related: [], weak: [] }, official: null,
        meta: { status: "empty", provider: "fixture", cached: false, ms: 1, total: 0, upstream_total: 0,
          engines: [], unresponsive: [], filtered: { dup: 0, risk: 0 }, official: 0, directory: 0, sid: "audit-empty" },
      };
    };
    await statePage.unroute("**/api/search");
    await statePage.route("**/api/search", route => route.fulfill({ json: emptyPayload(route.request().postDataJSON()) }));
    await statePage.goto(BASE + "/?q=quiet", { waitUntil: "domcontentloaded" });
    await statePage.waitForSelector(".state--empty", { timeout: 30000 });
    const emptyActions = await statePage.evaluate(() =>
      Array.from(document.querySelectorAll(".state--empty .state__actions > *")).map(node => node.textContent.trim()));
    check("空结果给出换关键词", emptyActions.some(text => text.includes("换关键词")), emptyActions.join("/"));
    await statePage.getByRole("button", { name: "换关键词" }).click();
    const focusedInput = await statePage.evaluate(() => document.activeElement?.getAttribute("name"));
    check("换关键词直接把焦点放进搜索框", focusedInput === "q", `active=${focusedInput}`);

    await statePage.goto(BASE + "/?q=" + encodeURIComponent("quiet !g"), { waitUntil: "domcontentloaded" });
    await statePage.waitForSelector(".state--empty", { timeout: 30000 });
    const suffixButton = statePage.getByRole("button", { name: /取消引擎后缀/ });
    check("空结果可一键取消引擎后缀", await suffixButton.count() === 1 &&
      (await suffixButton.innerText()).includes("!g"), "");
    await suffixButton.press("Enter");
    await statePage.locator(".state--empty h2").waitFor();
    const cleared = new URL(statePage.url()).searchParams;
    check("取消后缀后按原词重搜并保留恢复后的焦点", cleared.get("q") === "quiet" && cleared.get("literal") === "1" &&
      await statePage.locator(".state--empty h2").evaluate(node => node === document.activeElement), statePage.url());
    for (const [q, literal, shouldRemove] of [["quiet !g", true, false], ["quiet !unknown", false, false], ["quiet g", false, true]]) {
      await statePage.goto(BASE + "/?" + new URLSearchParams({ q, ...(literal ? { literal: "1" } : {}) }));
      await statePage.locator(".state--empty").waitFor();
      check(`仅对实际引擎路由提供取消（${q}${literal ? "，字面" : ""}）`, (await suffixButton.count() > 0) === shouldRemove, "");
    }

    // 分类计数与分类空态
    const categorized = (strong) => ({
      parsed: { q: "cat", engine: "default", region: null, router: "default", expanded: [] },
      groups: { strong, related: [], weak: [] }, official: null,
      meta: { status: "ok", provider: "fixture", cached: false, ms: 1, total: strong.length,
        upstream_total: strong.length, engines: [], unresponsive: [], filtered: { dup: 0, risk: 0 },
        official: 0, directory: 0, sid: "audit-cat" },
    });
    const makeResult = (id, category) => ({
      id, url: `https://example.test/${id}`, display_url: `example.test › ${id}`, title: `样本 ${id}`,
      snippet: "分类计数样本摘要", engine: ["google"], score: 1, risk: 0, reasons: [], favicon: null,
      published: null, read_minutes: null, category,
    });
    await statePage.unroute("**/api/search");
    await statePage.route("**/api/search", route => route.fulfill({
      json: categorized([makeResult("a", "encyclopedia"), makeResult("b", null), makeResult("c", null)]),
    }));
    await statePage.goto(BASE + "/?q=cat", { waitUntil: "domcontentloaded" });
    await statePage.waitForSelector(".results-body", { timeout: 30000 });
    await statePage.getByRole("navigation", { name: "搜索分类" }).getByRole("button", { name: "百科", exact: true }).click();
    await statePage.waitForSelector(".workspace-results__count", { timeout: 15000 });
    const categoryCount = await statePage.evaluate(() =>
      (document.querySelector(".workspace-results__count")?.textContent ?? "").replace(/\s+/g, " ").trim());
    check("分类页区分本页分类数和本页搜索结果数", categoryCount === "本页百科 1 条 · 本页搜索结果 3 条", categoryCount);
    await statePage.getByRole("navigation", { name: "搜索分类" }).getByRole("button", { name: "视频", exact: true }).click();
    await statePage.waitForSelector(".state--empty", { timeout: 15000 });
    const emptyCategory = await statePage.evaluate(() => ({
      title: document.querySelector(".state--empty h2")?.textContent ?? "",
      text: document.querySelector(".state--empty")?.innerText.replace(/\s+/g, " ") ?? "",
      actions: Array.from(document.querySelectorAll(".state--empty .state__actions > *")).map(node => node.textContent.trim()),
    }));
    check("分类空态说明还有其它结果并可查看全部",
      emptyCategory.title.includes("本页没有视频结果") && emptyCategory.text.includes("3 条其它结果") &&
      emptyCategory.actions.some(text => text.includes("查看全部结果")),
      `${emptyCategory.title} · ${emptyCategory.actions.join("/")}`);
    await statePage.getByRole("button", { name: "查看全部结果" }).click();
    await statePage.waitForSelector(".results-body .card", { timeout: 15000 });
    check("查看全部结果回到全部分类并交接焦点", await statePage.evaluate(() =>
      document.querySelector(".workspace-results__count") === null && document.activeElement?.classList.contains("pager__label")), "");
    await statePage.unroute("**/api/search");
    const official = { ...makeResult("official", null), host: "example.test", role: "home", label: "官网", origin: "directory" };
    await statePage.route("**/api/search", route => {
      const response = categorized([]);
      response.official = { key: "cat", brand: "样本", entries: [official] };
      response.meta.official = 1;
      return route.fulfill({ json: response });
    });
    await statePage.goto(BASE + "/?q=cat&category=video");
    const officialEmpty = statePage.locator(".state--empty");
    await officialEmpty.waitFor();
    check("仅有官方入口时分类空态单列入口", (await officialEmpty.innerText()).includes("另有 1 个官方入口") &&
      !(await officialEmpty.innerText()).includes("0 条其它结果"), "");
    await statePage.close();
    // —— P1-11 主题细节 ——
    const themePage = await desktop.newPage();
    await themePage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await themePage.waitForSelector(".workspace-results .pager", { timeout: 60000 });
    const themeToggle = themePage.locator(".theme-toggle");
    const readThemeState = () => themePage.evaluate(() => ({
      choice: document.documentElement.dataset.themeChoice,
      theme: document.documentElement.dataset.theme,
      scheme: getComputedStyle(document.documentElement).colorScheme,
      meta: document.querySelector('meta[name="theme-color"]')?.getAttribute("content") ?? "",
    }));
    for (let step = 0; step < 3; step += 1) {
      const now = await readThemeState();
      if (now.choice === "light") break;
      await themeToggle.click();
      await themePage.waitForTimeout(80);
    }
    const lightState = await readThemeState();
    check("浅色主题写死 color-scheme: light", lightState.scheme === "light", `scheme=${lightState.scheme}`);
    check("浅色主题同步 theme-color", lightState.meta.toLowerCase() === "#ffffff", `meta=${lightState.meta}`);
    await themeToggle.click();
    await themePage.waitForTimeout(80);
    const darkState = await readThemeState();
    check("深色主题写死 color-scheme: dark",
      darkState.theme === "dark" && darkState.scheme === "dark", `theme=${darkState.theme} scheme=${darkState.scheme}`);
    check("深色主题同步 theme-color",
      darkState.meta.toLowerCase() === "#1b2320" && darkState.meta !== lightState.meta, `meta=${darkState.meta}`);
    await themeToggle.click();
    await themePage.waitForTimeout(80);
    const autoState = await readThemeState();
    check("切回自动后 theme-color 跟随系统", autoState.choice === "auto" &&
      autoState.meta.toLowerCase() === (autoState.theme === "dark" ? "#1b2320" : "#ffffff"),
      `choice=${autoState.choice} theme=${autoState.theme} meta=${autoState.meta}`);
    const nextScheme = autoState.theme === "dark" ? "light" : "dark";
    await themePage.emulateMedia({ colorScheme: nextScheme });
    await themePage.waitForFunction(scheme => document.documentElement.dataset.theme === scheme, nextScheme);
    check("系统主题运行中切换时同步页面与浏览器色值", (await readThemeState()).meta === (nextScheme === "dark" ? "#1b2320" : "#ffffff"), "");
    const settingsTheme = await desktop.newPage();
    await settingsTheme.goto(BASE + "/settings");
    await settingsTheme.getByRole("radio", { name: "深色", exact: true }).check();
    await themePage.waitForFunction(() => document.querySelector(".theme-toggle")?.getAttribute("aria-label") === "主题：深色");
    await themePage.emulateMedia({ colorScheme: "light" });
    check("另一标签页的主题设置立即同步且保持手动深色", (await readThemeState()).scheme === "dark" &&
      await themeToggle.getAttribute("aria-label") === "主题：深色", "");
    await settingsTheme.getByRole("radio", { name: "跟随系统", exact: true }).check();
    await themePage.waitForFunction(() => document.documentElement.dataset.themeChoice === "auto");
    await settingsTheme.close();
    await themePage.close();

    const earlyTheme = await browser.newPage({ colorScheme: "light", serviceWorkers: "block" });
    await earlyTheme.addInitScript(() => localStorage.setItem("cs-theme", "dark"));
    await earlyTheme.route("**/assets/*.js", route => route.abort());
    await earlyTheme.goto(BASE + "/");
    const firstPaint = await earlyTheme.evaluate(() => ({
      mounted: document.querySelector("#root").childElementCount,
      scheme: getComputedStyle(document.documentElement).colorScheme,
      meta: document.querySelector('meta[name="theme-color"]').content,
    }));
    check("应用模块未加载时首屏已使用保存的主题", firstPaint.mounted === 0 && firstPaint.scheme === "dark" && firstPaint.meta === "#1b2320", JSON.stringify(firstPaint));
    await earlyTheme.close();

    const motionPage = await desktop.newPage();
    await motionPage.emulateMedia({ reducedMotion: "reduce" });
    await motionPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await motionPage.waitForSelector(".workspace-results .pager", { timeout: 60000 });
    const motionState = await motionPage.evaluate(() => {
      const animationName = (className) => {
        const node = document.createElement("span");
        node.className = className;
        document.body.append(node);
        const animation = getComputedStyle(node).animationName;
        node.remove();
        return animation;
      };
      return {
        reduce: matchMedia("(prefers-reduced-motion: reduce)").matches,
        scroll: getComputedStyle(document.documentElement).scrollBehavior,
        spinner: animationName("spinner"),
        cursor: animationName("summary__cursor"),
      };
    });
    check("减少动态效果时关闭 spinner 动画", motionState.reduce && motionState.spinner === "none",
      `reduce=${motionState.reduce} spinner=${motionState.spinner}`);
    check("减少动态效果时关闭总结光标动画", motionState.cursor === "none", `cursor=${motionState.cursor}`);
    check("减少动态效果时不做平滑滚动", motionState.scroll === "auto", `scroll=${motionState.scroll}`);
    const motionResult = await motionPage.locator(".workspace-results [id^='result-']:visible").first().getAttribute("id");
    await mockSummary(motionPage, motionResult.slice("result-".length));
    await motionPage.evaluate(() => {
      const scroll = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (options) {
        if (options?.block === "center") window.auditCitationScroll = options.behavior;
        return scroll.call(this, options);
      };
    });
    await motionPage.keyboard.press("s");
    await motionPage.locator(".citation").first().click();
    check("减少动态效果时总结引用立即定位", await motionPage.evaluate(() => window.auditCitationScroll === "instant"), "");
    await motionPage.emulateMedia({ reducedMotion: "no-preference" });
    await motionPage.locator(".citation").first().click();
    check("常规动态效果下总结引用保持平滑滚动", await motionPage.evaluate(() => window.auditCitationScroll === "smooth"), "");
    await motionPage.close();

    // —— P1-12 书签快捷栏刷新 ——
    const qbPage = await desktop.newPage();
    let qbCalls = 0;
    let qbLastUrl = "";
    await qbPage.route("**/api/bookmarks?*", route => {
      qbCalls += 1;
      qbLastUrl = route.request().url();
      const index = qbCalls;
      return route.fulfill({ json: {
        items: [{ id: index, url: "https://example.test/item-" + index, title: "条目 " + index,
          favicon: null, group_id: null, group_name: null, note: null, created_at: 0, dead: 0,
          dead_status: null, dead_checked_at: null, tags: [] }],
        groups: [], tags: [], total: 1, fts: false,
      } });
    });
    await qbPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await qbPage.waitForSelector(".quick-bookmarks__item", { timeout: 60000 });
    const firstItem = await qbPage.locator(".quick-bookmarks__item strong").first().innerText();
    await qbPage.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await qbPage.waitForFunction((before) => {
      const node = document.querySelector(".quick-bookmarks__item strong");
      return !!node && node.textContent !== before;
    }, firstItem, { timeout: 15000 }).catch(() => {});
    const afterVisible = await qbPage.locator(".quick-bookmarks__item strong").first().innerText();
    check("快捷栏在 visibilitychange 后刷新", afterVisible !== firstItem, `${firstItem} → ${afterVisible}`);
    const beforePageshow = qbCalls;
    await qbPage.evaluate(() => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await qbPage.waitForFunction(before => {
      const item = document.querySelector(".quick-bookmarks__item strong");
      return item && item.textContent !== before;
    }, afterVisible);
    check("恢复时合并 pageshow 与 visibilitychange 为一次快捷栏读取", qbCalls === beforePageshow + 1, `calls ${beforePageshow} → ${qbCalls}`);
    check("快捷栏只取 6 条并保留管理入口",
      /limit=6/.test(qbLastUrl) && await qbPage.locator(".quick-bookmarks__all").count() === 1,
      qbLastUrl.slice(qbLastUrl.indexOf("?")));
    const beforeUnrelated = qbCalls;
    await qbPage.evaluate(() => window.dispatchEvent(new StorageEvent("storage", { key: "cs-theme" })));
    await qbPage.waitForTimeout(150);
    check("无关的存储事件不刷新书签快捷栏", qbCalls === beforeUnrelated, `calls ${beforeUnrelated} → ${qbCalls}`);
    const quickToggle = qbPage.locator(".quick-bookmarks__toggle");
    await quickToggle.click();
    await qbPage.evaluate(() => window.dispatchEvent(new Event("cs:bookmarks-changed")));
    await qbPage.waitForTimeout(150);
    check("书签快捷栏折叠时跳过刷新", qbCalls === beforeUnrelated && await quickToggle.getAttribute("aria-expanded") === "false", "");
    await quickToggle.click();
    await qbPage.waitForFunction(before => document.querySelector(".quick-bookmarks__item strong")?.textContent === `条目 ${before + 1}`, beforeUnrelated);
    check("重新展开书签快捷栏时读取当前列表", qbCalls === beforeUnrelated + 1, "");
    if (TEST_BOOKMARK_WRITES) {
      const bookmarkTab = await desktop.newPage();
      const token = randomUUID();
      const bookmarkTitle = `快捷栏复核 ${token}`;
      const bookmarkUrl = `https://example.test/quickbar-${token}`;
      const importTitle = `快捷栏导入 ${token}`;
      const importUrl = `https://example.test/quickbar-import-${token}`;
      try {
        await qbPage.unroute("**/api/bookmarks?*");
        // 模拟两个同时可见的窗口，验证 storage 通知本身能刷新列表。
        await qbPage.evaluate(() => Object.defineProperty(document, "visibilityState", { value: "visible" }));
        await bookmarkTab.goto(BASE + "/bookmarks");
        await bookmarkTab.getByLabel("新书签网址").fill(bookmarkUrl);
        await bookmarkTab.getByLabel("新书签标题").fill(bookmarkTitle);
        const saved = bookmarkTab.waitForResponse(response => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/bookmarks");
        await bookmarkTab.getByRole("button", { name: "收藏", exact: true }).click();
        const { item: { id: bookmarkId } } = await (await saved).json();
        const quickItem = qbPage.locator(".quick-bookmarks__item").getByText(bookmarkTitle, { exact: true });
        await quickItem.waitFor();
        check("另一标签页真实收藏后刷新快捷栏", await quickItem.isVisible(), "");
        const removed = bookmarkTab.waitForResponse(response => response.request().method() === "DELETE" &&
          new URL(response.url()).pathname === `/api/bookmarks/${bookmarkId}`);
        await bookmarkTab.locator(".bm-card").filter({ hasText: bookmarkTitle }).getByRole("button", { name: "删除", exact: true }).click();
        const removal = await removed;
        await quickItem.waitFor({ state: "detached" });
        check("另一标签页真实删除后移除快捷项", removal.status() === 204 && await quickItem.count() === 0, "");
        await bookmarkTab.locator('input[type="file"]').setInputFiles({
          name: "quickbar-bookmarks.html",
          mimeType: "text/html",
          buffer: Buffer.from(`<!DOCTYPE NETSCAPE-Bookmark-file-1><META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8"><DL><p><DT><A HREF="${importUrl}">${importTitle}</A></DL>`),
        });
        await bookmarkTab.getByText("导入 1 条：新增 1，跳过 0 条，新建分组 0", { exact: true }).waitFor();
        const importedItem = qbPage.locator(".quick-bookmarks__item").filter({ hasText: importTitle });
        await importedItem.waitFor();
        check("另一标签页真实导入后刷新快捷栏", await importedItem.getAttribute("href") === importUrl, "");
      } finally {
        await cleanup(bookmarkTab.request, BASE, [bookmarkUrl, importUrl]);
        await bookmarkTab.close();
      }
    }
    await qbPage.close();
    // —— P1-13 AI 工具流控制 ——
    const streamPage = await desktop.newPage();
    // 挂住 SSE 请求，让流一直处于「生成中」，才能验证收起面板后的提示
    let releaseStream = null;
    await streamPage.route("**/api/summarize?*", async route => {
      await new Promise(resolve => { releaseStream = resolve; });
      return route.fulfill({
        contentType: "text/event-stream",
        body: "event: token\ndata: {\"t\":\"收尾\"}\n\nevent: done\ndata: {\"partial\":false,\"ms\":1}\n\n",
      }).catch(() => {});
    });
    await streamPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await streamPage.waitForSelector(".workspace-results .pager", { timeout: 60000 });
    const toolsGroup = streamPage.getByRole("group", { name: "AI 与翻译工具" });
    await toolsGroup.getByRole("button", { name: "AI 总结" }).click();
    await streamPage.getByRole("button", { name: "生成总结" }).click();
    await streamPage.waitForSelector(".summary__live", { timeout: 15000 });
    await toolsGroup.getByRole("button", { name: "AI 总结" }).click();
    await streamPage.waitForSelector(".background-task", { timeout: 8000 });
    const pill = await streamPage.evaluate(() => ({
      text: document.querySelector(".background-task")?.innerText.replace(/\s+/g, " ").trim() ?? "",
      actions: Array.from(document.querySelectorAll(".background-task__action")).map(node => node.textContent.trim()),
    }));
    check("收起总结面板后提示后台生成中", pill.text.includes("AI 总结正在后台生成"), pill.text);
    check("后台任务提供查看与停止", pill.actions.some(t => t === "停止") && pill.actions.some(t => t === "查看"),
      pill.actions.join("/"));
    await streamPage.locator(".background-task__action", { hasText: "停止" }).click();
    await streamPage.waitForFunction(() => !document.querySelector(".background-task"), null, { timeout: 8000 });
    const afterStop = await streamPage.evaluate(() => ({
      pill: !!document.querySelector(".background-task"),
      live: !!document.querySelector(".summary__live"),
    }));
    check("停止后后台提示与流都结束", !afterStop.pill && !afterStop.live, JSON.stringify(afterStop));
    check("停止后台总结后焦点回到工具入口", await toolsGroup.getByRole("button", { name: "AI 总结" })
      .evaluate(node => node === document.activeElement), "");
    releaseStream?.();
    await streamPage.close();

    const aiPage = await desktop.newPage();
    let aiReleased = null;
    await aiPage.route("**/api/ai-search", async route => {
      await new Promise(resolve => { aiReleased = resolve; });
      return route.fulfill({ json: { provider: "audit-stub", results: [], cached: false } }).catch(() => {});
    });
    await aiPage.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await aiPage.getByRole("switch", { name: "日常 AI 检索" }).check();
    await aiPage.fill('input[name="q"]', firstQuery);
    await aiPage.press('input[name="q"]', "Enter");
    await aiPage.waitForSelector(".workspace-results .pager", { timeout: 60000 });
    await aiPage.waitForTimeout(200);
    const aiTools = aiPage.getByRole("group", { name: "AI 与翻译工具" });
    await aiTools.getByRole("button", { name: "AI 检索" }).click();
    await aiPage.waitForSelector(".background-task", { timeout: 8000 });
    const aiPill = await aiPage.evaluate(() =>
      document.querySelector(".background-task")?.innerText.replace(/\s+/g, " ").trim() ?? "");
    check("AI 检索关闭后同样提示并可停止", aiPill.includes("AI 检索"), aiPill);
    await aiPage.locator(".background-task__action", { hasText: "停止" }).click();
    await aiPage.waitForFunction(() => !document.querySelector(".background-task"), null, { timeout: 8000 });
    check("停止 AI 检索后提示消失", await aiPage.evaluate(() => !document.querySelector(".background-task")), "");
    aiReleased?.();
    // 日常 AI 是跨页面共享的浏览器偏好，必须还原，否则会影响后面页面（AI 面板卡片混进 j/k 列表）
    await aiPage.getByRole("switch", { name: "日常 AI 检索" }).uncheck().catch(() => {});
    await aiPage.close();

    const taskMobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: "block" });
    const taskPhone = await taskMobile.newPage();
    await taskPhone.addInitScript(() => {
      window.auditAIAborts = [];
      const fetcher = window.fetch;
      window.fetch = (input, init) => {
        const url = new URL(String(input), location.href);
        if (url.pathname === "/api/ai-search" || url.pathname === "/api/summarize") {
          return new Promise((resolve, reject) => {
            init.signal.addEventListener("abort", () => {
              window.auditAIAborts.push(url.pathname);
              reject(init.signal.reason);
            }, { once: true });
          });
        }
        return fetcher(input, init);
      };
    });
    await taskPhone.goto(BASE + "/");
    await taskPhone.getByRole("switch", { name: "日常 AI 检索" }).check();
    await runSearch(taskPhone, firstQuery);
    const phoneAI = taskPhone.getByRole("group", { name: "AI 检索", exact: true });
    const phoneSummary = taskPhone.getByRole("group", { name: "AI 总结", exact: true });
    await phoneAI.getByRole("button", { name: "查看AI 检索" }).click();
    const phoneDrawer = taskPhone.getByRole("dialog", { name: "搜索工具" });
    await phoneDrawer.waitFor();
    check("窄屏查看后台 AI 检索打开抽屉并聚焦对应工具", await phoneDrawer
      .getByRole("button", { name: "AI 检索", exact: true }).evaluate(node => node === document.activeElement), "");
    await phoneDrawer.getByRole("button", { name: "AI 总结", exact: true }).click();
    await phoneDrawer.getByRole("button", { name: "生成总结" }).click();
    await phoneDrawer.getByRole("button", { name: "关闭", exact: true }).click();
    check("关闭移动抽屉后两项后台任务均可单独操作", await phoneAI.isVisible() && await phoneSummary.isVisible(), "");
    await phoneSummary.getByRole("button", { name: "停止AI 总结" }).click();
    await phoneSummary.waitFor({ state: "detached" });
    await taskPhone.locator(".workspace-nav").getByRole("button", { name: "AI", exact: true }).click();
    check("进入对话搜索时仍可停止后台 AI 检索", await phoneAI.isVisible(), "");
    await phoneAI.getByRole("button", { name: "停止AI 检索" }).click();
    await phoneAI.waitFor({ state: "detached" });
    check("分别停止时取消对应的 fetch 信号", await taskPhone.evaluate(() =>
      window.auditAIAborts.join(",") === "/api/summarize,/api/ai-search"), "");
    await taskMobile.close();

    // —— P1-14 设置页增强 ——
    const settingsPage = await desktop.newPage();
    await settingsPage.route("**/api/settings/models", route => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({ json: { revision: 0, assignments: {}, models: [
        { id: "audit-model", label: "审计模型", base_url: "http://127.0.0.1:11434/v1", model: "audit", features: [], has_key: false },
      ] } });
    });
    let modelTestBody;
    await settingsPage.route("**/api/settings/models/test", route => {
      modelTestBody = route.request().postDataJSON();
      return route.fulfill({ json: { ok: true, status: 200, models: 3, model: "audit", model_listed: false } });
    });
    await settingsPage.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    await settingsPage.waitForSelector("#engine-settings .engine-settings__filter", { timeout: 30000 });
    const beforeFilter = await settingsPage.locator("#engine-settings li").count();
    const engineSettingsFixture = await desktop.request.get(BASE + "/api/settings/engines").then(response => response.json());
    await settingsPage.fill(".engine-settings__filter", "!google");
    const bangFiltered = await settingsPage.locator("#engine-settings li").count();
    check("引擎筛选接受感叹号后缀和别名", bangFiltered > 0 && bangFiltered < beforeFilter, `${beforeFilter} → ${bangFiltered}`);
    await settingsPage.fill(".engine-settings__filter", "zzzz-no-match");
    const filtered = await settingsPage.evaluate(() => ({
      rows: document.querySelectorAll("#engine-settings li").length,
      hint: Array.from(document.querySelectorAll("#engine-settings [role=status]")).map(node => node.textContent).join(" "),
    }));
    check("引擎列表可按名称/后缀筛选", filtered.rows === 0 && filtered.hint.includes("没有匹配"),
      `${beforeFilter} → ${filtered.rows}`);
    await settingsPage.fill(".engine-settings__filter", "");
    await settingsPage.getByRole("button", { name: "刷新状态" }).click();
    await settingsPage.waitForSelector(".engine-settings__status", { timeout: 15000 });
    const probed = await settingsPage.evaluate(() => ({
      statuses: document.querySelectorAll(".engine-settings__status").length,
      notice: Array.from(document.querySelectorAll("#engine-settings [role=status]"))
        .map(node => node.textContent).join(" "),
    }));
    check("刷新状态贴出可用/冷却/未知", probed.statuses > 0 && /可用 \d+ · 冷却 \d+ · 未知 \d+/.test(probed.notice),
      `${probed.statuses} 个 · ${probed.notice.slice(0, 40)}`);
    await settingsPage.locator(".model-settings > summary").click();
    const testButton = settingsPage.getByRole("button", { name: "测试连接" });
    await testButton.click();
    await settingsPage.getByText("可用（3 个模型），列表未列出所填模型", { exact: true }).waitFor();
    const modelTest = await settingsPage.evaluate(() =>
      document.querySelector(".model-entry__test")?.textContent ?? "");
    check("模型测试绑定已保存版本并提示所填模型未列出", modelTest.includes("未列出") &&
      modelTestBody?.id === "audit-model" && modelTestBody?.revision === 0, modelTest);
    await settingsPage.getByLabel("API 基址").fill("http://127.0.0.1:11434/edited/v1");
    check("修改未保存的模型基址后清除旧结果并禁用测试", await testButton.isDisabled() &&
      await settingsPage.locator(".model-entry__test").count() === 0, "");
    const dataCard = await settingsPage.evaluate(() => {
      const card = document.querySelector('[aria-labelledby="data-settings"]');
      return {
        path: card?.querySelector("code")?.textContent ?? "",
        text: card?.innerText.replace(/\s+/g, " ") ?? "",
      };
    });
    check("数据管理显示本机库路径与书签数", /\.db$/.test(dataCard.path.trim()) && /书签 \d+ 条/.test(dataCard.text),
      dataCard.text.slice(0, 60));
    await settingsPage.evaluate(() => localStorage.setItem("cs-search-history", JSON.stringify([{ query: "audit", literal: true }])));
    await settingsPage.route("**/api/settings/engines", route => route.fulfill({ json: {
      preferences: { revision: 0, default_engines: ["g"], api_key: "audit-secret",
        custom: [{ code: "local", label: "自定义", kind: "website", target: "https://example.test/?key=audit-secret&q={q}" }] },
    } }));
    const download = settingsPage.waitForEvent("download", { timeout: 10000 });
    await settingsPage.getByRole("button", { name: "导出设置" }).click();
    const file = await download.catch(() => null);
    const exported = file ? fs.readFileSync(await file.path(), "utf8") : "{}";
    const settingsData = JSON.parse(exported);
    check("设置导出默认省略历史、密钥、绝对路径和网址模板", file?.suggestedFilename() === "cleansearch-settings.json" &&
      settingsData.engine_preferences?.custom?.[0]?.code === "local" && !exported.includes("audit-secret") &&
      !Object.hasOwn(settingsData.local ?? {}, "db_path") && !Object.hasOwn(settingsData, "search_history"), "");
    await settingsPage.getByRole("checkbox", { name: "在导出文件中包含搜索历史" }).check();
    const [withHistory] = await Promise.all([
      settingsPage.waitForEvent("download"), settingsPage.getByRole("button", { name: "导出设置" }).click(),
    ]);
    const optedIn = JSON.parse(fs.readFileSync(await withHistory.path(), "utf8"));
    check("显式勾选后导出搜索历史与字面模式", optedIn.search_history?.[0]?.query === "audit" &&
      optedIn.search_history?.[0]?.literal === true, "");
    const historyTab = await desktop.newPage();
    await historyTab.goto(BASE + "/bookmarks");
    await historyTab.evaluate(() => localStorage.setItem("cs-search-history", JSON.stringify([
      { query: "audit", literal: true }, { query: "other tab", literal: false },
    ])));
    await settingsPage.getByText(/搜索历史 2 条/).waitFor();
    check("设置页同步另一标签页的搜索历史计数", await settingsPage.getByText(/搜索历史 2 条/).isVisible(), "");
    await historyTab.close();
    await settingsPage.getByRole("button", { name: "清空搜索历史" }).click();
    const historyAfterClear = await settingsPage.evaluate(() => localStorage.getItem("cs-search-history"));
    check("清空搜索历史写入空列表", historyAfterClear === "[]", String(historyAfterClear));
    await settingsPage.close();
    // —— P1-15 旧页面移动端 ——
    const bmCtx = await browser.newContext({
      viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "zh-CN", serviceWorkers: "block",
    });
    const bmPhone = await bmCtx.newPage();
    await bmPhone.route("**/api/bookmarks?*", route => route.fulfill({ json: {
      items: [{ id: 1, url: "https://example.test/bookmark", title: "一个用于检查窄屏布局的书签标题",
        group_id: null, group_name: null, tags: [], created_at: 0, dead: 0 }],
      total: 1, groups: [{ id: 1, name: "一个用于检查下拉菜单宽度的长分组名称" }], tags: [], fts: false,
    } }));
    await bmPhone.goto(BASE + "/bookmarks", { waitUntil: "domcontentloaded" });
    await bmPhone.waitForSelector(".bm-card", { timeout: 40000 });
    const bmLayout = await bmPhone.evaluate(() => {
      const search = document.querySelector(".bm-search")?.getBoundingClientRect();
      const actions = document.querySelector(".bm-actions")?.getBoundingClientRect();
      const buttons = Array.from(document.querySelectorAll(".bm-actions > .button, .bm-actions > a"))
        .map(node => node.getBoundingClientRect());
      const add = document.querySelector(".bm-add-details");
      const card = document.querySelector(".bm-card");
      const title = card?.querySelector(".bm-card__title")?.getBoundingClientRect();
      const cardActions = card?.querySelector(".bm-card__actions")?.getBoundingClientRect();
      const cardBox = card?.getBoundingClientRect();
      return {
        searchY: search?.y ?? -1,
        actionsY: actions?.y ?? -1,
        buttonWidths: buttons.map(rect => Math.round(rect.width)),
        addOpen: !!add?.open,
        addFormVisible: (() => {
          const form = document.querySelector(".bm-add");
          if (!form) return false;
          return typeof form.checkVisibility === "function"
            ? form.checkVisibility({ contentVisibilityAuto: true }) : !!form.getClientRects().length;
        })(),
        titleBottom: title?.bottom ?? -1,
        actionsTop: cardActions?.top ?? -1,
        selectWidth: Math.round(card?.querySelector(".bm-card__actions select")?.getBoundingClientRect().width ?? 0),
        cardWidth: Math.round(cardBox?.width ?? 0),
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
      };
    });
    check("390 书签工具栏分成搜索与动作两行", bmLayout.actionsY > bmLayout.searchY + 8,
      `searchY=${Math.round(bmLayout.searchY)} actionsY=${Math.round(bmLayout.actionsY)}`);
    check("390 书签动作三等分", bmLayout.buttonWidths.length === 3 &&
      Math.max(...bmLayout.buttonWidths) - Math.min(...bmLayout.buttonWidths) <= 2,
      bmLayout.buttonWidths.join("/"));
    check("390 添加表单默认收起", !bmLayout.addOpen && !bmLayout.addFormVisible,
      `open=${bmLayout.addOpen} visible=${bmLayout.addFormVisible}`);
    await bmPhone.locator(".bm-add-details__summary").press("Enter");
    check("展开后可填写添加表单", await bmPhone.locator(".bm-add").isVisible(), "");
    check("390 卡片操作独占一行不挤压标题",
      bmLayout.actionsTop >= bmLayout.titleBottom - 1 && bmLayout.selectWidth <= bmLayout.cardWidth - 20,
      `titleBottom=${Math.round(bmLayout.titleBottom)} actionsTop=${Math.round(bmLayout.actionsTop)} select=${bmLayout.selectWidth}/${bmLayout.cardWidth}`);
    check("390 书签页无横向滚动", bmLayout.scrollW <= bmLayout.clientW + 1,
      `${bmLayout.scrollW}/${bmLayout.clientW}`);
    await bmPhone.setViewportSize({ width: 320, height: 720 });
    await bmPhone.reload({ waitUntil: "domcontentloaded" });
    await bmPhone.waitForSelector(".bm-card", { timeout: 40000 });
    const bm320 = await bmPhone.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }));
    check("320 书签页无横向滚动", bm320.scrollW <= bm320.clientW + 1, `${bm320.scrollW}/${bm320.clientW}`);
    const minTouch = await bmPhone.locator(".bm-actions > .button, .bm-card__actions select, .bm-card__remove, .bm-add-details__summary")
      .evaluateAll(nodes => Math.min(...nodes.map(node => node.getBoundingClientRect().height)));
    check("窄屏书签主要操作至少 44px 高", minTouch >= 44, `${minTouch}px`);
    await bmPhone.goto(BASE + "/bookmarks?url=https%3A%2F%2Fexample.test%2Fshared&title=Shared");
    const sharedField = bmPhone.getByLabel("新书签网址");
    await sharedField.waitFor();
    check("旧式 GET 分享在窄屏自动展开并清除地址栏参数", await sharedField.inputValue() === "https://example.test/shared" &&
      !new URL(bmPhone.url()).search, "");
    await bmCtx.close();

    const summaryPage = await desktop.newPage();
    let pageSummaryBody = null;
    let pageSummaryCalls = 0;
    await summaryPage.route("**/api/page/summarize", route => {
      pageSummaryCalls++;
      pageSummaryBody = route.request().postDataJSON();
      return route.fulfill({ json: {
        title: "示例页面", url: "https://example.test/doc", final_url: "https://example.test/doc",
        byline: null, published: null, word_count: 120, read_minutes: 1, extractor: "audit", truncated: false,
        summary: { one_liner: "示例结论", bullets: ["要点一"], caveats: [] },
        key_data: [], anchors: [], model: "audit",
      } });
    });
    await summaryPage.goto(BASE + "/s", { waitUntil: "domcontentloaded" });
    await summaryPage.waitForSelector(".page-summary__examples", { timeout: 20000 });
    const exampleCount = await summaryPage.locator(".page-summary__examples button").count();
    check("单页总结空态给出示例地址", exampleCount >= 3, `${exampleCount} 个`);
    await summaryPage.locator(".page-summary__examples button").first().press("Enter");
    await summaryPage.waitForSelector(".page-summary", { timeout: 15000 });
    const exampleState = await summaryPage.evaluate(() => ({
      input: document.querySelector('input[type="url"]')?.value ?? "",
    }));
    check("点示例会填入地址并开始总结",
      pageSummaryBody?.url === exampleState.input && /^https:\/\//.test(exampleState.input),
      `input=${exampleState.input} body=${pageSummaryBody?.url}`);
    check("从键盘启动示例后焦点留在网址输入框", await summaryPage.getByLabel("网页地址")
      .evaluate(node => node === document.activeElement), "");
    await summaryPage.reload();
    await summaryPage.waitForSelector(".page-summary");
    check("带网址打开单页总结时只发起一次请求", pageSummaryCalls === 2, `calls=${pageSummaryCalls}`);
    await summaryPage.close();
    // —— P2-1 Service Worker / P2-2 OpenSearch / P2-3 Manifest ——
    await auditPwa(browser);
    // —— P2-4/P2-6 分享文案与性能 ——
    const perfPage = await desktop.newPage();
    await perfPage.addInitScript(() => {
      // Exercise the fallback deterministically even where fetchLater is supported.
      Object.defineProperty(window, "fetchLater", { configurable: true, value: undefined });
      navigator.sendBeacon = () => false;
    });
    const perfChunks = [];
    perfPage.on("response", response => {
      const name = response.url().split("/").pop() ?? "";
      if (name.endsWith(".js")) perfChunks.push(name);
    });
    await perfPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "networkidle" });
    await perfPage.waitForSelector(".results-body", { timeout: 60000 });
    const perfState = await perfPage.evaluate(() => {
      const card = document.querySelector(".group__list > .card");
      return {
        contentVisibility: card ? getComputedStyle(card).contentVisibility : "none",
        containSize: card ? getComputedStyle(card).containIntrinsicSize : "",
      };
    });
    check("长列表卡片使用 content-visibility: auto",
      perfState.contentVisibility === "auto", `cv=${perfState.contentVisibility} size=${perfState.containSize}`);
    const performanceCard = perfPage.locator(".group__list > .card").first();
    await performanceCard.locator(".card__actions summary").click();
    check("结果卡菜单展开时移除裁剪约束", await performanceCard.evaluate(card =>
      getComputedStyle(card).contentVisibility === "visible"), "");
    check("首屏不加载设置页与书签页的分包",
      !perfChunks.some(name => /^SettingsPage-/.test(name)) &&
      !perfChunks.some(name => /^BookmarkPage-/.test(name)),
      perfChunks.filter(name => /Page-/.test(name)).join(",") || "无页面分包");
    await perfPage.getByRole("button", { name: "AI 总结", exact: true }).click();
    const postedVitals = perfPage.waitForResponse(response => new URL(response.url()).pathname === "/api/metrics/vitals" &&
      response.request().postDataJSON()?.search_ms !== undefined);
    await perfPage.evaluate(() => dispatchEvent(new PageTransitionEvent("pagehide")));
    const vitalsResponse = await postedVitals;
    const vitals = vitalsResponse.request().postDataJSON();
    check("浏览器指标回退上报耗时且不包含搜索参数", vitalsResponse.status() === 204 && vitals.path === "/" &&
      typeof vitals.search_ms === "number" && typeof vitals.panel_ms === "number" && typeof vitals.ttfb === "number", "");
    const lazyChunks = [];
    perfPage.on("response", response => lazyChunks.push(response.url().split("/").pop() ?? ""));
    await perfPage.goto(BASE + "/settings", { waitUntil: "networkidle" });
    await perfPage.waitForSelector(".settings-page", { timeout: 30000 });
    check("按需加载设置页分包", lazyChunks.some(name => /^SettingsPage-/.test(name)),
      lazyChunks.filter(name => /^Settings/.test(name)).join(",") || "未加载");
    await perfPage.close();
    // —— P2-7 搜索筛选 ——
    const filterPage = await desktop.newPage();
    const filterBodies = [];
    await filterPage.route("**/api/search", async route => {
      const body = route.request().postDataJSON();
      filterBodies.push(body);
      const { time_range, language, site, dedupe } = body.opts;
      const base = makeSearchFixture(body.q);
      const meta = { ...base.meta, filters: { time_range, language, site, dedupe } };
      if (site) {
        return route.fulfill({ json: { ...base, official: null, groups: { strong: [], related: [], weak: [] },
          meta: { ...meta, status: "empty", total: 0, official: 0 } } });
      }
      await route.fulfill({ json: { ...base, meta } });
    });
    await filterPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await filterPage.waitForSelector(".results-body", { timeout: 60000 });
    const filterState = await filterPage.evaluate(() => ({
      open: document.querySelector(".filters__body")?.matches(":popover-open"),
      summary: document.querySelector(".filters__toggle")?.textContent?.trim() ?? "",
      groups: document.querySelectorAll(".filters__group").length,
      selects: document.querySelectorAll(".filters__field select").length,
      site: !!document.querySelector(".filters__field input"),
    }));
    check("筛选条默认收起且控件齐全", !filterState.open && filterState.summary.includes("筛选") &&
      filterState.groups === 1 && filterState.selects === 2 && filterState.site,
      `open=${filterState.open} selects=${filterState.selects}`);
    const filtersTrigger = filterPage.locator(".filters__toggle");
    const filterPanel = filterPage.locator(".filters__body");
    await filtersTrigger.click();
    await filterPage.locator(".filters__field input").focus();
    await filterPage.keyboard.press("Escape");
    await filterPanel.waitFor({ state: "hidden" });
    check("Esc 收起筛选并归还焦点", await filtersTrigger.evaluate(node => node === document.activeElement), "");
    await filtersTrigger.click();
    await filterPage.locator(".workspace-results").click({ position: { x: 3, y: 3 } });
    await filterPanel.waitFor({ state: "hidden" });
    check("点击外部收起筛选", await filterPanel.isHidden(), "");
    await filtersTrigger.click();
    filterBodies.length = 0;
    await filterPage.getByRole("button", { name: "一周内" }).click();
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("range") === "week", null, { timeout: 20000 });
    await filterPage.waitForSelector(READY);
    const weekBody = filterBodies.at(-1);
    check("时间范围写入请求与地址栏", weekBody?.opts?.time_range === "week" && weekBody?.page === 1,
      `opts=${JSON.stringify(weekBody?.opts ?? {})}`);
    const noteText = await filterPage.locator(".workspace-filter-note").innerText();
    check("筛选摘要显示已选条件与数量", noteText.includes("一周内") &&
      (await filterPage.locator(".filters__badge").innerText()) === "1", noteText);

    await filterPage.goBack();
    await filterPage.waitForFunction(() => !document.querySelector(".workspace-filter-note") && !new URLSearchParams(location.search).has("range"));
    await filterPage.waitForSelector(".results-body:not([aria-busy=true])");
    check("仅筛选改变的历史后退也重新查询", filterBodies.at(-1)?.opts?.time_range === null && await filterPanel.isHidden(), "");
    await filterPage.locator(".pager").first().getByRole("button", { name: "下一页" }).click();
    await filterPage.waitForSelector(".results-body:not([aria-busy=true])");
    check("历史后退后翻页不写回旧筛选", filterBodies.at(-1)?.page === 2 &&
      !new URL(filterPage.url()).searchParams.has("range"), "");
    await filterPage.goBack();
    await filterPage.waitForSelector(".results-body:not([aria-busy=true])");
    await filtersTrigger.click();
    await filterPage.getByRole("button", { name: "一周内" }).click();

    const siteInput = filterPage.getByLabel("站点限定");
    await siteInput.fill("not a domain");
    const beforeInvalid = filterBodies.length;
    await siteInput.press("Enter");
    await filterPage.getByText("请输入域名，例如 example.com", { exact: true }).waitFor();
    check("无效站点保留已生效的筛选且不发请求", filterBodies.length === beforeInvalid &&
      !new URL(filterPage.url()).searchParams.has("site"), "");

    filterBodies.length = 0;
    await filterPage.fill(".filters__field input", "example.com");
    await filterPage.press(".filters__field input", "Enter");
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("site") === "example.com", null, { timeout: 20000 });
    check("站点限定写入请求与地址栏", filterBodies.at(-1)?.opts?.site === "example.com",
      `opts=${JSON.stringify(filterBodies.at(-1)?.opts ?? {})}`);
    filterBodies.length = 0;
    await filterPage.selectOption(".filters__field select >> nth=1", "strict");
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("dedupe") === "strict", null, { timeout: 20000 });
    check("去重强度写入请求与地址栏", filterBodies.at(-1)?.opts?.dedupe === "strict",
      `opts=${JSON.stringify(filterBodies.at(-1)?.opts ?? {})}`);

    await filterPage.reload({ waitUntil: "domcontentloaded" });
    await filterPage.waitForSelector(".state--empty", { timeout: 60000 });
    const restored = await filterPage.evaluate(() => ({
      badge: document.querySelector(".filters__badge")?.textContent ?? "",
      note: document.querySelector(".workspace-filter-note")?.textContent ?? "",
      url: location.search,
    }));
    check("刷新后筛选从地址栏还原", restored.badge === "3" && restored.note.includes("site:example.com") &&
      restored.note.includes("严格去重"), `badge=${restored.badge} note=${restored.note.slice(0, 40)}`);
    filterBodies.length = 0;
    await filtersTrigger.click();
    await filterPage.getByRole("button", { name: "重置筛选" }).click();
    await filterPage.waitForFunction(() => {
      const params = new URLSearchParams(location.search);
      return !params.get("range") && !params.get("site") && !params.get("dedupe");
    }, null, { timeout: 20000 });
    const resetBody = filterBodies.at(-1);
    check("重置筛选清空地址栏与请求条件",
      !resetBody?.opts?.time_range && !resetBody?.opts?.site && resetBody?.opts?.dedupe === "normal",
      `opts=${JSON.stringify(resetBody?.opts ?? {})}`);

    // 时间范围连改两档后回退：地址栏、界面徽标、请求体三处都要回到上一档
    filterBodies.length = 0;
    await filterPage.getByRole("button", { name: "一周内" }).click();
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("range") === "week", null, { timeout: 20000 });
    await filterPage.waitForSelector(READY);
    await filterPage.getByRole("button", { name: "一天内" }).click();
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("range") === "day", null, { timeout: 20000 });
    await filterPage.waitForSelector(".results-body:not([aria-busy=true])");
    const dayBody = filterBodies.at(-1);
    await filterPage.goBack();
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("range") === "week", null, { timeout: 20000 });
    await filterPage.waitForSelector(".results-body:not([aria-busy=true])");
    const weekAgainBody = filterBodies.at(-1);
    check("时间范围连改两档后回退还原上一档筛选", dayBody?.opts?.time_range === "day" &&
      weekAgainBody?.opts?.time_range === "week" &&
      (await filterPage.locator(".filters__badge").innerText()) === "1" &&
      (await filterPage.locator(".workspace-filter-note").innerText()).includes("一周内"),
      `day=${dayBody?.opts?.time_range} back=${weekAgainBody?.opts?.time_range}`);

    // 站点限定回退：输入框草稿、徽标与请求体同步
    await filtersTrigger.click();
    await filterPage.fill(".filters__field input", "example.com");
    await filterPage.press(".filters__field input", "Enter");
    await filterPage.waitForFunction(() => new URLSearchParams(location.search).get("site") === "example.com", null, { timeout: 20000 });
    await filterPage.waitForSelector(READY);
    await filterPage.goBack();
    await filterPage.waitForFunction(() => !new URLSearchParams(location.search).has("site"), null, { timeout: 20000 });
    await filterPage.waitForSelector(READY);
    const afterSiteBack = await filterPage.evaluate(() => ({
      site: document.querySelector(".filters__field input")?.value ?? null,
      badge: document.querySelector(".filters__badge")?.textContent ?? "",
      note: document.querySelector(".workspace-filter-note")?.textContent ?? "",
    }));
    const siteBackBody = filterBodies.at(-1);
    check("回退清掉站点限定后输入框与请求同步", afterSiteBack.site === "" && afterSiteBack.badge === "1" &&
      !afterSiteBack.note.includes("site:") && siteBackBody?.opts?.site === null && siteBackBody?.opts?.time_range === "week",
      `site=${JSON.stringify(afterSiteBack.site)} badge=${afterSiteBack.badge} opts=${JSON.stringify(siteBackBody?.opts ?? {})}`);

    // 路由与查询变化时也要收起，不能只靠点外部和 Esc
    await filtersTrigger.click();
    await filterPage.locator(".workspace-nav__item", { hasText: "视频" }).click();
    await filterPanel.waitFor({ state: "hidden" });
    check("切换分类后筛选面板收起", await filterPanel.isHidden() &&
      filterPage.url().includes("category=video"), filterPage.url());
    await filterPage.locator(".workspace-nav__item", { hasText: "首页" }).click();
    await filterPage.waitForSelector(READY);
    await filtersTrigger.click();
    await filterPage.fill('input[name="q"]', "python typing 泛型");
    await filterPage.press('input[name="q"]', "Enter");
    await filterPanel.waitFor({ state: "hidden" });
    // 新查询沿用当前筛选（P0-1 契约），但面板必须收起
    check("提交新查询后筛选面板收起且沿用当前筛选", await filterPanel.isHidden() &&
      new URL(filterPage.url()).searchParams.get("range") === "week", filterPage.url());
    let echoMismatch = true;
    await filterPage.route("**/api/search", async route => {
      if (!echoMismatch) return route.fallback();
      const base = makeSearchFixture(firstQuery);
      await route.fulfill({ json: { ...base, meta: { ...base.meta, filters: {
        time_range: "day", language: null, site: null, dedupe: "normal",
      } } } });
    });
    await filterPage.reload({ waitUntil: "domcontentloaded" });
    await filterPage.waitForSelector(".state--error");
    check("筛选回显和请求不符时保留链接并提示恢复", new URL(filterPage.url()).searchParams.get("range") === "week" &&
      (await filterPage.locator(".workspace-filter-note").innerText()).startsWith("筛选条件："), "");
    echoMismatch = false;
    await filterPage.locator(".state--error").getByRole("button", { name: "重置筛选" }).click();
    await filterPage.waitForSelector(".results-body");
    await filterPage.close();

    // 矮视口：面板必须整体在视口内，超出部分靠内部滚动
    for (const { width, height, fallback } of [
      { width: 1280, height: 280 }, { width: 1280, height: 480 }, { width: 768, height: 561 },
      { width: 768, height: 561, fallback: true },
    ]) {
      const shortPage = await browser.newPage({ viewport: { width, height }, serviceWorkers: "block" });
      if (fallback) await shortPage.addInitScript(() => { delete HTMLElement.prototype.showPopover; });
      await shortPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
      const trigger = shortPage.locator(".filters__toggle");
      const panel = shortPage.locator(".filters__body");
      await trigger.click();
      const box = await panel.boundingBox();
      const scroll = await panel.evaluate(node => {
        node.scrollTop = node.scrollHeight;
        return node.scrollTop;
      });
      check(`${width}×${height} 筛选面板完整${fallback ? "（无原生 popover）" : ""}`,
        box && box.y >= 0 && box.y + box.height <= height && box.x >= 0 && box.x + box.width <= width &&
        (height !== 280 || scroll > 0), `box=${JSON.stringify(box)} scrollTop=${scroll}`);
      if (fallback) {
        const site = panel.getByLabel("站点限定");
        await site.fill("draft.example");
        await trigger.click();
        await trigger.click();
        check("无原生 popover 时再次开关清除未应用草稿", (await site.inputValue()) === "", "");
        await site.focus();
        await shortPage.keyboard.press("Escape");
        check("无原生 popover 时 Esc 关闭并归还焦点",
          await panel.isHidden() && await trigger.evaluate(node => node === document.activeElement), "");
      }
      await shortPage.close();
    }

    // —— P0-3 契约版本与混版提示 ——
    const health = await desktop.request.get(BASE + "/api/health").then(response => response.json());
    const required = ["filters", "bookmark_status", "vitals", "model_test", "opensearch"];
    check("health 报告契约版本与能力表", health.api_version >= 2 && !!health.db_path &&
      required.every(name => health.capabilities?.[name] === true),
      `api_version=${health.api_version} capabilities=${JSON.stringify(health.capabilities)}`);
    const opensearch = await desktop.request.get(BASE + "/opensearch.xml");
    check("OpenSearch 描述符返回 XML MIME",
      (opensearch.headers()["content-type"] ?? "").includes("opensearchdescription+xml"),
      opensearch.headers()["content-type"] ?? "");

    const freshPage = await desktop.newPage();
    await freshPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await freshPage.waitForSelector(".results-body", { timeout: 60000 });
    check("新版后端不显示混版横幅且筛选可用",
      await freshPage.locator(".server-banner").count() === 0 &&
      !(await freshPage.locator(".filters__toggle").isDisabled()), "");
    await freshPage.close();

    // 旧后端：health 缺 api_version/capabilities，相关接口 404/405
    const legacyPage = await desktop.newPage();
    await legacyPage.addInitScript(() => { window.fetchLater = undefined; });
    const legacyCalls = { health: 0, status: 0, vitals: 0 };
    let resolveHealth;
    const delayedHealth = new Promise(resolve => { resolveHealth = resolve; });
    await legacyPage.route("**/api/health", async route => {
      legacyCalls.health++;
      await delayedHealth;
      await route.fulfill({ json: { status: "ok", provider: "fixture", api_version: 1, capabilities: { vitals: true } } });
    });
    await legacyPage.route("**/api/search", route => {
      const base = makeSearchFixture(firstQuery);
      return route.fulfill({ json: { ...base, meta: { ...base.meta, filters: undefined } } });
    });
    await legacyPage.route("**/api/bookmarks/status**", route => {
      legacyCalls.status++;
      return route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "not found", retryable: false } } });
    });
    await legacyPage.route("**/api/metrics/vitals", route => {
      legacyCalls.vitals++;
      return route.fulfill({ status: 405, body: "" });
    });
    await legacyPage.route("**/api/settings/models", route => route.request().method() === "GET"
      ? route.fulfill({ json: { revision: 0, assignments: {}, models: [
        { id: "audit-model", label: "审计模型", base_url: "http://127.0.0.1:11434/v1", model: "audit", features: [], has_key: false },
      ] } })
      : route.continue());
    await legacyPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await legacyPage.waitForSelector(".results-body");
    await legacyPage.evaluate(() => dispatchEvent(new PageTransitionEvent("pagehide")));
    check("能力探测等待中禁用筛选入口", await legacyPage.locator(".filters__toggle").isDisabled(), "");
    resolveHealth();
    await legacyPage.waitForSelector(".server-banner", { timeout: 60000 });
    const legacyBanner = await legacyPage.locator(".server-banner").innerText();
    check("旧后端显示版本过旧横幅并列出缺失能力", legacyBanner.includes("版本过旧") &&
      legacyBanner.includes("搜索筛选") && legacyBanner.includes("批量收藏状态"),
      legacyBanner.replace(/\s+/g, " ").slice(0, 60));
    check("旧后端禁用筛选入口且点不开面板",
      await legacyPage.locator(".filters__toggle").isDisabled() &&
      await legacyPage.locator(".filters__body").isHidden(), "");
    const legacyShot = path.join(OUT, "legacy-banner.png");
    await legacyPage.screenshot({ path: legacyShot });
    report.screenshots.push(path.relative(ROOT, legacyShot));
    await legacyPage.waitForSelector(".results-body", { timeout: 60000 });
    await legacyPage.evaluate(() => dispatchEvent(new PageTransitionEvent("pagehide")));
    await legacyPage.waitForTimeout(300);
    check("探测与旧后端均无未确认的收藏状态和性能请求",
      legacyCalls.health === 1 && legacyCalls.status === 0 && legacyCalls.vitals === 0, JSON.stringify(legacyCalls));
    await legacyPage.goto(BASE + "/?range=week&q=" + encodeURIComponent(firstQuery));
    await legacyPage.waitForSelector(".state--error");
    check("旧后端不会把分享链接的筛选标成已生效",
      (await legacyPage.locator(".workspace-filter-note").innerText()).startsWith("筛选条件："), "");
    await legacyPage.locator(".state--error").getByRole("button", { name: "重置筛选" }).click();
    await legacyPage.waitForSelector(".results-body");
    check("旧后端可从分享链接移除不支持的筛选并恢复结果",
      !new URL(legacyPage.url()).searchParams.has("range") && await legacyPage.locator(".workspace-filter-note").count() === 0, "");
    await legacyPage.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    await legacyPage.waitForSelector(".settings-page", { timeout: 30000 });
    await legacyPage.locator(".model-settings > summary").click();
    const legacyTestButton = legacyPage.getByRole("button", { name: "测试连接" }).first();
    check("旧后端禁用模型连通性测试", await legacyTestButton.isDisabled() &&
      (await legacyPage.getByText("本机服务版本过旧，重启服务后可用连通性测试。").count()) === 1, "");
    await legacyPage.close();
    for (const width of [320, 390, 768]) {
      const narrow = await browser.newPage({ viewport: { width, height: 760 }, isMobile: true, hasTouch: true, serviceWorkers: "block" });
      await narrow.goto(BASE + "/?lang=pt-BR");
      await narrow.locator(".filters__toggle").click();
      const bounds = await narrow.locator(".filters__body").boundingBox();
      check(`${width}px 筛选面板完整且保留分享的语言代码`, bounds && bounds.x >= 0 && bounds.y >= 0 &&
        bounds.x + bounds.width <= width && bounds.y + bounds.height <= 760 &&
        await narrow.locator(".filters__body").getByLabel("语言").inputValue() === "pt-BR", "");
      await narrow.close();
    }
    // —— P1-2 加载骨架与翻页保留旧列表 ——
    const slow = await desktop.newPage();
    await slow.emulateMedia({ reducedMotion: "reduce" });
    let releaseRequest;
    const requests = [];
    let pageTwo;
    let pageThreeAttempts = 0;
    await slow.route("**/api/search", async route => {
      const { page: number } = route.request().postDataJSON();
      requests.push(number);
      await new Promise(resolve => { releaseRequest = resolve; });
      if (number === 2) return route.fulfill({ json: pageTwo });
      if (number === 3) {
        if (pageThreeAttempts++ === 0) {
          return route.fulfill({ status: 503, json: { error: { code: "UPSTREAM_UNAVAILABLE", message: "固定失败" } } });
        }
        return route.fulfill({ json: {
          ...pageTwo, groups: { strong: [], related: [], weak: [] }, official: undefined,
          meta: { ...pageTwo.meta, status: "empty", total: 0, official: 0 },
        } });
      }
      await route.continue();
    });
    await slow.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    const initialResponse = slow.waitForResponse(response => new URL(response.url()).pathname === "/api/search");
    // 搜索框现在是 role=combobox（自动完成），不再走隐式 searchbox 角色
    const slowInput = slow.locator('input[name="q"]');
    await slowInput.fill(firstQuery);
    await slowInput.press("Enter");
    await slow.waitForSelector(".skeleton", { timeout: 8000 });
    const skeleton = await slow.evaluate(() => ({
      cards: document.querySelectorAll(".skeleton__card").length,
      status: document.querySelector(".skeleton__status")?.textContent ?? "",
      height: document.querySelector(".skeleton__cards")?.getBoundingClientRect().height ?? 0,
      cardsHidden: document.querySelector(".skeleton__cards")?.getAttribute("aria-hidden") === "true",
      animation: getComputedStyle(document.querySelector(".skeleton__row")).animationName,
      announcement: document.querySelector('main > [role="status"]').textContent,
      timerHidden: document.querySelector(".skeleton__status").getAttribute("aria-hidden") === "true",
    }));
    check("新查询渲染 3 张骨架卡", skeleton.cards === 3 && skeleton.cardsHidden,
      `cards=${skeleton.cards} ariaHidden=${skeleton.cardsHidden}`);
    check("骨架显示已用时间", /正在检索/.test(skeleton.status) && /\d\.\ds/.test(skeleton.status), skeleton.status);
    const ticker = slow.locator(".skeleton__status");
    await slow.waitForFunction(() => Number(document.querySelector(".skeleton__status")?.textContent.match(/(\d+\.\d)s$/)?.[1]) > 0.2);
    const ticking = await ticker.innerText();
    check("骨架计时在走（>0.2s）", Number((/(\d+\.\d)s/.exec(ticking) || [0, "0"])[1]) > 0.2, ticking);
    check("骨架撑住结果区高度（≥280px）", skeleton.height >= 280, `h=${Math.round(skeleton.height)}`);
    check("减少动态效果时骨架停止动画", skeleton.animation === "none", skeleton.animation);
    check("骨架计时仅用于视觉，主状态区播报查询", skeleton.timerHidden && skeleton.announcement.includes(firstQuery),
      skeleton.announcement);
    releaseRequest();
    pageTwo = await (await initialResponse).json();
    pageTwo.meta.sid = "audit-page-2";
    await slow.waitForSelector(READY, { timeout: 30000 });
    check("结果到达后骨架移除", await slow.locator(".skeleton").count() === 0, "");

    const slowNext = slow.getByRole("button", { name: "下一页" }).first();
    const nextRequest = slow.waitForRequest(request => request.postDataJSON()?.page === 2);
    await slowNext.press("Enter");
    await nextRequest;
    const oldResults = slow.locator('.results-body[aria-busy="true"]');
    await oldResults.waitFor({ timeout: 8000 });
    const stale = await oldResults.evaluate(body => ({
      cards: body.querySelectorAll("[id^='result-']").length,
      opacity: Number(getComputedStyle(body).opacity),
      label: body.querySelector(".pager__label").textContent,
      progress: document.querySelector(".results-progress")?.textContent ?? "",
      announcement: document.querySelector('main > [role="status"]').textContent,
      focused: document.activeElement === body.parentElement,
    }));
    check("翻页时保留旧列表并降透明", stale.cards > 0 && stale.opacity === 0.45,
      `cards=${stale.cards} opacity=${stale.opacity}`);
    check("旧列表保留原页码，新页码单独显示并播报",
      String(stale.label).startsWith("第 1 页") && stale.progress.includes("正在加载第 2 页") && stale.announcement === "正在加载第 2 页",
      `${stale.label} · ${stale.progress}`);
    await oldResults.locator(".pager button").last().evaluate(button => button.focus());
    await slow.keyboard.press("j");
    await slow.keyboard.press("Enter");
    const staleFocus = await oldResults.evaluate(body => ({
      inert: body.inert,
      parentFocused: document.activeElement === body.parentElement,
      active: document.activeElement?.className || document.activeElement?.tagName || "",
    }));
    check("翻页期间旧列表跳过键盘焦点与快捷键", stale.focused && staleFocus.inert && staleFocus.parentFocused &&
      requests.join(",") === "1,2",
      `requests=${requests} focused=${stale.focused} inert=${staleFocus.inert} parentFocused=${staleFocus.parentFocused} active=${staleFocus.active}`);
    releaseRequest();
    await slow.waitForSelector(READY, { timeout: 30000 });
    const loaded = await slow.locator(".results-body").evaluate(body => ({
      opacity: Number(getComputedStyle(body).opacity),
      focused: document.activeElement?.textContent,
      sid: body.querySelector(".metabar__sid").textContent,
    }));
    check("翻页成功恢复不透明并聚焦新页码", loaded.opacity === 1 && String(loaded.focused).startsWith("第 2 页") &&
      loaded.sid.includes("audit-page-2"), `opacity=${loaded.opacity} focus=${loaded.focused}`);

    const failingRequest = slow.waitForRequest(request => request.postDataJSON()?.page === 3);
    await slowNext.press("Enter");
    await failingRequest;
    await oldResults.waitFor();
    releaseRequest();
    const retry = slow.getByRole("button", { name: "重试" });
    await retry.waitFor();
    check("翻页失败移除旧列表并聚焦重试", await oldResults.count() === 0 &&
      await retry.evaluate(node => node === document.activeElement), "");
    const retryRequest = slow.waitForRequest(request => request.postDataJSON()?.page === 3);
    await retry.press("Enter");
    await retryRequest;
    await slow.locator(".skeleton").waitFor();
    releaseRequest();
    await slow.locator(".state--empty").waitFor();
    check("翻页返回空结果时显示空态和当前页码", await oldResults.count() === 0 &&
      (await slow.locator(".pager__label").first().innerText()).startsWith("第 3 页"), `requests=${requests}`);
    await slow.close();

    // —— 引擎菜单：外部点击关闭 + 分组正确 ——
    await page.evaluate(() => window.scrollTo(0, 0));
    const engineSummary = page.locator(".workspace-engines > summary").first();
    await engineSummary.click();
    const opened = await page.evaluate(() => document.querySelector(".workspace-engines")?.open === true);
    await page.locator(".workspace-nav").click({ position: { x: 6, y: 6 } });
    const closedByOutside = await page.evaluate(() => document.querySelector(".workspace-engines")?.open === false);
    check("引擎菜单点外部即关闭", opened && closedByOutside, `open=${opened} closed=${closedByOutside}`);

    await engineSummary.click();
    const more = page.locator(".engines__more").first();
    if (await more.count()) await more.click();
    const groups = await page.evaluate(() => Array.from(document.querySelectorAll(".engines__section")).map(section => ({
      title: section.getAttribute("aria-label") || (section.querySelector(".engines__heading")?.textContent ?? ""),
      codes: Array.from(section.querySelectorAll(".engines__code")).map(node => node.textContent),
      labels: Array.from(section.querySelectorAll(".engines__chip")).map(node => node.textContent),
      status: Array.from(section.querySelectorAll(".engines__status")).map(node => node.textContent),
    })));
    const mainland = groups.find(group => group.title.includes("中国大陆"));
    const others = groups.find(group => group.title === "其他引擎");
    check("Google 不在「中国大陆可直连」分组",
      !!mainland && !mainland.codes.includes("g") && !mainland.labels.some(label => label.startsWith("Google")),
      mainland ? mainland.codes.join(",") : "缺少大陆分组");
    check("未分组引擎有「其他引擎」标题", !!others, others ? others.codes.slice(0, 5).join(",") : "缺少其他引擎分组");
    check("引擎状态是文字标签", !!others && others.status.every(text => /可用|冷却|未知|直达|地区|不可用/.test(text)),
      others ? [...new Set(others.status)].join("/") : "无状态标签");
    await page.keyboard.press("Escape");

    await page.getByRole("navigation", { name: "搜索分类" }).getByRole("button", { name: "AI", exact: true }).click();
    check("AI 对话页只保留一个主标题且更新标签页标题",
      await page.locator("h1").count() === 1 && (await page.title()).startsWith("AI 对话搜索"), "");
    await page.goBack();

    const tools = page.getByRole("group", { name: "AI 与翻译工具" });
    const translation = tools.getByRole("button", { name: "翻译" });
    await translation.focus();
    await page.keyboard.press("Enter");
    const expanded = await translation.getAttribute("aria-expanded");
    await page.keyboard.press("Space");
    check("键盘可展开和收起工具面板",
      expanded === "true" && await translation.getAttribute("aria-expanded") === "false", "");

    const historyPage = await desktop.newPage();
    let aiRequests = 0;
    await historyPage.route("**/api/ai-search", route => {
      aiRequests++;
      return route.fulfill({ json: { provider: "audit-stub", results: [] } });
    });
    await historyPage.goto(BASE + "/");
    await historyPage.getByRole("switch", { name: "日常 AI 检索" }).check();
    try {
      await runSearch(historyPage, firstQuery);
      await historyPage.getByText("audit-stub", { exact: true }).waitFor();
      await historyPage.goBack();
      check("后退至空首页清空 AI 检索结果",
        await historyPage.locator(".ai-search").count() === 0 && (await historyPage.title()) === "CleanSearch", "");
      await historyPage.goForward();
      await historyPage.waitForSelector(READY);
      check("前进恢复普通结果时不重发 AI 检索", aiRequests === 1, `requests=${aiRequests}`);

      // 一次历史导航同时跨查询和筛选，不能沿用被离开的查询的 AI 结果。
      await historyPage.locator(".filters__toggle").click();
      await historyPage.getByRole("button", { name: "一周内" }).click();
      await historyPage.waitForSelector(READY);
      await runSearch(historyPage, "python asyncio");
      await historyPage.getByText("audit-stub", { exact: true }).waitFor();
      await historyPage.evaluate(() => history.go(-2));
      await historyPage.waitForURL(url => url.searchParams.get("q") === firstQuery && !url.searchParams.has("range"));
      await historyPage.waitForSelector(READY);
      check("历史一次还原查询和筛选时清除离开页面的 AI 检索", aiRequests === 2 &&
        await historyPage.locator(".ai-search").count() === 0, `requests=${aiRequests}`);
    } finally {
      await historyPage.getByRole("switch", { name: "日常 AI 检索" }).uncheck();
      await historyPage.close();
    }

    // —— 设置页：继承默认时开关必须「看得出来是禁用的」 ——
    await page.route("**/api/settings/engines", route => route.fulfill({ json: engineSettingsFixture }));
    await page.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#engine-settings [role=\"switch\"]", { timeout: 20000 });
    const engineState = await page.evaluate(() => {
      const panel = document.querySelector("#engine-settings");
      const switches = Array.from(panel.querySelectorAll('[role="switch"]'));
      const mode = switches.find(node => (node.getAttribute("aria-label") || "").includes("使用自选默认引擎"));
      const inheriting = !!mode && !mode.checked;
      const rows = switches.filter(node => node !== mode);
      const disabled = rows.filter(node => node.disabled);
      const opacity = disabled.length ? Number(getComputedStyle(disabled[0]).opacity) : 1;
      return {
        inheriting,
        rows: rows.length,
        disabled: disabled.length,
        checkedDisabled: disabled.filter(node => node.checked).length,
        opacity,
        described: disabled.filter(node => node.getAttribute("aria-describedby")).length,
        note: panel.querySelector(".engine-settings__inherit")?.textContent ?? "",
        reset: Array.from(panel.querySelectorAll("button")).some(node => node.textContent.includes("恢复默认")),
      };
    });
    if (engineState.inheriting) {
      check("继承默认时有说明文案", engineState.note.includes("继承 SearXNG 默认"), engineState.note.trim().slice(0, 40));
      check("继承默认时逐项开关禁用且不显示为已选",
        engineState.disabled === engineState.rows && engineState.checkedDisabled === 0,
        `disabled=${engineState.disabled}/${engineState.rows} checkedDisabled=${engineState.checkedDisabled}`);
      check("禁用开关视觉降透明（≠1）", engineState.opacity < 1, `opacity=${engineState.opacity}`);
      check("禁用原因可被读屏（aria-describedby）", engineState.described === engineState.disabled,
        `described=${engineState.described}/${engineState.disabled}`);
      check("提供「恢复默认」入口", engineState.reset, `reset=${engineState.reset}`);
    } else {
      check("引擎开关继承态检查", true, "跳过：当前是自选默认模式，开关本就可用");
    }
    await axeScan(page, "设置页");

    for (const [route, label] of [["/bookmarks", "书签"], ["/tools", "一键添加"], ["/s", "单页总结"], ["/settings", "设置"]]) {
      await page.goto(BASE + route, { waitUntil: "domcontentloaded" });
      await page.waitForSelector("main#main", { timeout: 20000 });
      const metrics = await page.evaluate(() => {
        const brand = document.querySelector(".workspace-brand__mark")?.getBoundingClientRect();
        const main = document.querySelector("main#main");
        const mainBox = main?.getBoundingClientRect();
        const padLeft = main ? parseFloat(getComputedStyle(main).paddingLeft) : 0;
        const current = document.querySelectorAll('[aria-current="page"]');
        return {
          brandX: brand ? brand.x : null,
          // 正文左边缘 = 内容盒起点，不是含 padding 的外框
          mainX: mainBox ? mainBox.x + padLeft : null,
          current: current.length,
          h1: document.querySelectorAll("h1").length,
        };
      });
      check(`${label}页 header 与正文左边缘对齐`,
        metrics.brandX !== null && metrics.mainX !== null && Math.abs(metrics.brandX - metrics.mainX) <= 1,
        `brand=${metrics.brandX} main=${metrics.mainX}`);
      check(`${label}页只有一个当前导航项`, metrics.current === 1, `current=${metrics.current}`);
      check(`${label}页有 h1`, metrics.h1 === 1, `h1=${metrics.h1}`);
    }

    // 工具页代码块 320px 不横向溢出
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(BASE + "/tools", { waitUntil: "domcontentloaded" });
    const viewCode = page.getByText("查看书签代码", { exact: true });
    await viewCode.waitFor();
    check("令牌和含令牌的书签代码默认收起",
      !(await page.locator(".tools__code").isVisible()) && (await page.locator(".tools__token code").innerText()).includes("•"), "");
    await viewCode.click();
    await page.waitForSelector(".tools__code", { timeout: 20000 });
    const overflow = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
      preW: document.querySelector(".tools__code")?.scrollWidth ?? 0,
      preClientW: document.querySelector(".tools__code")?.clientWidth ?? 0,
    }));
    check("工具页 320px 无横向滚动", overflow.scrollW <= overflow.clientW + 1,
      `page=${overflow.scrollW}/${overflow.clientW} pre=${overflow.preW}/${overflow.preClientW}`);
    check("工具页代码块自身可换行", overflow.preW <= overflow.preClientW + 1,
      `pre=${overflow.preW}/${overflow.preClientW}`);

    // 320 窄屏：首条结果的标题与摘要首行都要露出来
    const tiny = await browser.newPage({ viewport: { width: 320, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: "block" });
    await tiny.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await tiny.waitForSelector(".results-body", { timeout: 60000 });
    const tinyFirst = await tiny.evaluate(() => {
      const card = document.querySelector(".group__list > .card");
      const title = card?.querySelector(".card__title");
      const snippet = card?.querySelector(".card__snippet");
      return {
        titleY: title ? Math.round(title.getBoundingClientRect().y) : null,
        snippetY: snippet ? Math.round(snippet.getBoundingClientRect().y) : null,
        officialItems: document.querySelectorAll(".official__item").length,
      };
    });
    check("320 首屏露出首条标题与摘要首行", tinyFirst.titleY !== null && tinyFirst.titleY <= 700 &&
      tinyFirst.snippetY !== null && tinyFirst.snippetY < 844, JSON.stringify(tinyFirst));
    await tiny.close();

    // —— 空首页：最近搜索 / 示例 / 快捷入口 ——
    const homeContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: "block" });
    const home = await homeContext.newPage();
    await home.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await home.waitForSelector(".empty-home", { timeout: 30000 });
    const homeText = await home.locator(".empty-home").innerText();
    check("空首页给出示例与快捷入口", homeText.includes("试试这些") && homeText.includes("书签") &&
      homeText.includes("单页总结") && homeText.includes("AI 对话") && homeText.includes("快捷键"),
      homeText.replace(/\s+/g, " ").slice(0, 60));
    check("无历史时不显示最近搜索", await home.locator(".empty-home__chip").count() === 0, "");
    await searchWithResults(home);
    await home.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await home.waitForSelector(".empty-home__chip", { timeout: 30000 });
    check("搜索后空首页出现最近搜索",
      (await home.locator(".empty-home__title", { hasText: "最近搜索" }).count()) === 1 &&
      await home.locator(".empty-home__chip").count() >= 1, `${await home.locator(".empty-home__chip").count()} 条`);
    const historyCount = await home.locator(".empty-home__chip").count();
    await home.locator(".empty-home__remove").first().press("Enter");
    check("最近搜索支持单条删除", await home.locator(".empty-home__chip").count() === historyCount - 1,
      `${historyCount} → ${await home.locator(".empty-home__chip").count()}`);
    check("删除最后一条历史后焦点移到示例",
      await home.locator(".empty-home__examples button").first().evaluate(node => node === document.activeElement), "");
    const historyWriter = await homeContext.newPage();
    await historyWriter.goto(BASE + "/");
    await historyWriter.evaluate(() => localStorage.setItem("cs-search-history", JSON.stringify([
      { query: "python !g", literal: true }, ...Array.from({ length: 8 }, (_, i) => "历史 " + i),
    ])));
    const literalHistory = home.locator(".empty-home").getByRole("button", { name: "python !g", exact: true });
    await literalHistory.waitFor();
    check("另一标签页更新后空首页同步并限制为 8 条", await home.locator(".empty-home__chip").count() === 8, "");
    const historyRequest = home.waitForRequest(request => new URL(request.url()).pathname === "/api/search");
    await literalHistory.click();
    const restoredHistory = (await historyRequest).postDataJSON();
    check("空首页重搜保留历史的字面模式", restoredHistory.q === "python !g" && restoredHistory.opts.literal === true &&
      new URL(home.url()).searchParams.get("literal") === "1", "");
    await home.goto(BASE + "/");
    await home.locator(".empty-home__links").getByRole("button", { name: "AI 对话" }).click();
    await home.waitForSelector("#tool-drawer[open]", { timeout: 10000 });
    check("空首页快捷入口能打开 AI 对话", await home.locator("#tool-drawer").count() === 1, "");
    await homeContext.close();

    // —— 移动端：首屏结果与工具抽屉 ——
    const mobile = await browser.newContext({
      viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
      deviceScaleFactor: 3, locale: "zh-CN", serviceWorkers: "block",
    });
    const phone = await mobile.newPage();
    await phone.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await searchWithResults(phone);
    const firstCardY = await boxTop(phone, ".workspace [id^='result-']");
    check("390×844 首屏能看到第一条结果", firstCardY !== null && firstCardY < 844, `首条结果 y=${firstCardY}`);
    const firstTitleY = await phone.evaluate(() => {
      const title = document.querySelector(".group__list > .card .card__title");
      return title ? Math.round(title.getBoundingClientRect().y) : null;
    });
    check("390×844 首条结果标题在 y ≤ 700", firstTitleY !== null && firstTitleY <= 700, `标题 y=${firstTitleY}`);
    const officialState = await phone.evaluate(() => {
      const official = document.querySelector(".official");
      const firstCard = document.querySelector(".group__list > .card");
      return {
        items: document.querySelectorAll(".official__item").length,
        more: document.querySelector(".official__more")?.textContent?.trim() ?? "",
        afterCards: !!(official && firstCard &&
          (official.compareDocumentPosition(firstCard) & Node.DOCUMENT_POSITION_PRECEDING)),
      };
    });
    check("390 官方入口默认 2 条并折在强相关之后", officialState.items === 2 &&
      officialState.more.includes("查看全部") && officialState.afterCards, JSON.stringify(officialState));
    const officialToggle = phone.locator(".official__more");
    await officialToggle.press("Enter");
    check("展开后显示全部官方入口", await phone.locator(".official__item").count() >= 3,
      `${await phone.locator(".official__item").count()} 条`);
    check("官方入口展开和收起保留焦点并播报状态", await officialToggle.evaluate(node =>
      node === document.activeElement && node.getAttribute("aria-expanded") === "true" &&
      Boolean(document.getElementById(node.getAttribute("aria-controls")))), "");
    await officialToggle.press("Enter");
    check("再次激活官方入口开关时收回到两条", await officialToggle.getAttribute("aria-expanded") === "false" &&
      await phone.locator(".official__item").count() === 2, "");
    check("390×844 没有常驻书签/工具区", await phone.evaluate(() => !document.querySelector(".workspace-side")), "");
    const phoneMeta = await compactStats(phone);
    check("390×844 统计条单行且展开按钮至少 44px",
      phoneMeta.height <= 44 && phoneMeta.singleLine && phoneMeta.fits && phoneMeta.toggleHeight >= 44,
      `h=${Math.round(phoneMeta.height)} trigger=${phoneMeta.toggleHeight}`);
    const sticky = await phone.evaluate(async () => {
      window.scrollTo({ top: 700, behavior: "instant" });
      await new Promise(resolve => requestAnimationFrame(resolve));
      const top = document.querySelector(".metabar").getBoundingClientRect().top;
      const headerBottom = document.querySelector(".workspace-header").getBoundingClientRect().bottom;
      window.scrollTo({ top: 0, behavior: "instant" });
      return { top, headerBottom };
    });
    check("390×844 下滚动后统计条贴在页头下方", Math.abs(sticky.top - sticky.headerBottom) <= 2, JSON.stringify(sticky));

    const beforeDrawer = await boxTop(phone, ".workspace-results");
    await phone.locator(".workspace-drawer-fab").click();
    await phone.waitForSelector(".tool-drawer[open]", { timeout: 10000 });
    const afterDrawer = await boxTop(phone, ".workspace-results");
    check("打开工具抽屉后结果区位置不变",
      beforeDrawer !== null && afterDrawer !== null && Math.abs(beforeDrawer - afterDrawer) <= 1,
      `before=${beforeDrawer} after=${afterDrawer}`);
    const sheetTop = await boxTop(phone, ".tool-drawer__sheet");
    check("抽屉是底部面板", sheetTop !== null && sheetTop > 844 * 0.2, `sheet top=${sheetTop}`);
    const drawerShot = path.join(OUT, "mobile-drawer.png");
    await phone.screenshot({ path: drawerShot });
    report.screenshots.push(path.relative(ROOT, drawerShot));
    // 点遮罩关闭（closedby="any" 或兜底监听）
    await phone.mouse.click(195, 40);
    const closedByBackdrop = await phone.waitForSelector(".tool-drawer[open]", { state: "detached", timeout: 8000 })
      .then(() => true).catch(() => false);
    check("点遮罩关闭抽屉", closedByBackdrop, `closed=${closedByBackdrop}`);
    await phone.locator(".workspace-drawer-fab").click();
    await phone.waitForSelector(".tool-drawer[open]", { timeout: 10000 });
    await phone.locator(".tool-drawer__close").click();
    await phone.waitForSelector(".tool-drawer[open]", { state: "detached", timeout: 10000 }).catch(() => {});
    const focusBack = await phone.evaluate(() => document.activeElement?.className ?? "");
    check("关闭抽屉后焦点回到触发按钮", String(focusBack).includes("workspace-drawer-fab"), `activeElement=${focusBack}`);

    const summary = phone.locator(".tool-drawer #search-summary");
    const resultId = await phone.locator(".workspace-results [id^='result-']").first().getAttribute("id");
    const summaryRequests = await mockSummary(phone, resultId.slice("result-".length));
    await phone.locator(".workspace-results").focus();
    await phone.keyboard.press("s");
    const cite = summary.locator("button.citation").first();
    const drawerOpened = await cite.waitFor({ timeout: 8000 }).then(() => true).catch(() => false);
    check("移动端 s 打开总结抽屉并启动请求",
      drawerOpened && summaryRequests() === 1, `requests=${summaryRequests()}`);
    // 即使快捷键失败，也继续用正常入口检查引用定位。
    if (!drawerOpened) {
      if (!(await phone.locator(".tool-drawer[open]").isVisible())) await phone.locator(".workspace-drawer-fab").click();
      const summarize = phone.locator('.tool-drawer button[aria-controls="search-summary"]');
      if (await summarize.getAttribute("aria-expanded") !== "true") await summarize.click();
      await summary.getByRole("button", { name: "生成总结" }).click();
    }
    await cite.click({ timeout: 30000 });
    await phone.waitForFunction(id => !document.querySelector(".tool-drawer[open]") && document.activeElement?.id === id,
      resultId, { timeout: 8000 }).catch(() => {});
    const focusResult = await phone.evaluate(() => document.activeElement?.id ?? "");
    check("移动抽屉引用关闭抽屉并聚焦结果",
      !(await phone.locator(".tool-drawer[open]").isVisible()) && focusResult === resultId,
      `focus=${focusResult}`);
    // 仅为断言引用定位替换总结流，目标采用同一固定样本中第三条官方入口。
    await officialToggle.click();
    const thirdId = await phone.locator(".official__item").nth(2).getAttribute("id");
    await officialToggle.click();
    await phone.unroute("**/api/summarize?*");
    await mockSummary(phone, thirdId.slice("result-".length));
    await phone.locator(".workspace-results").focus();
    await phone.keyboard.press("s");
    await summary.locator("button.citation").first().click();
    check("移动端总结引用可展开并聚焦折叠的官方入口",
      await officialToggle.getAttribute("aria-expanded") === "true" &&
      await phone.evaluate(id => document.activeElement?.id === id, thirdId), thirdId);
    if (await phone.locator(".tool-drawer[open]").isVisible()) await phone.keyboard.press("Escape");
    const fab = phone.locator(".workspace-drawer-fab");
    await fab.click();
    await phone.keyboard.press("Escape");
    await phone.locator(".tool-drawer[open]").waitFor({ state: "detached" });
    check("Esc 关闭抽屉并归还焦点",
      !(await phone.locator(".tool-drawer[open]").isVisible()) &&
      await fab.evaluate(node => node === document.activeElement), "");

    await phone.evaluate(() => delete HTMLDialogElement.prototype.closedBy);
    await fab.click();
    await phone.locator(".tool-drawer[open]").evaluate(dialog => dialog.removeAttribute("closedby"));
    await phone.mouse.click(195, 40);
    const closedByFallback = await phone.locator(".tool-drawer[open]").waitFor({ state: "detached", timeout: 5000 })
      .then(() => true).catch(() => false);
    check("缺少 closedBy 接口时可点击遮罩关闭", closedByFallback, "");

    await phone.route("**/api/translate", route => route.fulfill({ json: { text: "Python ds", model: "audit-stub" } }));
    await phone.locator(".workspace-nav__item", { hasText: "百科" }).click();
    await fab.click();
    await phone.locator(".workspace-tools__tabs").getByRole("button", { name: "翻译" }).click();
    const translate = phone.locator("#search-translate");
    await translate.getByRole("textbox", { name: "原文" }).fill("test");
    await translate.getByRole("button", { name: "翻译", exact: true }).click();
    const searchRequest = phone.waitForRequest(request => new URL(request.url()).pathname === "/api/search");
    await translate.getByRole("button", { name: "搜索", exact: true }).click();
    const translatedRequest = (await searchRequest).postDataJSON();
    const translatedUrl = new URL(phone.url()).searchParams;
    check("移动端译文转搜关闭抽屉，末尾短码按字面搜索",
      !(await phone.locator(".tool-drawer[open]").isVisible()) && translatedRequest.q === "Python ds" &&
      translatedRequest.opts.literal === true && translatedUrl.get("literal") === "1" && !translatedUrl.has("category"),
      translatedUrl.toString());
    await phone.waitForSelector(READY);
    await phone.goBack();
    check("译文转搜一次后退回到原分类", new URL(phone.url()).searchParams.get("category") === "encyclopedia", phone.url());
    await phone.goBack();
    await phone.waitForSelector(READY);

    // —— 触控尺寸 ——
    const targets = await phone.evaluate(() => {
      const selectors = [
        // 摘要展开是行内次要按钮，按 24×24 单独检查
        'button:not([role="switch"]):not(.card__snippet-toggle)',
        ".workspace-nav__item",
        ".workspace-header__actions > *",
        ".pager .chip",
        ".card__save",
      ].join(",");
      const seen = new Set();
      const bad = [];
      document.querySelectorAll(selectors).forEach(node => {
        if (seen.has(node)) return;
        seen.add(node);
        // 折叠面板里的控件不参与可见性统计
        if (node.closest("details:not([open])")) return;
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        if (rect.width < 44 || rect.height < 44) {
          bad.push({
            tag: node.tagName,
            text: (node.textContent || "").trim().slice(0, 18),
            w: Math.round(rect.width),
            h: Math.round(rect.height),
          });
        }
      });
      return bad;
    });
    const inlineTargets = await phone.evaluate(() => Array.from(
      document.querySelectorAll(".card__snippet-toggle"),
    ).map(node => {
      const rect = node.getBoundingClientRect();
      return { w: Math.round(rect.width), h: Math.round(rect.height) };
    }).filter(item => item.w > 0 && (item.w < 24 || item.h < 24)));
    check("行内次要按钮 ≥24×24", inlineTargets.length === 0,
      inlineTargets.map(item => `${item.w}×${item.h}`).join(" · "));
    check("粗指针下主要控件 ≥44×44", targets.length === 0,
      targets.slice(0, 6).map(item => `${item.text || item.tag}(${item.w}×${item.h})`).join(" · "));

    const switches = await phone.evaluate(() => Array.from(document.querySelectorAll('[role="switch"]')).map(node => {
      const rect = node.getBoundingClientRect();
      return { w: Math.round(rect.width), h: Math.round(rect.height) };
    }));
    check("开关 ≥44×24", switches.length > 0 && switches.every(item => item.w >= 44 && item.h >= 24),
      switches.map(item => `${item.w}×${item.h}`).join(" · "));

    // 抽屉断点 1180：1180 及以下用抽屉入口，1181 起恢复右栏
    for (const width of [320, 768, 900, 1024, 1180, 1181, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(BASE + "/");
      const rail = page.locator(width <= 1180 ? ".workspace-drawer-fab" : ".workspace-side");
      await rail.waitFor();
      const sizes = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
      check(`${width}px 工具形态正确且页面无横向溢出`, sizes[0] <= sizes[1] + 1, sizes.join("/"));
    }

    // —— 平板 / 小笔记本断点与深色主题 ——
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto(BASE + "/?q=" + encodeURIComponent(firstQuery));
    await page.waitForSelector(".results-body", { timeout: 60000 });
    const tablet = await page.evaluate(() => ({
      columns: getComputedStyle(document.querySelector(".workspace")).gridTemplateColumns.split(" ").filter(Boolean).length,
      hasSide: !!document.querySelector(".workspace-side"),
      hasFab: (() => { const fab = document.querySelector(".workspace-drawer-fab"); return !!fab && !!fab.getClientRects().length; })(),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    }));
    check("768px 单列布局并使用抽屉入口", tablet.columns === 1 && !tablet.hasSide && tablet.hasFab && tablet.overflow <= 1,
      JSON.stringify(tablet));
    // 1024 不再固定三栏：主列在三栏里只有约 600px，换成抽屉后内容列变宽
    await page.setViewportSize({ width: 1024, height: 900 });
    await page.waitForFunction(() => {
      const fab = document.querySelector(".workspace-drawer-fab");
      return !!fab && fab.getClientRects().length > 0;
    }, null, { timeout: 10000 });
    const laptop = await page.evaluate(() => {
      const results = document.querySelector(".workspace-results");
      const side = document.querySelector(".workspace-side");
      return {
        columns: getComputedStyle(document.querySelector(".workspace")).gridTemplateColumns.split(" ").filter(Boolean).length,
        resultsWidth: results ? Math.round(results.getBoundingClientRect().width) : 0,
        hasSide: !!side && !!side.getClientRects().length,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    check("1024px 使用抽屉且内容列 ≥560", laptop.columns === 1 && !laptop.hasSide &&
      laptop.resultsWidth >= 560 && laptop.overflow <= 1, JSON.stringify(laptop));
    const laptopShot = path.join(OUT, "laptop-1024.png");
    await page.screenshot({ path: laptopShot });
    report.screenshots.push(path.relative(ROOT, laptopShot));

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForFunction(() => {
      const side = document.querySelector(".workspace-side");
      return !!side && side.getClientRects().length > 0;
    }, null, { timeout: 10000 });
    const wide = await page.evaluate(() => {
      const main = document.querySelector(".workspace-main");
      const fab = document.querySelector(".workspace-drawer-fab");
      return {
        columns: getComputedStyle(document.querySelector(".workspace")).gridTemplateColumns.split(" ").filter(Boolean).length,
        mainWidth: main ? Math.round(main.getBoundingClientRect().width) : 0,
        hasFab: !!fab && !!fab.getClientRects().length,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    check("1440px 恢复三栏且主列 ≥560", wide.columns === 3 && !wide.hasFab &&
      wide.mainWidth >= 560 && wide.overflow <= 1, JSON.stringify(wide));

    const darkPage = await desktop.newPage();
    await darkPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await darkPage.waitForSelector(".results-body", { timeout: 60000 });
    await darkPage.evaluate(() => {
      localStorage.setItem("cs-theme", "dark");
      document.documentElement.dataset.theme = "dark";
      document.documentElement.dataset.themeChoice = "dark";
    });
    await darkPage.waitForTimeout(200);
    const darkSurface = await darkPage.evaluate(() => ({
      scheme: getComputedStyle(document.documentElement).colorScheme,
      bg: getComputedStyle(document.querySelector(".workspace-app") || document.body).backgroundColor,
      meta: document.querySelector('meta[name="theme-color"]')?.getAttribute("content") ?? "",
    }));
    check("深色主题下 color-scheme 与页面底色一致",
      darkSurface.scheme === "dark" && /rgb\(2[0-9], 2[0-9], 2[0-9]\)|rgb\(1[0-9], 1[0-9], 1[0-9]\)/.test(darkSurface.bg),
      JSON.stringify(darkSurface));
    await axeScan(darkPage, "深色结果页");
    await darkPage.close();
    await phone.setViewportSize({ width: 320, height: 720 });
    const smallStats = await compactStats(phone);
    check("320px 统计条单行且不遮挡详情按钮", smallStats.singleLine && smallStats.fits, `h=${smallStats.height}`);
    await phone.setViewportSize({ width: 390, height: 844 });

    // —— 截图基线 ——
    const shots = [
      ["desktop-light-search", page, { width: 1440, height: 900 }, "light", "/?q=python"],
      ["mobile-dark-search", phone, null, "dark", "/?q=python"],
    ];
    for (const [name, browserPage, viewport, theme, route] of shots) {
      if (viewport) await browserPage.setViewportSize(viewport);
      await browserPage.goto(BASE + route, { waitUntil: "domcontentloaded" });
      await browserPage.evaluate((value) => {
        document.documentElement.dataset.theme = value;
        document.documentElement.style.colorScheme = value;
      }, theme);
      await browserPage.waitForSelector(".workspace-results .pager, .state--empty, .state--error", { timeout: 60000 });
      const file = path.join(OUT, name + ".png");
      await browserPage.screenshot({ path: file, fullPage: false });
      report.screenshots.push(path.relative(ROOT, file));
    }
    await mobile.close();

    // —— P2：快捷键焦点、安装按钮不可用态、离线文案 ——
    const focusPage = await desktop.newPage();
    await focusPage.goto(BASE + "/?q=" + encodeURIComponent(firstQuery), { waitUntil: "domcontentloaded" });
    await focusPage.waitForSelector(".results-body", { timeout: 60000 });
    await focusPage.evaluate(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); });
    check("? 从无焦点状态打开面板前焦点在 body",
      await focusPage.evaluate(() => document.activeElement === document.body), "");
    await focusPage.keyboard.press("?");
    await focusPage.waitForSelector(".shortcuts-dialog[open]", { timeout: 10000 });
    await focusPage.keyboard.press("Escape");
    await focusPage.waitForFunction(() => !document.querySelector(".shortcuts-dialog[open]"), null, { timeout: 10000 });
    await focusPage.waitForFunction(() => document.activeElement?.matches(".shortcuts__open"));
    const focusedAfterClose = await focusPage.evaluate(() => {
      const active = document.activeElement;
      return { tag: active ? active.tagName : "", text: (active?.textContent ?? "").trim().slice(0, 20),
        isBody: !active || active === document.body };
    });
    check("无焦点时关闭面板把焦点交还「全部快捷键」",
      !focusedAfterClose.isBody && focusedAfterClose.text.includes("全部快捷键"),
      JSON.stringify(focusedAfterClose));
    await focusPage.goto(BASE + "/");
    await focusPage.locator(".empty-home").waitFor();
    await focusPage.keyboard.press("?");
    await focusPage.getByRole("dialog", { name: "键盘快捷键" }).getByRole("button", { name: "关闭" }).click();
    check("空首页快捷键面板关闭后焦点回到主内容", await focusPage.evaluate(() => document.activeElement?.id === "main"), "");
    await focusPage.close();

    const installPage = await desktop.newPage();
    await installPage.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    await installPage.getByRole("heading", { name: "安装与离线" }).waitFor();
    const installState = await installPage.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("section[aria-labelledby='install-settings'] button"));
      const target = buttons.find(node => /安装|入口/.test(node.textContent ?? ""));
      return target ? { text: target.textContent?.trim() ?? "", disabled: target.disabled,
        title: target.getAttribute("title") ?? "" } : null;
    });
    check("未提供安装入口时按钮真禁用并给菜单指引", !!installState && installState.disabled &&
      installState.title.includes("浏览器菜单"), JSON.stringify(installState));
    await installPage.close();

    const insecurePage = await desktop.newPage();
    await insecurePage.addInitScript(() => { Object.defineProperty(window, "isSecureContext", { value: false }); });
    await insecurePage.goto(BASE + "/settings");
    const installCard = insecurePage.locator('[aria-labelledby="install-settings"]');
    await installCard.getByText("局域网地址需要 HTTPS", { exact: false }).waitFor();
    check("非安全上下文提示 HTTPS 并隐藏安装入口", await installCard.getByRole("button").count() === 0, "");
    await insecurePage.close();

    // 断网：/api 全部失败，界面要给中文产品文案而不是 Failed to fetch
    const offlinePage = await desktop.newPage();
    await offlinePage.route("**/api/**", route => route.abort());
    await offlinePage.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    await offlinePage.waitForSelector(".server-banner", { timeout: 30000 });
    const offlineState = await offlinePage.evaluate(() => ({
      banner: (document.querySelector(".server-banner")?.innerText ?? "").replace(/\s+/g, " "),
      engineError: (Array.from(document.querySelectorAll("#engine-settings [role=status]"))
        .map(node => node.textContent ?? "").join(" ")).replace(/\s+/g, " "),
      saveDisabled: (() => {
        const button = Array.from(document.querySelectorAll("#engine-settings button"))
          .find(node => /保存引擎设置/.test(node.textContent ?? ""));
        return button ? button.disabled : null;
      })(),
    }));
    check("断网时页头显示连不上本机服务", offlineState.banner.includes("连不上本机服务"), offlineState.banner.slice(0, 40));
    check("断网时引擎设置用中文文案且没有可写的保存",
      offlineState.engineError.includes("连不上本机服务") && !offlineState.engineError.includes("Failed to fetch") &&
      offlineState.saveDisabled !== false, JSON.stringify(offlineState).slice(0, 140));
    await offlinePage.close();

    const reconnectPage = await desktop.newPage();
    let healthProbes = 0;
    let blockHealth = false;
    let releaseHealth;
    let pendingHealth;
    await reconnectPage.route("**/api/health", async route => {
      healthProbes++;
      if (blockHealth) {
        await new Promise(resolve => { releaseHealth = resolve; pendingHealth?.(); });
      }
      await route.fulfill({ json: health }).catch(() => {});
    });
    await reconnectPage.route("**/api/settings/engines", route => route.fulfill({ json: engineSettingsFixture }));
    await reconnectPage.goto(BASE + "/settings");
    const enginePanel = reconnectPage.locator("#engine-settings");
    const engineMode = enginePanel.getByRole("switch", { name: "使用自选默认引擎" });
    const addEngine = enginePanel.getByRole("button", { name: "添加搜索入口" });
    await addEngine.click();
    check("设置页和所有能力控件共享一次 health", healthProbes === 1, `health=${healthProbes}`);
    await enginePanel.getByLabel("入口名称").fill("未保存草稿");
    await reconnectPage.evaluate(() => window.dispatchEvent(new Event("offline")));
    await reconnectPage.locator('.server-banner[data-state="offline"]').waitFor();
    check("掉线后已加载的引擎面板只读并保留草稿", await engineMode.isDisabled() && await addEngine.isDisabled() &&
      await enginePanel.getByLabel("入口名称").isDisabled() && (await enginePanel.getByLabel("入口名称").inputValue()) === "未保存草稿" &&
      await enginePanel.getByRole("button", { name: "刷新状态" }).isEnabled(), "");
    const beforeReconnect = healthProbes;
    blockHealth = true;
    const healthHeld = new Promise(resolve => { pendingHealth = resolve; });
    await reconnectPage.evaluate(() => window.dispatchEvent(new Event("online")));
    await healthHeld;
    await reconnectPage.evaluate(() => window.dispatchEvent(new Event("offline")));
    await reconnectPage.locator('.server-banner[data-state="offline"]').waitFor();
    blockHealth = false;
    releaseHealth();
    const followupHealth = reconnectPage.waitForResponse(response => new URL(response.url()).pathname === "/api/health");
    await reconnectPage.evaluate(() => window.dispatchEvent(new Event("online")));
    await followupHealth;
    await reconnectPage.locator(".server-banner").waitFor({ state: "hidden" });
    check("每次连网只探测一次 health，恢复后引擎面板可编辑",
      healthProbes - beforeReconnect === 2 && await enginePanel.getByLabel("入口名称").isEnabled(),
      `两次 online 共 ${healthProbes - beforeReconnect} 次 health`);
    await reconnectPage.close();

    await desktop.close();
  } catch (error) {
    report.error = String(error && error.stack ? error.stack : error);
    console.error(report.error);
  } finally {
    await browser.close();
  }
  writeReport(OUT, "p0-ui-audit", report);
})().catch(error => {
  console.error(`无法启动浏览器审计：${error.message}`);
  process.exitCode = 1;
});
