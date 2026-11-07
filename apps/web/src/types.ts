export type Group = "strong" | "related" | "weak";

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
  sid: string;
}

export interface ParsedQuery {
  q: string;
  engine: string;
  region: string | null;
  router: "suffix" | "bang" | "default";
  expanded: string[];
}

export interface SearchResponse {
  parsed: ParsedQuery;
  groups: Record<Group, Result[]>;
  meta: SearchMeta;
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