// 搜索 URL 契约单测：往返、非法值归一、筛选差异比较。运行：node --test scripts/url-state.test.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");

const webRequire = createRequire(path.join(__dirname, "../apps/web/package.json"));
const ts = webRequire("typescript");
const source = fs.readFileSync(path.join(__dirname, "../apps/web/src/urlState.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports_ = {};
// 浏览器 URL 内建类要显式注入，源码默认参数才会拿到 window.location.search 的同构用法。
runInNewContext(output, { exports: exports_, URLSearchParams, URL });

// 源码在独立 vm 上下文里执行，对象原型与主上下文不同；比较前先转成本地纯数据。
const plain = (value) => JSON.parse(JSON.stringify(value));

const base = {
  q: "python 文档", literal: false, page: 1, category: "all",
  range: "", lang: "", site: "", dedupe: "normal",
};

test("完整筛选状态写进地址栏并能原样读回", () => {
  const state = {
    ...base, q: "python asyncio", literal: true, page: 3, category: "video",
    range: "week", lang: "zh-CN", site: "docs.python.org", dedupe: "strict",
  };
  const url = exports_.searchUrl(state);
  assert.equal(url, "/?q=python+asyncio&literal=1&page=3&category=video&range=week&lang=zh-CN&site=docs.python.org&dedupe=strict");
  assert.deepEqual(plain(exports_.readUrlState(new URL(url, "http://x").search)), state);
});

test("默认值不进地址栏，也不会在回读时变成非法态", () => {
  const url = exports_.searchUrl(base);
  assert.equal(url, "/?q=python+%E6%96%87%E6%A1%A3");
  assert.deepEqual(plain(exports_.readUrlState(new URL(url, "http://x").search)), base);
  assert.deepEqual(plain(exports_.readUrlState("")), { ...base, q: "", category: "all" });
});

test("非法 page / range / dedupe / lang / site 一律归一", () => {
  const read = (search) => exports_.readUrlState(search);
  for (const page of ["0", "11", "abc", "2.5", "-1", ""]) {
    assert.equal(read("?q=a&page=" + encodeURIComponent(page)).page, 1, "page=" + page);
  }
  assert.equal(read("?q=a&page=10").page, 10);
  assert.equal(read("?q=a&range=decade").range, "");
  assert.equal(read("?q=a&range=week").range, "week");
  assert.equal(read("?q=a&dedupe=maybe").dedupe, "normal");
  assert.equal(read("?q=a&dedupe=off").dedupe, "off");
  assert.equal(read("?q=a&lang=ZH-cn").lang, "zh-CN");
  assert.equal(read("?q=a&lang=zh_cn").lang, "");
  assert.equal(read("?q=a&lang=toolong1").lang, "");
  assert.equal(read("?q=a&site=HTTPS://WWW.Example.com/path").site, "example.com");
  assert.equal(read("?q=a&site=WWW.www.example.com.").site, "example.com");
  assert.equal(read("?q=a&site=not%20a%20domain").site, "");
  assert.equal(read("?q=a&site=localhost").site, "");
});

test("filtersFromUrl 与同一状态的筛选比较一致", () => {
  const state = exports_.readUrlState("?q=a&range=week&lang=ja&site=example.com&dedupe=strict");
  const filters = exports_.filtersFromUrl(state);
  assert.deepEqual(plain(filters), { timeRange: "week", language: "ja", site: "example.com", dedupe: "strict" });
  assert.equal(exports_.sameFilters(filters, exports_.filtersFromUrl(state)), true);
});

test("筛选差异能逐项识别", () => {
  const baseFilters = exports_.DEFAULT_FILTERS;
  assert.equal(exports_.sameFilters(baseFilters, { ...baseFilters }), true);
  for (const patch of [{ timeRange: "day" }, { language: "en" }, { site: "example.com" }, { dedupe: "off" }, { dedupe: "strict" }]) {
    assert.equal(exports_.sameFilters(baseFilters, { ...baseFilters, ...patch }), false, JSON.stringify(patch));
  }
  assert.equal(exports_.sameFilters({ ...baseFilters, site: "example.com" }, { ...baseFilters, site: "example.com" }), true);
});

test("withFilters 把筛选合进 URL 状态且不丢查询身份", () => {
  const merged = exports_.withFilters(
    { q: "rust", literal: true, page: 2, category: "download" },
    { timeRange: "month", language: "", site: "crates.io", dedupe: "off" },
  );
  assert.deepEqual(plain(merged), {
    q: "rust", literal: true, page: 2, category: "download",
    range: "month", lang: "", site: "crates.io", dedupe: "off",
  });
  assert.equal(exports_.searchUrl(merged), "/?q=rust&literal=1&page=2&category=download&range=month&site=crates.io&dedupe=off");
  assert.deepEqual(plain(exports_.filtersFromUrl(exports_.readUrlState(new URL(exports_.searchUrl(merged), "http://x").search))),
    { timeRange: "month", language: "", site: "crates.io", dedupe: "off" });
});

test("请求体筛选片段：空值发 null，去重保留当前档位", () => {
  assert.deepEqual(plain(exports_.filterOptions(exports_.DEFAULT_FILTERS)),
    { time_range: null, language: null, site: null, dedupe: "normal" });
  assert.deepEqual(plain(exports_.filterOptions({ timeRange: "week", language: "en", site: "example.com", dedupe: "strict" })),
    { time_range: "week", language: "en", site: "example.com", dedupe: "strict" });
});
