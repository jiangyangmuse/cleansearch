import type { EngineInfo } from "./types";
import type { HistoryEntry } from "./searchHistory";

export interface Suggestion {
  id: string;
  label: string;
  hint: string;
  insert: string;
  literal: boolean;
}

/** 官方品牌快捷词：只做输入提示，不改变检索语义。 */
const BRAND_TERMS: { label: string; term: string }[] = [
  { label: "必应", term: "bing" },
  { label: "百度", term: "baidu" },
  { label: "知乎", term: "知乎" },
  { label: "哔哩哔哩", term: "bilibili" },
  { label: "GitHub", term: "github" },
  { label: "MDN 文档", term: "mdn web docs" },
  { label: "Python 文档", term: "python 文档" },
  { label: "维基百科", term: "wikipedia" },
];

const MAX_HISTORY = 4;
const MAX_ENGINES = 3;
const MAX_BRANDS = 3;

function matches(haystack: string, needle: string): boolean {
  return !needle || haystack.toLowerCase().includes(needle.toLowerCase());
}

/**
 * 输入建议：本地历史 + 引擎后缀 + 官方品牌，按输入前缀/子串过滤，最多 limit 条。
 * 引擎项插入成 `<当前词> !code`，其余直接替换输入框内容。
 */
export function buildSuggestions(
  input: string,
  history: HistoryEntry[],
  engines: EngineInfo[],
): Suggestion[] {
  const raw = input.normalize("NFKC").trim();
  const suffix = /^(.*?)\s*!([a-z0-9]{0,8})$/i.exec(raw);
  if (suffix) {
    const [, base, prefix] = suffix;
    return engines.flatMap(engine => {
      if (engine.selectable === false || ![engine.code, ...engine.aliases].some(code =>
        code.toLowerCase().startsWith(prefix.toLowerCase()))) return [];
      const insert = engineQuery(base, engine.code, engines, true);
      return insert ? [{
        id: `engine:${engine.code}`,
        label: engine.label,
        hint: `引擎后缀 !${engine.code}`,
        insert,
        literal: false,
      }] : [];
    }).slice(0, MAX_ENGINES);
  }

  const recent = history.filter(entry => entry.query.trim() && matches(entry.query.normalize("NFKC"), raw))
    .slice(0, MAX_HISTORY).map(entry => ({
      id: `history:${entry.query}`,
      label: entry.query,
      hint: entry.literal ? "历史 · 字面" : "历史",
      insert: entry.query,
      literal: entry.literal,
    }));
  const brands = BRAND_TERMS.filter(brand => matches(brand.label, raw) || matches(brand.term, raw))
    .filter(brand => !recent.some(item => !item.literal && item.insert.toLowerCase() === brand.term))
    .slice(0, MAX_BRANDS).map(brand => ({
      id: `brand:${brand.term}`,
      label: brand.label,
      hint: "品牌词",
      insert: brand.term,
      literal: false,
    }));
  return [...recent, ...brands];
}
import { engineQuery } from "./engineQuery";
