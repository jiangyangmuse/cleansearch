// 视觉回归：按路由 × 断点 × 主题截图，与基线哈希比对。
// 用法：node scripts/visual-regression.cjs [--base URL] [--update]
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { ROOT, loadPlaywright } = require("./browser-check.cjs");
const { PNG } = require(require.resolve("pngjs", { paths: [path.join(ROOT, "apps", "web")] }));

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const index = argv.indexOf("--" + name);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
};
const BASE = arg("base", "http://127.0.0.1:8000").replace(/\/+$/, "");
const OUT = path.resolve(ROOT, arg("out", "reports/assets/p2-extension-vitals-review/visual-baseline"));
const UPDATE = argv.includes("--update");
const CURRENT = UPDATE ? OUT : path.resolve(arg("actual", path.join(OUT, "actual")));

const ROUTES = [
  { name: "search-idle", path: "/", wait: ".workspace-search" },
  { name: "search-results", path: "/?q=python", wait: ".results-body" },
  { name: "bookmarks", path: "/bookmarks", wait: ".bm-card, .bm-empty" },
  { name: "settings", path: "/settings", wait: "#engine-settings" },
  { name: "summary", path: "/s", wait: ".page-summary__examples, .page-summary" },
  { name: "tools", path: "/tools", wait: ".tools__card" },
];
const VIEWPORTS = [
  { name: "desktop", viewport: { width: 1440, height: 900 }, theme: "light" },
  { name: "mobile", viewport: { width: 390, height: 844 }, theme: "dark", isMobile: true, hasTouch: true },
];

function digest(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex").slice(0, 16);
}

function samePixels(reference, candidate) {
  const before = PNG.sync.read(fs.readFileSync(reference));
  const after = PNG.sync.read(fs.readFileSync(candidate));
  if (before.width !== after.width || before.height !== after.height) return false;
  // Chromium can round the same antialiased edge by one or two RGB levels.
  return before.data.every((value, index) => Math.abs(value - after.data[index]) <= (index % 4 === 3 ? 0 : 2));
}

(async () => {
  if (!UPDATE && CURRENT === OUT) throw new Error("对比截图目录须与基线目录不同");
  fs.mkdirSync(CURRENT, { recursive: true });
  const manifestPath = path.join(OUT, "manifest.json");
  const baseline = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, "utf8")) : {};
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const results = [];
  try {
    for (const spec of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: spec.viewport, isMobile: !!spec.isMobile, hasTouch: !!spec.hasTouch,
        deviceScaleFactor: 1, locale: "zh-CN", colorScheme: spec.theme, serviceWorkers: "block",
      });
      await context.addInitScript((theme) => localStorage.setItem("cs-theme", theme), spec.theme);
      const page = await context.newPage();
      await page.route("**/api/bookmarks?*", route => route.fulfill({ json: {
        items: [{ id: 1, url: "https://docs.python.org/3/library/asyncio.html", title: "asyncio 文档",
          group_id: null, group_name: null, tags: ["异步", "文档"], created_at: 0, dead: 0 }],
        groups: [], tags: [{ tag: "异步", count: 1 }, { tag: "文档", count: 1 }], total: 1, fts: true,
      } }));
      for (const route of ROUTES) {
        const key = `${spec.name}-${route.name}`;
        await page.goto(BASE + route.path, { waitUntil: "domcontentloaded" });
        await page.waitForSelector(route.wait, { timeout: 45000 });
        if (route.name.startsWith("search-")) {
          await page.waitForFunction(() => {
            const quickbar = document.querySelector(".workspace-side .quick-bookmarks");
            return !quickbar || !quickbar.textContent.includes("正在读取书签");
          });
          await page.locator(".workspace-engines > summary").waitFor();
        }
        await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important}" });
        await page.evaluate(() => document.fonts.ready.then(() => {}));
        const file = path.join(CURRENT, key + ".png");
        // 缓存命中状态、耗时、sid 会随运行变化，截图时遮掉这些区域
        const masks = [];
        for (const selector of [".metabar", ".results-progress", ".summary__sid", ".summary__foot",
          ".quick-bookmarks", ".tools__token", ".tools__card .state__hint:last-child"]) {
          masks.push(...(await page.locator(selector).all()));
        }
        await page.screenshot({ path: file, fullPage: false, mask: masks });
        const hash = digest(file);
        const previous = baseline[key];
        const reference = path.join(OUT, key + ".png");
        const missing = !UPDATE && (!previous || !fs.existsSync(reference));
        const changed = !UPDATE && !missing && (digest(reference) !== previous ||
          (previous !== hash && !samePixels(reference, file)));
        results.push({ key, hash, changed, missing });
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const current = Object.fromEntries(results.map((item) => [item.key, item.hash]));
  const changed = results.filter((item) => item.changed);
  const missing = results.filter((item) => item.missing);
  if (UPDATE) {
    fs.writeFileSync(manifestPath, JSON.stringify(current, null, 2) + "\n");
    console.log(`已更新基线：${results.length} 张（${OUT}）`);
  } else {
    console.log(`对比 ${results.length} 张：变化 ${changed.length}，缺基线 ${missing.length}`);
    for (const item of changed) console.log("  变化 " + item.key);
    for (const item of missing) console.log("  新增 " + item.key);
    if (changed.length || missing.length) process.exitCode = 1;
  }
})();
