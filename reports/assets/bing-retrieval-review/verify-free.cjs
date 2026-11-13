const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.resolve('apps/web/package.json'))('playwright');
const base = process.argv[2] || 'http://127.0.0.1:18177';
const label = base.endsWith(':8000') ? 'daily' : 'isolated';

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport:{width:1280,height:1000}});
  const errors=[];
  page.on('pageerror', e=>errors.push(e.message));
  const evidence={base,browser:browser.version(),search_mocked:false,favicon_mocked:true,bookmark_writes:false};
  async function query(text) {
    const waited=page.waitForResponse(r=>r.url().endsWith('/api/search'),{timeout:45000});
    await page.goto(base+'/?q='+encodeURIComponent(text));
    const response=await waited;
    assert.equal(response.status(),200);
    return response.json();
  }
  try {
    await page.route('**/api/favicon**',r=>r.fulfill({status:404}));
    const body=await query('deepseek !b');
    assert.equal(body.parsed.engine,'bing');
    assert.deepEqual(body.meta.engines,['bing']);
    const entries=body.official.entries;
    const home=entries.find(e=>e.role==='home');
    assert.equal(home.origin,'directory');
    assert.equal(home.url,'https://www.deepseek.com/');
    assert.deepEqual(home.engine,[]);
    await page.locator(`#result-${home.id}`).waitFor();
    assert.match(await page.locator(`#result-${home.id}`).innerText(),/目录直达/);
    assert.ok(entries.some(e=>e.role==='console'&&e.origin==='search'));
    const ordinary=Object.values(body.groups).flat();
    assert.ok(ordinary.some(e=>e.url.includes('huggingface.co')&&e.score>=.30));
    evidence.bing={meta:body.meta,official:entries.map(({url,role,origin})=>({url,role,origin}))};
    const cached=await query('deepseek !b');
    assert.equal(cached.meta.cached,true);
    assert.deepEqual(cached.official,body.official);
    evidence.cache=true;
    const navigation=await query('deepseek 官网 !b');
    const warnings=Object.values(navigation.groups).flat().filter(e=>e.brand_warning);
    assert.ok(warnings.every(e=>e.score<.30&&navigation.groups.weak.some(w=>w.id===e.id)));
    if(warnings.length) {
      const weak=page.locator('details.group--collapsible');
      if(await weak.count()) await weak.locator('summary').click();
      await page.getByText('品牌身份未核验',{exact:true}).first().waitFor();
    }
    evidence.warning_candidates_present=warnings.length>0;
    evidence.warnings=warnings.map(({url,brand_warning,risk})=>({url,brand_warning,risk}));
    await page.screenshot({path:path.join(__dirname,label+'-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await page.locator('.official').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(__dirname,label+'-mobile.png')});
    evidence.mobile_no_overflow=true;
    evidence.page_errors=errors;
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(__dirname,label+'-browser.json'),JSON.stringify(evidence,null,2));
    console.log(JSON.stringify({base,official:entries.length,directory:body.meta.directory,engines:body.meta.engines,warnings:warnings.length,cache:true,mobile_no_overflow:true}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
