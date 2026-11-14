import { useSyncExternalStore } from "react";
import { readHealth, type HealthInfo } from "./api";
import { setVitalsEnabled } from "./perf";

/**
 * 前端依赖的服务能力。旧服务（新 dist + 旧 API）会缺这些，
 * 表现为 404/405 或参数被静默忽略，所以启动时先核对再决定界面。
 */
export const REQUIRED_CAPABILITIES = [
  "filters", "bookmark_status", "vitals", "model_test", "opensearch",
] as const;

export type Capability = typeof REQUIRED_CAPABILITIES[number];

export const CAPABILITY_LABELS: Record<Capability, string> = {
  filters: "搜索筛选",
  bookmark_status: "批量收藏状态",
  vitals: "性能上报",
  model_test: "模型连通性测试",
  opensearch: "浏览器搜索集成",
};

/** 当前前端所要求的契约版本；服务端 api_version 低于它即视为混版。 */
export const REQUIRED_API_VERSION = 2;

export type ServerState =
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "ok"; health: HealthInfo }
  | { kind: "outdated"; health: HealthInfo; missing: Capability[] };

export function serverStateFrom(health: HealthInfo | null): ServerState {
  if (!health) return { kind: "offline" };
  const version = typeof health.api_version === "number" ? health.api_version : 0;
  const capabilities = health.capabilities ?? {};
  const missing = REQUIRED_CAPABILITIES.filter(name => capabilities[name] !== true);
  if (version < REQUIRED_API_VERSION) return { kind: "outdated", health, missing: [...REQUIRED_CAPABILITIES] };
  return missing.length ? { kind: "outdated", health, missing } : { kind: "ok", health };
}

/** 等服务确认契约后才调用依赖该能力的接口。 */
export function capabilityReady(state: ServerState, name: Capability): boolean {
  return state.kind === "ok" || (state.kind === "outdated" && !state.missing.includes(name));
}

let probe: AbortController | null = null;
let resolved: ServerState = { kind: "loading" };
const listeners = new Set<() => void>();

function publish(next: ServerState): void {
  resolved = next;
  setVitalsEnabled(capabilityReady(next, "vitals"));
  listeners.forEach(listener => listener());
}

export function refreshServerState(): void {
  probe?.abort();
  const request = new AbortController();
  probe = request;
  const timeout = window.setTimeout(() => request.abort(), 5000);
  void readHealth(request.signal)
    .catch(() => null)
    .then(health => {
      if (probe !== request) return;
      probe = null;
      publish(serverStateFrom(health));
    })
    .finally(() => window.clearTimeout(timeout));
}

export function watchServerState(): void {
  const offline = () => {
    probe?.abort();
    probe = null;
    publish({ kind: "offline" });
  };
  window.addEventListener("offline", offline);
  window.addEventListener("online", refreshServerState);
  window.addEventListener("pageshow", event => {
    if (event.persisted && navigator.onLine) refreshServerState();
  });
  if (navigator.onLine) refreshServerState();
  else offline();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useServerState(): ServerState {
  return useSyncExternalStore(subscribe, () => resolved);
}
