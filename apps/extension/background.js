const DEFAULTS = { api: "http://127.0.0.1:8000", token: "" };
const MENU_ID = "cleansearch-save";

async function saveUrl(url, title) {
  const settings = await chrome.storage.local.get(DEFAULTS);
  if (!settings.token) return { ok: false, message: "缺少 token，请先在扩展弹窗里填写" };
  try {
    const response = await fetch(settings.api.replace(/\/$/, "") + "/api/bookmarks", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CS-Token": settings.token },
      body: JSON.stringify({ url, title: title || undefined }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { ok: false, message: "失败：" + (payload.error?.message || response.status) };
    }
    return { ok: true, message: payload.deduplicated ? "已在书签里" : "已收藏" };
  } catch (error) {
    return { ok: false, message: "连不上 API：" + error.message };
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "收藏到 CleanSearch",
    contexts: ["page", "link"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  const url = info.linkUrl || info.pageUrl || tab?.url;
  if (!url) return;
  const result = await saveUrl(url, tab?.title);
  // 没有稳定通知通道，用 badge 给个即时反馈
  chrome.action.setBadgeText({ text: result.ok ? "✓" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: result.ok ? "#2f6f4f" : "#b3261e" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
});

// 供 popup 与调试复用
self.cleansearchSave = saveUrl;
