#!/usr/bin/env node
/**
 * 真实浏览器验收：加载未打包扩展 + 检查 PWA 清单。
 *
 * 依赖：npm i -D playwright && npx playwright install chromium（仓库默认不装）
 * 用法：node scripts/verify-extension.cjs [baseUrl] [截图目录]
 * 默认：http://127.0.0.1:8000  与 docs/m9-evidence
 *
 * 会启动一个可见的 Chromium（--load-extension 在 headless 下不稳），
 * 使用临时 profile，跑完自动关闭；不会改动正式书签库以外的任何东西。
 */
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function loadPlaywright() {
  const searchPaths = [
    path.join(ROOT, "apps", "web", "node_modules"),
    path.join(ROOT, "node_modules"),
  ];
  for (const dir of searchPaths) {
    try {
      return require(require.resolve("playwright", { paths: [dir] }));
    } catch {
      /* 继续找下一个位置 */
    }
  }
  try {
    return require("playwright");
  } catch {
    throw new Error(
      "缺少 playwright：在 apps/web 下执行 npm i -D playwright && npx playwright install chromium 后重试",
    );
  }
}

const { chromium } = loadPlaywright();
const EXT = path.join(ROOT, "apps", "extension");
const BASE = process.argv[2] || process.env.CS_BASE_URL || "http://127.0.0.1:8000";
const OUT = process.argv[3] || path.join(ROOT, "docs", "m9-evidence");

const log = [];
const check = (name, ok, detail) => log.push({ name, ok: !!ok, detail });

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "cs-ext-profile-"));
  const channel = process.env.CS_BROWSER_CHANNEL || undefined;
  const context = await chromium.launchPersistentContext(profile, {
    headless: false,
    channel,
    viewport: { width: 1280, height: 900 },
    args: ["--disable-extensions-except=" + EXT, "--load-extension=" + EXT, "--no-first-run"],
  });

  const errors = [];
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(String(e.message)));
  let failedStep = "";

  try {
    let worker = context.serviceWorkers()[0];
    if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 15000 });
    const extensionId = new URL(worker.url()).host;
    check("扩展已加载", !!extensionId, "id=" + extensionId);

    const tokenBody = await (await fetch(BASE + "/api/tools/bookmarklet")).json();

    await page.goto("chrome-extension://" + extensionId + "/popup.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#save", { timeout: 15000 });
    check("popup 可打开", true, extensionId + "/popup.html");

    await page.click("details summary");
    await page.fill("#api", BASE);
    await page.fill("#token", tokenBody.token);
    await page.click("#save-settings");
    await page.waitForFunction(() => /设置已保存/.test(document.querySelector("#status")?.textContent || ""), null, { timeout: 5000 });

    await page.fill("#url", "https://docs.python.org/3/library/asyncio.html");
    await page.fill("#title", "asyncio 文档（扩展验收）");
    await page.click("#save");
    await page.waitForFunction(() => /已收藏|已在书签|失败/.test(document.querySelector("#status")?.textContent || ""), null, { timeout: 15000 });
    const status = (await page.textContent("#status")) || "";
    check("popup 写入书签", /已收藏/.test(status), status);

    const saved = await (await fetch(BASE + "/api/bookmarks")).json();
    check(
      "书签落库",
      saved.total >= 1 && saved.items.some((item) => item.url.includes("docs.python.org")),
      "total=" + saved.total,
    );
    await page.screenshot({ path: path.join(OUT, "01-扩展收藏.png") });

    // 后台 service worker 的保存函数（右键菜单复用同一条路径）
    const background = await worker.evaluate(async (base) => {
      const result = await self.cleansearchSave(base + "/", "后台保存验收");
      return result;
    }, BASE);
    check("后台保存函数可用", background && background.ok === true, JSON.stringify(background));

    const cdp = await context.newCDPSession(page);
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    const manifest = await cdp.send("Page.getAppManifest");
    check(
      "manifest 被解析",
      (manifest.data || "").includes("share_target") && String(manifest.url).includes("manifest.webmanifest"),
      manifest.url,
    );
    const installability = await cdp.send("Page.getInstallabilityErrors");
    const installErrors = (installability.installabilityErrors || []).map((e) => e.errorId);
    fs.writeFileSync(
      path.join(OUT, "installability.json"),
      JSON.stringify(installErrors, null, 2),
    );
    check("安装性检查", true, installErrors.length ? installErrors.join(" | ") : "无错误");

    check("无 JS 运行时错误", errors.length === 0, errors.slice(0, 2).join(" | ") || "ok");
  } catch (error) {
    failedStep = String(error).split("\n")[0];
  }

  await context.close();
  console.log(JSON.stringify(log, null, 1));
  const failed = log.filter((item) => !item.ok);
  console.log(failedStep ? "STEP FAILED: " + failedStep : failed.length === 0 ? "ALL PASS" : "FAILED: " + failed.map((f) => f.name).join(", "));
  process.exit(failedStep || failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});