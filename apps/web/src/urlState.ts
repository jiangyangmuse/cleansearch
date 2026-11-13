/** 搜索页 URL 契约：q / literal / page / category / 筛选条件都可分享，前进后退与刷新都能复现。 */
export interface SearchUrlState {
  q: string;
  literal: boolean;
  page: number;
  category: string;
  /** 时间范围：day/week/month/year */
  range: "" | typeof TIME_RANGES[number];
  /** 语言代码，如 zh、en */
  lang: string;
  /** 站点限定域名 */
  site: string;
  /** 去重强度：off/normal/strict */
  dedupe: typeof DEDUPE_MODES[number];
}

export const TIME_RANGES = ["day", "week", "month", "year"] as const;
export const DEDUPE_MODES = ["off", "normal", "strict"] as const;

export type HistoryMode = "push" | "replace" | "none";

export const MAX_PAGE = 10;

export function readUrlState(search = window.location.search): SearchUrlState {
  const params = new URLSearchParams(search);
  const raw = Number(params.get("page") ?? "1");
  const page = Number.isInteger(raw) && raw >= 1 && raw <= MAX_PAGE ? raw : 1;
  const range = params.get("range") ?? "";
  const dedupe = params.get("dedupe") ?? "";
  return {
    q: params.get("q") ?? "",
    literal: params.get("literal") === "1",
    page,
    category: params.get("category") ?? "all",
    range: TIME_RANGES.find(value => value === range) ?? "",
    lang: normalizeLanguage(params.get("lang") ?? ""),
    site: normalizeSite(params.get("site") ?? "") ?? "",
    dedupe: DEDUPE_MODES.find(value => value === dedupe) ?? "normal",
  };
}

export function normalizeLanguage(raw: string): string {
  const value = raw.trim().toLowerCase();
  if (!/^[a-z]{2,3}(?:-[a-z]{2,4})?$/.test(value)) return "";
  const [language, region] = value.split("-");
  if (!region) return language;
  return `${language}-${region.length === 4 ? region[0].toUpperCase() + region.slice(1) : region.toUpperCase()}`;
}

export function normalizeSite(raw: string): string | null {
  const value = raw.trim().toLowerCase();
  if (!value) return "";
  const host = value.replace(/^https?:\/\//, "").split(/[/?#]/, 1)[0].replace(/^www\./, "").replace(/\.$/, "");
  const labels = host.split(".");
  return host.length <= 253 && labels.length > 1 && labels.every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))
    ? host : null;
}

export function searchUrl(state: SearchUrlState): string {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.literal) params.set("literal", "1");
  if (state.page > 1) params.set("page", String(state.page));
  if (state.category && state.category !== "all") params.set("category", state.category);
  if (state.range) params.set("range", state.range);
  if (state.lang) params.set("lang", state.lang);
  if (state.site) params.set("site", state.site);
  if (state.dedupe && state.dedupe !== "normal") params.set("dedupe", state.dedupe);
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

export function writeUrl(state: SearchUrlState, mode: HistoryMode): void {
  if (mode === "none") return;
  const url = searchUrl(state);
  const next = new URL(url, window.location.origin);
  if (new URLSearchParams(window.location.search).get("debug") === "1") next.searchParams.set("debug", "1");
  const target = next.pathname + next.search;
  // 同一查询重复提交（例如再次按回车）不再压一条无差别历史。
  if (target === window.location.pathname + window.location.search) return;
  if (mode === "push") window.history.pushState(null, "", target);
  else window.history.replaceState(null, "", target);
}
