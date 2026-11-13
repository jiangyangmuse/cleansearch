import type { EngineInfo } from "./types";

export const ENGINE_SECTIONS = [
  { section: "mainland", title: "中国大陆可直连" },
  { section: null, title: "其他引擎" },
  { section: "custom", title: "自定义" },
] as const;

/** 状态用文字标签而不是颜色点：色弱与屏幕阅读器都能分辨。 */
export function engineStatusLabel(engine: EngineInfo): { tone: "ok" | "cooldown" | "unknown"; text: string } {
  if (engine.kind === "website") return { tone: "unknown", text: "直达" };
  if (engine.kind === "region") return { tone: "unknown", text: "地区" };
  if (engine.selectable === false) return { tone: "cooldown", text: "不可用" };
  if (engine.status === "cooldown") {
    const minutes = Math.max(1, Math.ceil(engine.remaining_seconds / 60));
    return { tone: "cooldown", text: `冷却 ${minutes} 分` };
  }
  if (engine.status === "ok") return { tone: "ok", text: "可用" };
  return { tone: "unknown", text: "未知" };
}

export function hasAISuffix(raw: string): boolean {
  const text = raw.normalize("NFKC").trim();
  if (text.split('"').length % 2 === 0) return false;
  const match = /(?:\s*!|\s+)ds$/i.exec(text);
  return match !== null && [...text.slice(0, match.index).trim()].length >= 2;
}

// 与后端相同：只替换实际可解析的末尾短码，不逐层删掉查询正文。
export function engineQuery(raw: string, code: string, engines: EngineInfo[], literal = false): string | null {
  const text = raw.normalize("NFKC").trim();
  if (text.split('"').length % 2 === 0) return null;
  if (literal) return [...text].length >= 2 ? `${text} !${code}` : null;
  const codes = new Set(["zh", "cn", "jp", "us", "en", "ds"]);
  for (const engine of engines) {
    codes.add(engine.code);
    engine.aliases.forEach((alias) => codes.add(alias));
  }
  const match = /\s*!([a-z][a-z0-9]{0,7})$/i.exec(text) ?? /\s+([a-z][a-z0-9]{0,7})$/i.exec(text);
  let base = text;
  if (match && codes.has(match[1].toLowerCase())) {
    const candidate = text.slice(0, match.index).trim();
    if ([...candidate].length >= 2) base = candidate;
  }
  return [...base].length >= 2 ? `${base} !${code}` : null;
}
