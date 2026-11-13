/** 查询词高亮工具：中文按词组整段匹配，英文按词边界，最多 3 个词。 */
const CJK_CHAR = "[\\p{Script=Han}\\p{Script=Hiragana}\\p{Script=Katakana}\\p{Script=Hangul}]";
const CJK = new RegExp(CJK_CHAR, "u");
const WORD_CHAR = "[\\p{L}\\p{N}\\p{M}_]";

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** 使用后端已解析的查询，保留 C++、C#、Node.js 等技术词。 */
export function searchTerms(query: string): string[] {
  const tokens = query.normalize("NFKC").match(/[\p{L}\p{N}_][\p{L}\p{N}\p{M}_]*(?:[.-][\p{L}\p{N}\p{M}_]+)*(?:\+\+|#)?/gu) ?? [];
  const picked: string[] = [];
  for (const token of tokens) {
    if ([...token].length < 2) continue;
    if (picked.some(item => item.toLowerCase() === token.toLowerCase())) continue;
    picked.push(token);
    if (picked.length === 3) break;
  }
  return picked;
}

export interface Segment { text: string; hit: boolean; }

/** 把文本切成「命中 / 未命中」片段，交给组件渲染 <mark>。 */
export function splitHighlight(text: string, terms: string[]): Segment[] {
  if (!text) return [];
  if (!terms.length) return [{ text, hit: false }];
  const unions = terms
    .slice()
    .sort((left, right) => right.length - left.length)
    .map(term => {
      const escaped = escapeRegExp(term);
      if (CJK.test(term)) return escaped;
      // 允许「学Python」等中英混排，同时排除 Pythonic 之类的词内命中。
      return `(?:(?<!${WORD_CHAR})|(?<=${CJK_CHAR}))${escaped}(?:(?!${WORD_CHAR})|(?=${CJK_CHAR}))`;
    });
  const pattern = new RegExp(`(${unions.join("|")})`, "giu");
  return text.split(pattern).flatMap((part, index) => part ? [{ text: part, hit: index % 2 === 1 }] : []);
}

/** 域名面包屑由链接地址生成，单独解码路径段。 */
export function breadcrumb(url: string, displayUrl: string): string {
  const shorten = (value: string): string => {
    let text = value;
    try {
      const decoded = decodeURIComponent(value);
      if (!/[\p{Cc}\p{Bidi_Control}›/\\]/u.test(decoded)) text = decoded;
    } catch { /* 保留原串 */ }
    const chars = [...text];
    return chars.length > 24 ? chars.slice(0, 23).join("") + "…" : text;
  };
  try {
    const parsed = new URL(url);
    const segments = parsed.pathname.split("/").filter(Boolean).slice(-2).map(shorten);
    return [parsed.host, ...segments].join(" › ");
  } catch {
    return displayUrl || url;
  }
}
