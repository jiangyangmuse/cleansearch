const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { chromium } = createRequire(path.resolve('apps/web/package.json'))('playwright');

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1280, height: 1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const evidence = {browser: browser.version(), base: 'http://127.0.0.1:8000', search_summary_mocked: false, bookmark_writes: false};
  try {
    // 只排除图标下载；真实搜索、目录和总结请求全部直连日常服务。
    await page.route('**/api/favicon**', route => route.fulfill({status: 404}));
    const response = page.waitForResponse(r => r.url().endsWith('/api/search'));
    await page.goto('http://127.0.0.1:8000/?q=deepseek');
    const payload = await (await response).json();
    const entries = payload.official.entries;
    assert.ok(entries.length >= 1);
    assert.equal(payload.meta.provider, 'searxng');
    assert.equal(payload.meta.cached, true);
    await page.locator('.official__link').first().waitFor();
    const total = payload.meta.total + payload.meta.official;
    assert.match(await page.locator('.metabar').innerText(), new RegExp(`展示 ${total} 条`));
    for (const entry of entries) {
      const target = page.locator(`[data-result-id="${entry.id}"]`);
      assert.equal(await target.count(), 1);
      assert.equal(await target.isVisible(), true);
      assert.equal(await page.locator(`.group a[href="${entry.url}"]`).count(), 0);
    }
    await page.locator('input[name="q"]').blur();
    await page.keyboard.press('j');
    assert.equal(await page.locator(`#result-${entries[0].id}`).evaluate(node => node === document.activeElement), true);
    await page.getByRole('button', {name: '生成总结', exact: true}).click();
    await page.getByRole('button', {name: '重新生成', exact: true}).waitFor({timeout: 90000});
    assert.equal(await page.locator('.summary__error').count(), 0);
    let linked = null;
    for (const entry of entries) {
      // SSE 中的编号顺序与官方区顺序一致。
      const number = entries.indexOf(entry) + 1;
      const cite = page.locator('.summary__text .citation').filter({hasText: `[${number}]`}).first();
      if (await cite.count()) {
        await cite.click();
        assert.equal(await page.locator(`#result-${entry.id}`).evaluate(node => node.classList.contains('card--flash')), true);
        linked = {number, result_id: entry.id, url: entry.url};
        break;
      }
    }
    assert.ok(linked, '模型正文没有官方入口引用，不能证明入口引用定位');
    evidence.citation_target = linked;
    evidence.official = entries.map(({role, url, id}) => ({role, url, id}));
    evidence.displayed = total;
    evidence.summary_model = await page.locator('.summary__foot').innerText();
    await page.screenshot({path: path.join(__dirname, 'live-desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('.official').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: path.join(__dirname, 'live-mobile.png')});
    evidence.mobile_no_overflow = true;
    const tutorialResponse = page.waitForResponse(r => r.url().endsWith('/api/search'));
    await page.goto('http://127.0.0.1:8000/?q=' + encodeURIComponent('deepseek how to use'));
    const tutorial = await (await tutorialResponse).json();
    assert.equal(tutorial.official, null);
    assert.equal(await page.locator('.official').count(), 0);
    assert.ok(tutorial.meta.total > 0);
    evidence.tutorial_has_no_official_panel = true;
    assert.deepEqual(errors, []);
    evidence.page_errors = errors;
    fs.writeFileSync(path.join(__dirname, 'browser-live.json'), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
