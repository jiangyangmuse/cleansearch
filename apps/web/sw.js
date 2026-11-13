/* Vite 注入本次构建的内容版本及完整壳资源表。 */
const CACHE = `cs-shell-${"__CS_BUILD__"}`;
const SHELL = "__CS_PRECACHE__";
const INDEX_HASH = "__CS_INDEX_HASH__";
const ROUTES = new Set(["/", "/index.html", "/bookmarks", "/s", "/settings", "/tools", "/r"]);
const STATIC = new Set(SHELL);
const NAV_TIMEOUT_MS = 3500;

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const responses = await Promise.all(SHELL.map(async path => {
      const request = new Request(path, { cache: "reload" });
      const response = await fetch(request);
      if (!response.ok || response.redirected ||
          (path.startsWith("/assets/") && response.headers.get("content-type")?.includes("text/html"))) {
        throw new Error(`预缓存失败 ${path}`);
      }
      if (path === "/index.html") {
        const digest = await crypto.subtle.digest("SHA-256", await response.clone().arrayBuffer());
        const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
        if (hex !== INDEX_HASH) throw new Error("预缓存首页与 Service Worker 的构建版本不一致");
      }
      return [request, response];
    }));
    await Promise.all(responses.map(([request, response]) => cache.put(request, response)));
  })().catch(async error => {
    await caches.delete(CACHE);
    throw error;
  }));
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => key !== CACHE && /^cs-(?:shell|assets)-/.test(key))
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", event => {
  if (event.data === "SKIP_WAITING") event.waitUntil(self.skipWaiting());
});

async function networkFirstNavigation(request, pathname) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NAV_TIMEOUT_MS);
  try {
    const response = await fetch(request, { cache: "no-store", signal: controller.signal });
    if (response.status < 500) return response;
  } catch {
    // 网络不可达或已超时。
  } finally {
    clearTimeout(timer);
  }
  const cache = await caches.open(CACHE);
  const shell = ROUTES.has(pathname) ? await cache.match("/index.html") : undefined;
  return shell || await cache.match("/offline.html") || Response.error();
}

async function shareTarget(request) {
  const target = new URL("/bookmarks", self.location.origin);
  const params = new URLSearchParams({ shared: "1" });
  try {
    const form = await request.formData();
    for (const [name, limit] of [["url", 2048], ["text", 8192], ["title", 1024]]) {
      const value = form.get(name);
      if (typeof value === "string" && value) params.set(name, name === "url" && value.length > limit ? "" : value.slice(0, limit));
    }
    if (form.getAll("files").some(value => value instanceof File && value.size > 0)) params.set("files", "1");
  } catch {
    // 无法读取的表单仍进入书签页显示反馈。
  }
  // 分享数据只在片段中传给书签页，后续 GET 不会把它发给服务器。
  target.hash = params.toString();
  return Response.redirect(target, 303);
}

self.addEventListener("fetch", event => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  const pathname = url.pathname.replace(/\/+$/, "") || "/";
  if (request.method === "POST" && request.mode === "navigate" && pathname === "/share") {
    event.respondWith(shareTarget(request));
    return;
  }
  if (request.method !== "GET") return;
  if (pathname === "/api" || pathname.startsWith("/api/") || pathname === "/go" || pathname.startsWith("/go/")) {
    event.respondWith(fetch(request, { cache: "no-store" }));
    return;
  }
  if (request.mode === "navigate" && pathname !== "/offline.html") {
    event.respondWith(networkFirstNavigation(request, pathname));
  } else if (STATIC.has(url.pathname)) {
    event.respondWith(caches.open(CACHE).then(async cache => await cache.match(url.pathname) || fetch(request)));
  }
});
