// Run against a real SearXNG-backed API with an enabled, preferably isolated cache.
const BASE = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const Q = process.env.CS_FILTER_QUERY || "python";
let passed = 0;
let failures = 0;

function check(name, ok, detail = "") {
  if (ok) passed++;
  else failures++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " · " + detail : ""}`);
}

async function post(opts, q = Q) {
  const response = await fetch(BASE + "/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q, opts }),
    signal: AbortSignal.timeout(45000),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`HTTP ${response.status} ${body.error?.code ?? ""}`);
  const { meta, groups, official } = body;
  return { meta, results: [...groups.strong, ...groups.related, ...groups.weak, ...(official?.entries ?? [])] };
}

async function run() {
  const base = await post({});
  check("真实 SearXNG 基准有结果", base.meta.provider === "searxng" && base.results.length > 0,
    `provider=${base.meta.provider} total=${base.results.length}`);
  const target = "docs.python.org";
  const site = await post({ site: target });
  const hosts = [...new Set(site.results.map(item => new URL(item.url).hostname))];
  check("站点筛选仅返回目标域或子域（含官方区）", site.meta.filters?.site === target && hosts.length > 0 &&
    hosts.every(host => host === target || host.endsWith("." + target)), `hosts=${hosts.join(",")}`);
  const directory = await post({ site: "no-match.invalid" }, "deepseek");
  check("站外官方目录不会补回零结果", directory.meta.status === "empty" && !directory.results.length);

  const week = await post({ time_range: "week" });
  check("一周筛选回显，允许真实零结果", week.meta.filters?.time_range === "week",
    `total=${week.results.length} cached=${week.meta.cached}`);
  const repeat = await post({ time_range: "week" });
  check("同筛选重复命中缓存", repeat.meta.cached === true && repeat.meta.filters?.time_range === "week");
  const month = await post({ time_range: "month" });
  check("不同筛选返回对应条件", month.meta.filters?.time_range === "month", `cached=${month.meta.cached}`);
  const lang = await post({ language: "en" });
  check("语言筛选回显", lang.meta.filters?.language === "en", `total=${lang.results.length}`);
  const strict = await post({ dedupe: "strict" });
  const ordinary = strict.results.filter(item => !item.role);
  const titles = ordinary.map(item => item.title.trim().toLowerCase().replace(/\s+/g, " "));
  check("严格去重的普通结果无重复标题", strict.meta.filters?.dedupe === "strict" &&
    new Set(titles).size === titles.length, `total=${ordinary.length}`);
  const off = await post({ dedupe: "off" });
  check("关闭去重回显且合并计数为零", off.meta.filters?.dedupe === "off" && off.meta.filtered?.dup === 0,
    `total=${off.results.length}`);
}

run().catch(error => check("真实筛选请求", false, error.message)).finally(() => {
  console.log(failures ? `FAILED ${failures} (${passed} passed)` : `ALL PASS (${passed})`);
  process.exitCode = failures ? 1 : 0;
});
