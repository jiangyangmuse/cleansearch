// 设计系统静态检查：旧选择器已清理、间距/圆角 token 存在且被使用。运行：node --test scripts/css-audit.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const css = ["styles.css", "workspace.css"]
  .map((name) => fs.readFileSync(path.join(ROOT, "apps", "web", "src", name), "utf8"))
  .join("\n");

const DEAD = [
  [".summary-toggle", /\.summary-toggle\b/],
  [".layout", /(^|\n)\.layout\s*\{/],
  [".layout__rail", /\.layout__rail/],
  [".layout__results", /\.layout__results/],
  [".layout__side", /\.layout__side/],
  [".ai-search-controls", /\.ai-search-controls/],
  [".metabar__route", /\.metabar__route/],
  [".main--wide", /\.main--wide/],
  [".header__links", /\.header__links/],
  [".header__link--active", /\.header__link--active/],
  [".state__error", /\.state__error\b/],
  [".engines__dot", /\.engines__dot/],
  [".engines__label", /\.engines__label/],
  [".brand__tag", /\.brand__tag/],
  [".brand", /(^|\n)\.brand\s*\{/],
];

test("已删除的旧布局与死样式不再出现", () => {
  const leftovers = DEAD.filter(([, pattern]) => pattern.test(css)).map(([name]) => name);
  assert.deepEqual(leftovers, [], "仍在样式表里：" + leftovers.join(", "));
});

test("间距与圆角 token 已定义", () => {
  for (const token of ["--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6",
    "--radius-sm", "--radius-md", "--radius-lg", "--font-xs", "--font-sm", "--font-md", "--font-base"]) {
    assert.match(css, new RegExp(token + ":"), "缺少 " + token);
  }
});

test("样式实际使用 token 而不是散落魔法数字", () => {
  const spaceUses = (css.match(/var\(--space-[1-6]\)/g) || []).length;
  const radiusUses = (css.match(/var\(--radius-(?:sm|md|lg)\)/g) || []).length;
  assert.ok(spaceUses >= 3, "var(--space-*) 使用过少：" + spaceUses);
  assert.ok(radiusUses >= 1, "var(--radius-*) 尚未使用");
});
