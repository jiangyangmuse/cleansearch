// 扩展静态检查：manifest 字段、图标尺寸、页面引用是否齐全。运行：node --test scripts/extension.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const EXT = path.join(ROOT, "apps", "extension");
const manifest = JSON.parse(fs.readFileSync(path.join(EXT, "manifest.json"), "utf8"));

function pngSize(file) {
  const buffer = fs.readFileSync(file);
  assert.equal(buffer.subarray(1, 4).toString("ascii"), "PNG", file + " 不是 PNG");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

function exists(relative) {
  return fs.existsSync(path.join(EXT, relative));
}

test("manifest 是 MV3 且带图标与动作图标", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.ok(manifest.name && manifest.version && manifest.description);
  for (const size of ["16", "32", "48", "128"]) {
    assert.ok(manifest.icons[size], "缺少 icons " + size);
    assert.ok(manifest.action.default_icon[size], "缺少 default_icon " + size);
    assert.equal(manifest.icons[size], manifest.action.default_icon[size]);
  }
});

test("图标文件存在且像素尺寸与声明一致", () => {
  for (const size of [16, 32, 48, 128]) {
    const relative = manifest.icons[String(size)];
    assert.ok(exists(relative), "缺少文件 " + relative);
    const { width, height } = pngSize(path.join(EXT, relative));
    assert.equal(width, size);
    assert.equal(height, size);
  }
});

test("commands 提供收藏当前页快捷键", () => {
  const command = manifest.commands?.["save-page"];
  assert.ok(command, "缺少 save-page 命令");
  assert.equal(command.suggested_key.default, "Ctrl+Shift+S");
  assert.equal(command.suggested_key.mac, "Command+Shift+S");
  const background = fs.readFileSync(path.join(EXT, "background.js"), "utf8");
  assert.match(background, /chrome\.commands\.onCommand/);
  assert.match(background, /saveActiveTab/);
});

test("omnibox 关键字是 cs 并在后台打开搜索", () => {
  assert.equal(manifest.omnibox?.keyword, "cs");
  const background = fs.readFileSync(path.join(EXT, "background.js"), "utf8");
  assert.match(background, /chrome\.omnibox\.onInputEntered/);
  assert.match(background, /searchParams\.set\("q", query\)/);
});

test("options 页与 popup 引用的文件都存在", () => {
  assert.equal(manifest.options_ui?.page, "options.html");
  for (const file of ["connection.js", "options.html", "options.js", "options.css", "popup.html", "popup.js", "popup.css"]) {
    assert.ok(exists(file), "缺少 " + file);
  }
  const optionsHtml = fs.readFileSync(path.join(EXT, "options.html"), "utf8");
  assert.match(optionsHtml, /options\.js/);
  assert.match(optionsHtml, /测试连接/);
  const popupHtml = fs.readFileSync(path.join(EXT, "popup.html"), "utf8");
  assert.match(popupHtml, /open-bookmarks/);
  assert.match(popupHtml, /open-options/);
});

test("右键菜单覆盖页面、链接与选中文本", () => {
  const background = fs.readFileSync(path.join(EXT, "background.js"), "utf8");
  assert.match(background, /contexts: \["page", "link", "selection"\]/);
  assert.match(background, /info\.selectionText/);
});

test("后台回调使用触发标签、拒绝远程配置并遵循 omnibox 打开方式", async () => {
  const handlers = {};
  const calls = [];
  const storage = { api: "http://127.0.0.1:8123", token: "fixture-token" };
  const listener = name => ({ addListener: fn => { handlers[name] = fn; } });
  const sandbox = vm.createContext({ URL, AbortSignal, self: {},
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ deduplicated: false }) };
    },
    chrome: {
      storage: { local: { get: async () => storage } },
      runtime: { onInstalled: listener("installed") },
      commands: { onCommand: listener("command") },
      omnibox: { onInputEntered: listener("omnibox") },
      contextMenus: { onClicked: listener("contextMenu") },
      action: { setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}, setTitle: async () => {} },
      tabs: { update: async options => calls.push({ update: options }), create: async options => calls.push({ create: options }) },
    },
  });
  sandbox.importScripts = name => vm.runInContext(fs.readFileSync(path.join(EXT, name), "utf8"), sandbox);
  vm.runInContext(fs.readFileSync(path.join(EXT, "background.js"), "utf8"), sandbox);

  await handlers.command("save-page", { id: 7, url: "https://example.test/command", title: "快捷收藏" });
  await handlers.contextMenu({ menuItemId: "cleansearch-save", linkUrl: "https://example.test/link", selectionText: "选中文本" },
    { id: 7, url: "https://example.test/page", title: "页面" });
  await handlers.omnibox("空 格&字符", "currentTab");
  await handlers.omnibox("python", "newBackgroundTab");
  storage.api = "https://example.test";
  await handlers.command("save-page", { id: 7, url: "https://example.test/blocked", title: "拒绝外部 API" });

  assert.equal(calls.length, 4);
  assert.deepEqual(JSON.parse(calls[0].options.body), { url: "https://example.test/command", title: "快捷收藏" });
  assert.deepEqual(JSON.parse(calls[1].options.body), { url: "https://example.test/link", title: "选中文本 — 页面" });
  assert.equal(calls[0].url, "http://127.0.0.1:8123/api/bookmarks");
  assert.equal(calls[0].options.redirect, "error");
  assert.equal(new URL(calls[2].update.url).searchParams.get("q"), "空 格&字符");
  assert.equal(calls[3].create.active, false);
});
