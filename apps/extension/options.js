const $ = (id) => document.getElementById(id);

function setStatus(text, tone = "ok") {
  $("status").textContent = text;
  $("status").dataset.tone = tone;
}

async function load() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  $("api").value = stored.api || DEFAULTS.api;
  $("token").value = stored.token || "";
  $("open-tools").href = (localApi(stored.api) || DEFAULTS.api) + "/tools";
}

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const api = localApi($("api").value);
  if (!api) { setStatus("API 地址必须是本机 HTTP 地址（127.0.0.1 或 localhost）", "error"); return; }
  try {
    const existing = await chrome.storage.local.get(DEFAULTS);
    const token = $("token").value.trim() || existing.token || "";
    await chrome.storage.local.set({ api, token });
    $("api").value = api;
    $("open-tools").href = api + "/tools";
    setStatus("设置已保存");
  } catch { setStatus("无法保存设置", "error"); }
});

$("test").addEventListener("click", async () => {
  const api = localApi($("api").value);
  if (!api) { setStatus("API 地址必须是本机 HTTP 地址（127.0.0.1 或 localhost）", "error"); return; }
  $("test").disabled = true;
  setStatus("正在测试…");
  try {
    const response = await localRequest(api, "/api/health");
    if (!response.ok) { setStatus(`连接失败：HTTP ${response.status}`, "error"); return; }
    const payload = await response.json();
    if (payload.status !== "ok" || typeof payload.provider !== "string") {
      setStatus("响应不是 CleanSearch 健康状态", "error");
      return;
    }
    const token = $("token").value.trim() || (await chrome.storage.local.get(DEFAULTS)).token;
    if (!token) { setStatus(`服务正常（${payload.provider}），但还没填 token`, "error"); return; }
    // 用一次带 token 的写动作验证权限：只发一个会被拒绝的坏网址，不会真的写入
    const probe = await captureRequest(api, token, "not-a-url");
    if (probe.status === 401 || probe.status === 403) { setStatus("token 无效或没有添加权限", "error"); return; }
    const probeBody = await probe.json().catch(() => null);
    if (probe.status !== 400 || probeBody?.detail !== "只支持 http(s) 链接") {
      setStatus(`服务响应异常（HTTP ${probe.status}），无法确认 token 权限`, "error");
      return;
    }
    setStatus(`连接正常（${payload.provider}，${payload.version}），token 可用`);
  } catch (error) {
    setStatus("连不上 API：" + error.message, "error");
  } finally {
    $("test").disabled = false;
  }
});

load().catch(() => setStatus("无法读取设置", "error"));
