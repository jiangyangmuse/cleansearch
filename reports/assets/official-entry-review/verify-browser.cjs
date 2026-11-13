const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.resolve('apps/web/package.json'))('playwright');
const base = process.argv[2] || 'http://127.0.0.1:18175';
const out = __dirname;

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1280, height: 1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const evidence = {browser: browser.version(), upstream: 'seeded fixture', search_summary_bookmark_mocked: false, favicon_mocked: true};
  try {
    // 图标不属于验收范围，拦截以免触发外部请求。
    await page.route('**/api/favicon**', route => route.fulfill({status: 404}));
    const response = page.waitForResponse(r => r.url().endsWith('/api/search'));
    await page.goto(`${base}/?q=deepseek`);
    const payload = await (await response).json();
    const links = payload.official.entries;
    assert.equal(links.length, 4);
    await page.locator('.official__link').first().waitFor();
    assert.match(await page.locator('.metabar').innerText(), /展示 6 条/);
    for (const entry of links) {
      assert.equal(await page.locator(`[data-result-id="${entry.id}"]`).count(), 1);
      assert.equal(await page.locator(`.group a[href="${entry.url}"]`).count(), 0);
    }
    const first = page.locator(`#result-${links[0].id}`);
    await page.locator('input[name="q"]').blur();
    await page.keyboard.press('j');
    assert.equal(await first.evaluate(node => node === document.activeElement), true);
    await page.keyboard.press('b');
    await first.getByRole('button', {name: '已收藏', exact: true}).waitFor();
    const popup = page.waitForEvent('popup');
    await page.keyboard.press('Enter');
    const opened = await popup;
    await opened.close();
    evidence.keyboard_navigation_and_bookmark = true;
    await page.getByRole('button', {name: '生成总结', exact: true}).click();
    await page.getByRole('button', {name: '重新生成', exact: true}).waitFor({timeout: 10000});
    const citation = page.locator('.summary__text button').first();
    await citation.click();
    assert.equal(await first.evaluate(node => node.classList.contains('card--flash')), true);
    evidence.summary_citation_target = links[0].id;
    await page.screenshot({path: path.join(out, 'desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('.official').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: path.join(out, 'mobile.png')});
    await page.setViewportSize({width: 320, height: 740});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    evidence.no_overflow_widths = [390, 320];
    // 缓存重载后仍可引用同一入口。
    const cachedResponse = page.waitForResponse(r => r.url().endsWith('/api/search'));
    await page.reload();
    const cached = await (await cachedResponse).json();
    assert.equal(cached.meta.cached, true);
    assert.deepEqual(cached.official, payload.official);
    assert.equal(await page.locator(`#result-${links[0].id}`).count(), 1);
    evidence.cache_keeps_ids = true;
    const ordinaryResponse = page.waitForResponse(r => r.url().endsWith('/api/search'));
    await page.goto(`${base}/?q=${encodeURIComponent('deepseek how to use')}`);
    const ordinary = await (await ordinaryResponse).json();
    assert.equal(ordinary.official, null);
    assert.equal(await page.locator('.official').count(), 0);
    evidence.content_query_uses_normal_results = true;
    assert.deepEqual(errors, []);
    evidence.page_errors = errors;
    fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
