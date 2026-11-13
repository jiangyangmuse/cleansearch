import type { AISearchResponse, ApiErrorPayload, EnginePreferences, EngineSettings, SearchResponse } from "./types";
import { notifyBookmarksChanged } from "./bookmarkChanges";

export class ApiError extends Error {
  code: string;
  status: number;
  retryable: boolean;

  constructor(message: string, code: string, status: number, retryable = true) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

export interface SearchBody {
  q: string;
  page?: number;
  region?: string | null;
  opts?: {
    safe?: boolean;
    exact?: boolean;
    summarize?: boolean;
    literal?: boolean;
    fixture?: string | null;
    /** 筛选：时间范围 / 语言 / 站点限定 / 去重强度 */
    time_range?: "day" | "week" | "month" | "year" | null;
    language?: string | null;
    site?: string | null;
    dedupe?: "off" | "normal" | "strict";
  };
}

async function requestSearch<T>(path: string, body: SearchBody, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("无法连接到本机服务，确认 FastAPI 已启动（默认 http://127.0.0.1:8000）", "NETWORK_ERROR", 0);
  }

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    const message = payload?.error?.message ?? `请求失败（HTTP ${response.status}）`;
    const code = payload?.error?.code ?? "HTTP_" + response.status;
    const retryable = payload?.error?.retryable ?? (response.status >= 500 || response.status === 408 || response.status === 429);
    throw new ApiError(message, code, response.status, retryable);
  }

  return (await response.json()) as T;
}

export function search(body: SearchBody, signal?: AbortSignal): Promise<SearchResponse> {
  return requestSearch("/api/search", body, signal);
}

export function searchAI(q: string, signal?: AbortSignal, literal = false): Promise<AISearchResponse> {
  return requestSearch("/api/ai-search", { q, opts: { literal } }, signal);
}


export interface Citation {
  i: number;
  result_id: string;
  title: string;
  url: string;
  domain: string;
  material?: "snippet" | "full" | "truncated";
}

export interface SummaryMeta {
  model: string;
  sources: number;
  mode: string;
  sid: string;
  query: string;
  fetched?: number;
  failed?: number;
  truncated?: number;
  degraded?: boolean;
}

export interface SummaryDone {
  ms: number;
  tokens: number;
  partial: boolean;
}

export interface SummaryHandlers {
  onMeta?: (meta: SummaryMeta) => void;
  onCite?: (cite: Citation) => void;
  onToken?: (text: string) => void;
  onDone?: (done: SummaryDone) => void;
  onError?: (error: { code: string; message: string; retryable: boolean }) => void;
}

/** 读取 /api/summarize 的 SSE 流；signal 中止即停止读取（切换查询时用）。 */
export async function streamSummary(
  sid: string,
  handlers: SummaryHandlers,
  signal?: AbortSignal,
  mode: "fast" | "full" = "fast",
): Promise<void> {
  const response = await fetch(
    `/api/summarize?sid=${encodeURIComponent(sid)}&mode=${mode}`,
    { headers: { Accept: "text/event-stream" }, signal },
  );

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(
      payload?.error?.message ?? `总结请求失败（HTTP ${response.status}）`,
      payload?.error?.code ?? "HTTP_" + response.status,
      response.status,
      payload?.error?.retryable ?? true,
    );
  }
  if (!response.body) throw new ApiError("浏览器不支持流式响应", "NO_STREAM", 0, false);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminated = false;

  const dispatch = (block: string) => {
    signal?.throwIfAborted();
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      return;
    }
    if (event === "meta") handlers.onMeta?.(payload as SummaryMeta);
    else if (event === "cite") handlers.onCite?.(payload as Citation);
    else if (event === "token") handlers.onToken?.((payload as { t: string }).t);
    else if (event === "done") {
      terminated = true;
      handlers.onDone?.(payload as SummaryDone);
    } else if (event === "error") {
      terminated = true;
      handlers.onError?.(payload as { code: string; message: string; retryable: boolean });
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf("\n\n");
    while (index >= 0) {
      dispatch(buffer.slice(0, index));
      buffer = buffer.slice(index + 2);
      index = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) dispatch(buffer);
  if (!terminated) throw new ApiError("总结连接中断，请重试", "SUMMARY_STREAM_INTERRUPTED", 0);
}

