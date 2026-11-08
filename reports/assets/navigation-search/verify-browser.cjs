const path=require("path");
const {chromium}=require(path.resolve("apps/web/node_modules/playwright"));
const fs=require("fs");
(async()=>{
 const browser=await chromium.launch();
 try {
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  await page.goto("http://127.0.0.1:18171/?q=deepseek",{waitUntil:"networkidle"});
  const home=page.locator('a[href="https://www.deepseek.com/en/"]').first();
  await home.waitFor({state:"visible",timeout:30000});
  await home.scrollIntoViewIfNeeded();
  const evidence={query:"deepseek",home_url:await home.getAttribute("href"),title:await home.innerText(),visible:await home.isVisible(),browser_version:browser.version(),source:"live Serper fallback; SearXNG unavailable"};
  await page.screenshot({path:"reports/assets/navigation-search/after-ui.png"});
  fs.writeFileSync("reports/assets/navigation-search/browser.json",JSON.stringify(evidence,null,2)+"\n");
  console.log(JSON.stringify(evidence));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
