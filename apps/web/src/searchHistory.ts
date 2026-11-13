export const HISTORY_KEY = "cs-search-history";
export const HISTORY_CHANGED = "cs:search-history";

export type HistoryEntry = { query: string; literal: boolean };

export function readSearchHistory(): HistoryEntry[] {
  try {
    const items: unknown = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
    if (!Array.isArray(items)) return [];
    return items.flatMap((item: unknown) => {
      if (typeof item === "string") return [{ query: item, literal: false }];
      if (item && typeof item === "object" && "query" in item && typeof item.query === "string") {
        return [{ query: item.query, literal: "literal" in item && item.literal === true }];
      }
      return [];
    }).slice(0, 30);
  } catch {
    return [];
  }
}

function writeHistory(items: HistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
    window.dispatchEvent(new Event(HISTORY_CHANGED));
    return true;
  } catch {
    // 搜索在浏览器限制本地存储时仍可使用。
    return false;
  }
}

export function rememberSearch(entry: HistoryEntry) {
  writeHistory([entry, ...readSearchHistory().filter(item => item.query !== entry.query)].slice(0, 30));
}

export function historySearchHref({ query, literal }: HistoryEntry) {
  const params = new URLSearchParams({ q: query });
  if (literal) params.set("literal", "1");
  return `/?${params}`;
}

export function clearSearchHistory() {
  return writeHistory([]);
}
