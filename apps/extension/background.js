importScripts("connection.js");
const MENU_ID = "cleansearch-save";

async function readSettings() {
  return chrome.storage.local.get(DEFAULTS);
}

async function showResult(result, tabId) {
  if (typeof tabId !== "number") return;
  await Promise.all([
    chrome.action.setBadgeText({ tabId, text: result.ok ? "✓" : "!" }),
    chrome.action.setBadgeBackgroundColor({ tabId, color: result.ok ? "#2f6f4f" : "#b3261e" }),
    chrome.action.setTitle({ tabId, title: result.message }),
  ]).catch(() => {}); // 用户可能已关闭该标签页。
}

async function saveUrl(url, title) {
  const settings = await readSettings();
  if (!settings.token) return { ok: false, message: "缺少 token，请先在扩展设置里填写" };
  try {
    const response = await captureRequest(settings.api, settings.token, url, title);
    const payload = await response.json();
    if (!response.ok || typeof payload.deduplicated !== "boolean") {
      return { ok: false, message: "收藏失败：" + (payload.error?.message || payload.detail || response.status) };
    }
    return { ok: true, message: payload.deduplicated ? "已在书签里" : "已收藏" };
  } catch (error) {
    return { ok: false, message: "连不上 API：" + error.message };
  }
}

async function saveActiveTab(tab) {
  const url = tab?.url;
  const result = url && /^https?:\/\//i.test(url) ? await saveUrl(url, tab.title)
    : { ok: false, message: "当前页不是 HTTP(S) 页面" };
  await showResult(result, tab?.id);
  return result;
}

function createMenus() {
  // 重复创建会报错，先清掉旧的
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_ID,
      title: "收藏到 CleanSearch",
      contexts: ["page", "link", "selection"],
    }, () => { void chrome.runtime.lastError; });
  });
}

chrome.runtime.onInstalled.addListener(createMenus);

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command !== "save-page") return;
  try { await saveActiveTab(tab); }
  catch { await showResult({ ok: false, message: "无法读取扩展设置" }, tab?.id); }
});

// 地址栏关键字 cs：回车后用本机前端搜索
chrome.omnibox.onInputEntered.addListener(async (text, disposition) => {
  const query = text.trim();
  try {
    const settings = await readSettings();
    const url = new URL("/", localApi(settings.api) || DEFAULTS.api);
    if (query) url.searchParams.set("q", query);
    if (disposition === "currentTab") await chrome.tabs.update({ url: url.href });
    else await chrome.tabs.create({ url: url.href, active: disposition !== "newBackgroundTab" });
  } catch { /* 标签页已关闭或设置不可读。 */ }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  const url = info.linkUrl || info.pageUrl || tab?.url;
  if (!url) return;
  // 选中文本作为标题前缀，便于在书签列表里认出这段内容
  const selection = (info.selectionText || "").trim();
  const title = selection ? `${selection.slice(0, 80)} — ${tab?.title ?? ""}`.trim() : tab?.title;
  try { await showResult(await saveUrl(url, title), tab?.id); }
  catch { await showResult({ ok: false, message: "无法读取扩展设置" }, tab?.id); }
});

// 供 popup 与调试复用
self.cleansearchSave = saveUrl;
self.cleansearchSaveActiveTab = saveActiveTab;
