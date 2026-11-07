/**
 * Android 相关验收（浏览器模拟，非真机）：
 * 1) share_target 声明有效且能被系统分享命中
 * 2) 分享链接预填到书签表单
 * 3) PWA 安装性检查
 * 4) 触屏交互（保存按钮）在移动视口可用
 */
const path = require("path");

function loadPlaywright() {
  const candidates = [
    "playwright",
    path.join(__dirname, "..", "apps", "web", "node_modules", "playwright"),
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      /* 继续尝试下一个 */
    }
  }
  throw new Error("找不到 playwright：先在 apps/web 里 npm ci");
}

const { chromium, devices } = loadPlaywright();

const BASE = process.env.CS_BASE || "http://127.0.0.1:8000";
const OUT = "docs/m10-evidence";

(async () => {
  const results = [];
  const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail });
  const browser = await chromium.launch();
  const context = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));

  // 1) manifest 与 share_target
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  const manifestHref = await page.getAttribute('link[rel="manifest"]', "href");
  const manifest = await (await context.request.get(new URL(manifestHref, BASE).toString())).json();
  const share = manifest.share_target || {};
  check("manifest 声明 share_target", share.action === "/bookmarks" && share.method === "GET",
        `action=${share.action} method=${share.method}`);
  check("share_target 参数完整", ["title", "text", "url"].every((key) => share.params && share.params[key]),
        JSON.stringify(share.params || {}));

  // 2) 分享预填（Android 分享会带 url/text/title）
  const shared = encodeURIComponent("https://docs.python.org/3/library/asyncio.html");
  const text = encodeURIComponent("asyncio 文档 " + "https://docs.python.org/3/library/asyncio.html");
  await page.goto(`${BASE}/bookmarks?url=${shared}&text=${text}&title=${encodeURIComponent("asyncio 文档")}`, { waitUntil: "networkidle" });
  const prefilled = await page.inputValue('input[aria-label="新书签网址"]');
  const prefilledTitle = await page.inputValue('input[aria-label="新书签标题"]');
  check("分享链接预填", prefilled.includes("docs.python.org"), prefilled.slice(0, 50));
  check("分享标题预填", prefilledTitle.includes("asyncio"), prefilledTitle);

  // 3) 触屏保存
  await page.tap('.bm-add button[type="submit"]');
  await page.waitForFunction(() => /已收藏|已在书签/.test(document.querySelector(".bm-message")?.textContent || ""), null, { timeout: 20000 });
  const saved = await page.evaluate(async () => {
    const body = await (await fetch("/api/bookmarks?limit=50")).json();
    return body.items.some((item) => item.url.includes("docs.python.org/3/library/asyncio.html"));
  });
  check("触屏保存成功", saved, "bookmark present=" + saved);
  await page.screenshot({ path: OUT + "/03-android-share-prefill.png" });

  // 4) 安装性（CDP）
  const cdp = await context.newCDPSession(page);
  await cdp.send("Page.enable");
  const manifestInfo = await cdp.send("Page.getAppManifest");
  let installability = [];
  try {
    installability = (await cdp.send("Page.getInstallabilityErrors")).installabilityErrors || [];
  } catch (error) {
    installability = [{ errorId: String(error).slice(0, 60) }];
  }
  check("PWA 清单可读", !!manifestInfo.data, (manifestInfo.url || "").slice(-40));
  check("安装性问题数", installability.length === 0, JSON.stringify(installability).slice(0, 160));

  check("无 JS 运行时错误", errors.length === 0, errors.slice(0, 2).join(" | ") || "ok");
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
  const failed = results.filter((r) => !r.ok);
  console.log(failed.length ? "FAILED: " + failed.map((f) => f.name).join(", ") : "ALL PASS");
  process.exit(failed.length ? 1 : 0);
})();