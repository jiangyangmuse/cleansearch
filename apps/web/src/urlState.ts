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

/** 筛选条件：地址栏与请求体共用同一份结构，避免界面、URL、请求三者漂移。 */
export interface SearchFiltersState {
  /** 时间范围："" 表示全部时间 */
  timeRange: "" | typeof TIME_RANGES[number];
  /** 语言代码，"" 表示不限 */
  language: string;
  /** 站点限定域名，"" 表示不限 */
  site: string;
  /** 去重强度 */
  dedupe: typeof DEDUPE_MODES[number];
}

export const DEFAULT_FILTERS: SearchFiltersState = { timeRange: "", language: "", site: "", dedupe: "normal" };

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
  const host = value.replace(/^https?:\/\//, "").split(/[/?#]/, 1)[0].replace(/^(?:www\.)+/, "").replace(/\.$/, "");
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

/** 从 URL 状态取出筛选条件；非法值已在 readUrlState 归一化。 */
export function filtersFromUrl(state: SearchUrlState): SearchFiltersState {
  return { timeRange: state.range, language: state.lang, site: state.site, dedupe: state.dedupe };
}

/** 筛选差异比较：popstate 用它判断「只改了筛选」还是「同一次搜索」。 */
export function sameFilters(left: SearchFiltersState, right: SearchFiltersState): boolean {
  return left.timeRange === right.timeRange && left.language === right.language
    && left.site === right.site && left.dedupe === right.dedupe;
}

/** 除筛选以外的搜索身份：查询、字面模式、页码、分类。 */
export type SearchBaseState = Omit<SearchUrlState, "range" | "lang" | "site" | "dedupe">;

/** 把筛选合进 URL 状态：写地址栏与发请求都用这一个来源。 */
export function withFilters<T extends SearchBaseState>(state: T, filters: SearchFiltersState): SearchUrlState {
  return { ...state, range: filters.timeRange, lang: filters.language, site: filters.site, dedupe: filters.dedupe };
}

/** 请求体 opts 里的筛选片段，与 SearchRequest.opts 契约对齐（空值发 null）。 */
export function filterOptions(filters: SearchFiltersState): {
  time_range: Exclude<SearchFiltersState["timeRange"], ""> | null;
  language: string | null;
  site: string | null;
  dedupe: SearchFiltersState["dedupe"];
} {
  return {
    time_range: filters.timeRange || null,
    language: filters.language || null,
    site: filters.site || null,
    dedupe: filters.dedupe,
  };
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
