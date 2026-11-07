const $ = (id) => document.getElementById(id);
const DEFAULTS = { api: "http://127.0.0.1:8000", token: "" };
let tabUrl = "";

function localApi(value) {
  try {
    const url = new URL(value.trim());
    if (url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname) &&
        !url.username && !url.password && url.pathname === "/" && !url.search && !url.hash) {
      return url.origin;
    }
  } catch { /* 输入不合法 */ }
  return null;
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  $("api").value = stored.api || DEFAULTS.api;
  $("token").value = stored.token || "";
}

async function loadTab() {
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch {
    return null; // 权限或上下文受限时留空，用户可以直接粘贴地址
  }
  tabUrl = tab?.url || "";
  // 输入框展示将要保存的地址；用户也能在这里改成别的页面
  $("url").value = tabUrl;
  $("title").value = tab?.title || "";
}

$("save-settings").addEventListener("click", async () => {
  const api = localApi($("api").value);
  if (!api) {
    $("status").textContent = "API 地址必须是本机 HTTP 地址（127.0.0.1 或 localhost）";
    return;
  }
  try {
    await chrome.storage.local.set({ api, token: $("token").value.trim() });
    $("api").value = api;
    $("status").textContent = "设置已保存";
  } catch {
    $("status").textContent = "无法保存连接设置";
  }
});

$("save").addEventListener("click", async () => {
  const api = localApi($("api").value);
  const token = $("token").value.trim();
  const target = ($("url").value || tabUrl).trim();
  if (!/^https?:\/\//i.test(target)) {
    $("status").textContent = "只能收藏 http(s) 页面";
    return;
  }
  if (!api) {
    $("status").textContent = "API 地址必须是本机 HTTP 地址（127.0.0.1 或 localhost）";
    return;
  }
  if (!token) {
    $("status").textContent = "先在下方填写 /tools 页面里的 token";
    return;
  }
  $("save").disabled = true;
  $("status").textContent = "保存中…";
  try {
    const response = await fetch(api + "/api/bookmarks", {
      method: "POST",
      redirect: "error",
      credentials: "omit",
      signal: AbortSignal.timeout(5000),
      headers: { "Content-Type": "application/json", "X-CS-Token": token },
      body: JSON.stringify({ url: target, title: [...$("title").value.trim()].slice(0, 512).join("") || undefined }),
    });
    const payload = await response.json().catch(() => ({}));
    $("status").textContent = response.ok
      ? payload.deduplicated
        ? "已在书签里"
        : "已收藏"
      : "失败：" + (payload.error?.message || (typeof payload.detail === "string" ? payload.detail : response.status));
  } catch (error) {
    $("status").textContent = "连不上 API：" + error.message;
  } finally {
    $("save").disabled = false;
  }
});

Promise.all([loadTab(), loadSettings()])
  .then(() => { $("save").disabled = false; $("save-settings").disabled = false; })
  .catch(() => { $("status").textContent = "无法读取当前页面或连接设置"; });