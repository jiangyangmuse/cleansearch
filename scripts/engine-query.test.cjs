const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");

const webRequire = createRequire(path.join(__dirname, "../apps/web/package.json"));
const ts = webRequire("typescript");
const source = fs.readFileSync(path.join(__dirname, "../apps/web/src/engineQuery.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports_ = {};
runInNewContext(output, { exports: exports_ });
const engines = [
  { code: "g", aliases: [] }, { code: "b", aliases: [] },
  { code: "d", aliases: ["ddg"] },
];

for (const [query, expected] of [
  ["python 文档", "python 文档 !b"],
  ["python !g", "python !b"],
  ["明日方舟 ds", "明日方舟 !b"],
  ["python!g", "python !b"],
  ["python g", "python !b"],
  ["python ddg", "python !b"],
  ["python us", "python !b"],
  ["python g b", "python g !b"],
  ["C g", "C g !b"],
  ["ｐｙｔｈｏｎ　！ｇ", "python !b"],
  ['"python g"', '"python g" !b'],
  ['"python g', null],
  ["C", null],
  ["😀", null],
  ["😀😀", "😀😀 !b"],
]) {
  test(`engine switch preserves query: ${JSON.stringify(query)}`, () => {
    assert.equal(exports_.engineQuery(query, "b", engines), expected);
  });
}

test("AI suffix is explicit and follows normal suffix boundaries", () => {
  for (const q of ["明日方舟 ds", "nexon!ds", "明日方舟　！ＤＳ"]) {
    assert.equal(exports_.hasAISuffix(q), true);
  }
  for (const q of ["ds", "nexonds", "C ds", '"nexon ds"']) {
    assert.equal(exports_.hasAISuffix(q), false);
  }
});

test("choosing an engine keeps suffix-like words in a literal query", () => {
  assert.equal(exports_.engineQuery("Nintendo ds", "b", engines, true), "Nintendo ds !b");
  assert.equal(exports_.engineQuery("listen en", "b", engines, true), "listen en !b");
});