async function jsonRequest<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    let code = "HTTP_" + response.status;
    let retryable = response.status >= 500;
    try {
      const payload = (await response.json()) as { detail?: string; error?: ApiErrorPayload["error"] };
      message = typeof payload.detail === "string" ? payload.detail : payload.error?.message ?? message;
      code = payload.error?.code ?? code;
      retryable = payload.error?.retryable ?? retryable;
    } catch {
      /* 保留默认文案 */
    }
    throw new ApiError(message, code, response.status, retryable);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type ModelFeature = "search" | "summary" | "translate";
export type ModelEntry = {
  id: string; label: string; base_url: string; model: string;
  has_key?: boolean; api_key?: string; features: ModelFeature[];
};
export type ModelAssignment = { primary: string | null; fallback: string | null };
export type ModelSettings = {
  revision: number; models: ModelEntry[];
  assignments: Partial<Record<ModelFeature, ModelAssignment>>;
};

function writeJSON<T>(path: string, method: "POST" | "PUT", body: unknown, signal?: AbortSignal) {
  return jsonRequest<T>(path, {
    method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  });
}

export const loadEngineSettings = (signal?: AbortSignal) =>
  jsonRequest<EngineSettings>("/api/settings/engines", { signal, cache: "no-store" });

export const saveEngineSettings = (preferences: EnginePreferences) =>
  writeJSON<EnginePreferences>("/api/settings/engines", "PUT", preferences);

export type ConversationReply = {
  model: string;
  groups: { label: string; query: string; results: import("./types").Result[]; error: string | null }[];
};

export const searchConversation = (message: string, history: { message: string; directions: string[] }[], signal?: AbortSignal) =>
  writeJSON<ConversationReply>("/api/conversation-search", "POST", { message, history }, signal);

export const loadModelSettings = (signal?: AbortSignal) =>
  jsonRequest<ModelSettings>("/api/settings/models", { signal, cache: "no-store" });

export const saveModelSettings = (settings: ModelSettings, signal?: AbortSignal) =>
  writeJSON<ModelSettings>("/api/settings/models", "PUT", {
    ...settings, models: settings.models.map(({ has_key: _hasKey, ...model }) => model),
  }, signal);

export type BatchSummary = {
  pages: { url: string; final_url?: string; title?: string; truncated?: boolean; error?: string }[];
  summary: string; model: string | null;
};

export const summarizePages = (urls: string[], signal?: AbortSignal) =>
  writeJSON<BatchSummary>("/api/pages/summarize", "POST", { urls }, signal);

export const translateText = (text: string, target: string, signal?: AbortSignal) =>
  writeJSON<{ text: string; model: string }>("/api/translate", "POST", { text, target }, signal);

export async function listBookmarks(
  params: { q?: string; group?: number | null; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.group != null) search.set("group", String(params.group));
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const suffix = search.toString();
  return jsonRequest<import("./types").BookmarkListResponse>(`/api/bookmarks${suffix ? "?" + suffix : ""}`, { signal, cache: "no-store" });
}

export async function saveBookmark(body: {
  url: string;
  title?: string;
  group_id?: number | null;
  tags?: string[];
}) {
  const result = await jsonRequest<import("./types").BookmarkSaveResponse>("/api/bookmarks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  notifyBookmarksChanged();
  return result;
}

export interface HealthInfo {
  status: string;
  provider: string;
  web_built: boolean;
  bookmarks: number;
  db_path: string;
  version: string;
}

/** 设置页数据管理用：本机库路径、书签数、版本。 */
export function readHealth(signal?: AbortSignal) {
  return jsonRequest<HealthInfo>("/api/health", { signal, cache: "no-store" });
}

export interface ModelTestResult {
  ok: boolean;
  status: number;
  models?: number;
  model?: string;
  model_listed?: boolean;
  message?: string;
}

/** 测试模型连通性：只请求 /models，不消耗 token、不改配置。 */
export function testModelConnection(id: string, revision: number, signal: AbortSignal) {
  return jsonRequest<ModelTestResult>("/api/settings/models/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, revision }),
    signal,
  });
}

