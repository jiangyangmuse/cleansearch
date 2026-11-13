import { onCLS, onINP, onLCP, onTTFB } from "web-vitals";

const ENDPOINT = "/api/metrics/vitals";
const ROUTES = new Set(["/", "/r", "/bookmarks", "/settings", "/s", "/tools"]);
const state: Partial<Record<"lcp" | "cls" | "inp" | "ttfb" | "search_ms" | "panel_ms", number>> = {};
let panelStart: number | undefined;
let lastSent = "";
let queued: AbortController | undefined;
let timer: number | undefined;
let schedule: () => void = () => {};

const request = (body: string): RequestInit => ({
  method: "POST", body, headers: { "Content-Type": "application/json" },
});

function flush(allowFallback = false): void {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  if (!Object.keys(state).length) return;
  const body = JSON.stringify({ path: ROUTES.has(path) ? path : "/", ...state });
  if (body === lastSent) return;
  const later = (globalThis as typeof globalThis & {
    fetchLater?: (url: string, options: RequestInit) => { readonly activated: boolean };
  }).fetchLater;
  try {
    if (later) {
      queued?.abort();
      queued = new AbortController();
      later(ENDPOINT, { ...request(body), signal: queued.signal });
      lastSent = body;
      return;
    }
  } catch { queued = undefined; }
  if (!allowFallback) return;
  try {
    if (navigator.sendBeacon?.(ENDPOINT, new Blob([body], { type: "application/json" }))) {
      lastSent = body;
      return;
    }
  } catch { /* 浏览器可能拒绝 beacon。 */ }
  lastSent = body;
  void fetch(ENDPOINT, { ...request(body), keepalive: true }).catch(() => {
    if (lastSent === body) lastSent = "";
  });
}

export function initPerf(): void {
  schedule = () => {
    window.clearTimeout(timer);
    if (document.visibilityState !== "hidden") timer = window.setTimeout(flush, 250);
  };
  const update = (key: "lcp" | "cls" | "inp" | "ttfb", value: number) => {
    if (!Number.isFinite(value) || value < 0 || value > (key === "cls" ? 100 : 600_000)) return;
    const scale = key === "cls" ? 1000 : 10;
    state[key] = Math.round(value * scale) / scale;
    schedule();
  };
  onLCP(metric => update("lcp", metric.value), { reportAllChanges: true });
  onCLS(metric => update("cls", metric.value), { reportAllChanges: true });
  onINP(metric => update("inp", metric.value), { reportAllChanges: true });
  onTTFB(metric => update("ttfb", metric.value));
  const flushHidden = () => {
    if (document.visibilityState !== "hidden") return;
    window.clearTimeout(timer);
    // Let web-vitals collect the final buffered entries before the snapshot.
    window.setTimeout(() => flush(true), 0);
  };
  document.addEventListener("visibilitychange", flushHidden);
  window.addEventListener("pagehide", () => flush(true));
  window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    window.clearTimeout(timer);
    for (const key of Object.keys(state) as (keyof typeof state)[]) delete state[key];
    queued = undefined;
    lastSent = "";
    panelStart = undefined;
  });
}

export function markSearchEnd(startedAt: number): void {
  state.search_ms = Math.round((performance.now() - startedAt) * 10) / 10;
  schedule();
}

export function markPanelOpen(): void {
  panelStart = performance.now();
}

export function markPanelReady(): void {
  if (panelStart === undefined) return;
  state.panel_ms = Math.round((performance.now() - panelStart) * 10) / 10;
  panelStart = undefined;
  schedule();
}
