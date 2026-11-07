const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8000";
const OUT = "D:\\agent\\llq\\docs\\m10-evidence";

(async () => {
  const browser = await chromium.launch();
  const results = [];
  const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail });

  // ---------- 桌面：favicon / 死链快照 / 拖拽 / 导入进度 ----------
  const page = await browser.newPage({ viewport: { width: 1280, height: 950 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(BASE + "/bookmarks", { waitUntil: "networkidle" });
  await page.waitForSelector(".bm-card", { timeout: 20000 });

  const faviconSrc = await page.$$eval(".bm-card img", (els) => els.map((e) => e.getAttribute("src")).filter(Boolean));
  check("favicon 走本地缓存接口", faviconSrc.some((src) => src && src.startsWith("/api/favicon?host=")), faviconSrc.slice(0, 2).join(" | "));

  // 触发死链检查，等徽标出现
  await page.click('button:has-text("检测本页死链")');
  await page.waitForFunction(() => /失效/.test(document.querySelector(".bm-message")?.textContent || ""), null, { timeout: 60000 });
  await page.waitForSelector(".bm-card__dead", { timeout: 30000 });
  const deadText = await page.textContent(".bm-card__dead");
  check("死链徽标带状态码", /404/.test(deadText || ""), deadText);

  // 拖拽：把第一张卡片拖到「资料」分组
  const card = await page.$('.bm-card[data-bookmark-id="1"]');
  const chip = await page.$('.bm-groups .chip:has-text("资料")');
  check("卡片可拖拽", (await card.getAttribute("draggable")) !== null, "draggable");
  const box = await card.boundingBox();
  const chipBox = await chip.boundingBox();
  await page.mouse.move(box.x + 40, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(chipBox.x + 20, chipBox.y + 10, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(1200);
  const moved = await page.evaluate(async () => {
    const res = await fetch("/api/bookmarks?limit=200");
    const body = await res.json();
    const item = body.items.find((i) => i.id === 1);
    return item ? { group: item.group_id, name: item.group_name } : null;
  });
  check("拖拽后分组已改", moved && moved.group !== null, JSON.stringify(moved));

  // 导入 2000 条，验证进度文案最终变结果
  const entries = Array.from({ length: 2000 }, (_, i) => `<DT><A HREF="https://bulk.test/${i}" ADD_DATE="1700000000">批量 ${i}</A>`).join("");
  const file = path.join(process.env.TEMP, "bulk-bookmarks.html");
  fs.writeFileSync(file, "<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>" + entries + "</DL><p>");
  await page.setInputFiles('input[type="file"]', file);
  await page.waitForFunction(() => /导入 2000 条/.test(document.querySelector(".bm-message")?.textContent || ""), null, { timeout: 120000 });
  const imported = await page.textContent(".bm-message");
  check("大量导入完成", /新增 2000/.test(imported || ""), (imported || "").slice(0, 60));
  await page.screenshot({ path: path.join(OUT, "02-bookmarks-p3.png"), fullPage: false });

  // ---------- 移动端：抽屉手势 ----------
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await mobile.goto(BASE, { waitUntil: "networkidle" });
  await mobile.fill('input[name="q"]', "HTTP");
  await mobile.click('button[type="submit"]');
  await mobile.waitForSelector("article.card", { timeout: 40000 });
  await mobile.click('button:has-text("AI 总结")');
  await mobile.waitForSelector(".layout__side--open", { timeout: 15000 });
  const drawer = await mobile.$(".layout__side--open");
  const dbox = await drawer.boundingBox();
  // 模拟从抽屉顶部向下拉
  await mobile.touchscreen.tap(dbox.x + dbox.width / 2, dbox.y + 20);
  await mobile.evaluate(() => {
    const el = document.querySelector(".layout__side--open");
    const touch = (y) => new Touch({ identifier: 1, target: el, clientX: 100, clientY: y });
    el.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, touches: [touch(200)], changedTouches: [touch(200)] }));
    el.dispatchEvent(new TouchEvent("touchmove", { bubbles: true, touches: [touch(340)], changedTouches: [touch(340)] }));
    el.dispatchEvent(new TouchEvent("touchend", { bubbles: true, touches: [], changedTouches: [touch(340)] }));
  });
  await mobile.waitForTimeout(600);
  const open = await mobile.$(".layout__side--open");
  check("下拉手势关闭抽屉", open === null, open === null ? "closed" : "still open");

  check("无 JS 运行时错误", errors.length === 0, errors.slice(0, 2).join(" | ") || "ok");
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
  const failed = results.filter((r) => !r.ok);
  console.log(failed.length ? "FAILED: " + failed.map((f) => f.name).join(", ") : "ALL PASS");
  process.exit(failed.length ? 1 : 0);
})();
