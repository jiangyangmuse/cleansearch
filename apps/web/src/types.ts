export type Group = "strong" | "related" | "weak";
export type ResultCategory = "encyclopedia" | "download" | "video";

export interface Result {
  id: string;
  url: string;
  display_url: string;
  title: string;
  snippet: string;
  engine: string[];
  score: number;
  risk: number;
  reasons: string[];
  favicon: string | null;
  published: string | null;
  read_minutes: number | null;
  go_url?: string | null;
  brand_warning?: string | null;
  category?: ResultCategory | null;
}

export interface AISearchResponse {
  provider: string;
  results: Result[];
  cached: boolean;
}

export interface OfficialLink extends Result {
  origin: "search" | "directory";
  role: string;
  label: string;
  host: string;
  source: string;
  verified: string;
}

export interface OfficialSection {
  key: string;
  brand: string;
  entries: OfficialLink[];
}

export interface SearchMeta {
  status: "ok" | "empty";
  engines: string[];
  unresponsive: string[];
  provider: string;
  cached: boolean;
  ms: number;
  total: number;
  upstream_total: number;
  filtered: { dup: number; risk: number };
  official: number;
  directory: number;
  filters?: { time_range: string | null; language: string | null; site: string | null; dedupe: string };
  sid: string;
}

export interface ParsedQuery {
  q: string;
  engine: string;
  region: string | null;
  router: "suffix" | "bang" | "default";
  expanded: string[];
  custom_code?: string | null;
  open_url?: string | null;
}

export interface SearchResponse {
  parsed: ParsedQuery;
  groups: Record<Group, Result[]>;
  meta: SearchMeta;
  official: OfficialSection | null;
}

export type EngineSection = "mainland" | "custom" | null;
export type SearchEntryKind = "engine" | "region" | "website";

export interface EngineInfo {
  code: string;
  label: string;
  engine: string;
  searx_engine: string;
  fallbacks: string[];
  paid: string;
  aliases: string[];
  note: string;
  status: "ok" | "cooldown" | "unknown";
  available: boolean | null;
  can_fallback: boolean;
  selectable: boolean;
  fails: number;
  avg_ms: number | null;
  last_error: string | null;
  remaining_seconds: number;
  section?: EngineSection;
  kind?: SearchEntryKind;
}

export type CustomSearchEntry = { code: string; label: string; kind: SearchEntryKind; target: string };
export type EnginePreferences = { revision: number; default_engines: string[] | null; custom: CustomSearchEntry[] };
export type EngineSettings = {
  preferences: EnginePreferences;
  builtins: Pick<EngineInfo, "code" | "label" | "searx_engine" | "section" | "aliases">[];
  sources: Record<string, boolean> | null;
};

export interface EnginesResponse {
  provider: string;
  searxng_url: string;
  breaker: boolean;
  paid: { serper: boolean; brave: boolean };
  engines: EngineInfo[];
}

export interface ApiErrorPayload {
  error: { code: string; message: string; retryable: boolean };
}

export interface Bookmark {
  id: number;
  url: string;
  title: string | null;
  favicon: string | null;
  group_id: number | null;
  group_name: string | null;
  note: string | null;
  created_at: number;
  dead: number;
  dead_status: number | null;
  dead_checked_at: number | null;
  tags: string[];
}

export interface BookmarkGroup {
  id: number;
  name: string;
  count: number;
}

export interface BookmarkListResponse {
  items: Bookmark[];
  groups: BookmarkGroup[];
  tags?: { tag: string; count: number }[];
  total: number;
  fts: boolean;
}

export interface BookmarkSaveResponse {
  item: Bookmark;
  deduplicated: boolean;
}

export interface ImportResult {
  total: number;
  created: number;
  updated: number;
  skipped: number;
  groups_created: number;
}
