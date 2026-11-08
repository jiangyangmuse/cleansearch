import type { ApiErrorPayload, SearchResponse } from "./types";

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
  opts?: { safe?: boolean; exact?: boolean; summarize?: boolean; fixture?: string | null };
}

export async function search(body: SearchBody, signal?: AbortSignal): Promise<SearchResponse> {
  let response: Response;
  try {
    response = await fetch("/api/search", {
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
    const retryable = payload?.error?.retryable ?? true;
    throw new ApiError(message, code, response.status, retryable);
  }

  return (await response.json()) as SearchResponse;
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
    try {
      const payload = (await response.json()) as { detail?: string; error?: { message: string } };
      message = typeof payload.detail === "string" ? payload.detail : payload.error?.message ?? message;
    } catch {
      /* 保留默认文案 */
    }
    throw new ApiError(message, "HTTP_" + response.status, response.status, response.status >= 500);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

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
  return jsonRequest<import("./types").BookmarkListResponse>(`/api/bookmarks${suffix ? "?" + suffix : ""}`, { signal });
}

export async function saveBookmark(body: {
  url: string;
  title?: string;
  group_id?: number | null;
  tags?: string[];
}) {
  return jsonRequest<import("./types").BookmarkSaveResponse>("/api/bookmarks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteBookmark(id: number) {
  return jsonRequest<void>(`/api/bookmarks/${id}`, { method: "DELETE" });
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
  return jsonRequest<import("./types").EnginesResponse>("/api/engines", { signal });
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

export async function summarizePage(url: string) {
  return jsonRequest<PageSummary>("/api/page/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
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
  return jsonRequest<import("./types").ImportResult>("/api/bookmarks/import", {
    method: "POST",
    body: form,
  });
}