/** 批量查询哪些网址已收藏；返回 {网址: 书签 id}。 */
export async function bookmarkStatus(urls: string[], signal?: AbortSignal): Promise<Record<string, number>> {
  if (urls.length === 0) return {};
  const params = new URLSearchParams();
  urls.slice(0, 40).forEach(url => params.append("urls", url));
  return jsonRequest<Record<string, number>>(`/api/bookmarks/status?${params.toString()}`, { signal });
}

export async function deleteBookmark(id: number) {
  await jsonRequest<void>(`/api/bookmarks/${id}`, { method: "DELETE" });
  notifyBookmarksChanged();
}

export async function removeResultBookmark(id: number, url: string) {
  await jsonRequest<void>(`/api/bookmarks/${id}/result?${new URLSearchParams({ url })}`, { method: "DELETE" });
  notifyBookmarksChanged();
}

export async function moveBookmark(id: number, groupId: number | null) {
  return jsonRequest<import("./types").Bookmark>(`/api/bookmarks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group_id: groupId }),
  });
}

export async function getSearchProvider(signal: AbortSignal): Promise<string> {
  const health = await jsonRequest<{ provider: string }>("/api/health", { signal });
  return health.provider;
}

export async function getEngines(signal?: AbortSignal) {
  return jsonRequest<import("./types").EnginesResponse>("/api/engines", { signal, cache: "no-store" });
}

export async function createGroup(name: string) {
  return jsonRequest<import("./types").BookmarkGroup>("/api/groups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export interface PageSummary {
  url: string;
  final_url: string;
  title: string;
  byline: string | null;
  published: string | null;
  word_count: number;
  read_minutes: number;
  content_hash: string;
  extractor: string;
  truncated: boolean;
  summary: { one_liner: string; bullets: string[]; key_data: unknown[]; caveats: string[] };
  key_data: { label: string; value: string }[];
  anchors: { i: number; text: string }[];
  summary_text: string;
  model: string;
}

export async function summarizePage(url: string, signal?: AbortSignal) {
  return jsonRequest<PageSummary>("/api/page/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal,
  });
}

export async function checkDeadLinks(ids?: number[]) {
  return jsonRequest<{ checked: number; dead: number; unknown: number }>(
    "/api/bookmarks/check",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids ? { ids, limit: Math.max(1, ids.length) } : {}),
    },
  );
}

export function faviconUrl(host: string | null | undefined): string | null {
  if (!host) return null;
  return `/api/favicon?host=${encodeURIComponent(host)}`;
}

export interface ImportJob {
  id: string;
  state: "running" | "done" | "error";
  processed: number;
  total: number;
  created: number;
  skipped: number;
  groups_created: number;
  error: string;
}

export async function startImportJob(file: File): Promise<{ id: string }> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/bookmarks/import/jobs", { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new ApiError(detail?.error?.message ?? "导入任务创建失败", "IMPORT_FAILED", response.status);
  }
  return response.json();
}

export async function importJobStatus(id: string): Promise<ImportJob> {
  const response = await fetch(`/api/bookmarks/import/jobs/${id}`, { cache: "no-store" });
  if (!response.ok) throw new ApiError("导入任务不存在", "IMPORT_JOB_MISSING", response.status);
  return response.json();
}

export async function importBookmarks(file: File) {
  const form = new FormData();
  form.append("file", file);
  const result = await jsonRequest<import("./types").ImportResult>("/api/bookmarks/import", {
    method: "POST",
    body: form,
  });
  notifyBookmarksChanged();
  return result;
}
