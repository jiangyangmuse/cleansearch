const DEFAULTS = { api: "http://127.0.0.1:8000", token: "" };

function localApi(value) {
  try {
    const url = new URL(value.trim());
    if (url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname) &&
        !url.username && !url.password && url.pathname === "/" && !url.search && !url.hash) return url.origin;
  } catch { /* 地址无效 */ }
  return null;
}

function localRequest(api, path, options = {}) {
  const origin = localApi(api);
  if (!origin) throw new Error("API 地址必须是本机 HTTP 地址（127.0.0.1 或 localhost）");
  return fetch(origin + path, {
    ...options, redirect: "error", credentials: "omit", cache: "no-store", signal: AbortSignal.timeout(5000),
  });
}

function captureRequest(api, token, url, title) {
  return localRequest(api, "/api/bookmarks", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CS-Token": token },
    body: JSON.stringify({ url, title: [...(title || "").trim()].slice(0, 512).join("") || undefined }),
  });
}
