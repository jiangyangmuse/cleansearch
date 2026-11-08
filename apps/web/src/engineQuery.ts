import type { EngineInfo } from "./types";

// 与后端相同：只替换实际可解析的末尾短码，不逐层删掉查询正文。
export function engineQuery(raw: string, code: string, engines: EngineInfo[]): string | null {
  const text = raw.normalize("NFKC").trim();
  if (text.split('"').length % 2 === 0) return null;
  const codes = new Set(["zh", "cn", "jp", "us", "en"]);
  for (const engine of engines) {
    codes.add(engine.code);
    engine.aliases.forEach((alias) => codes.add(alias));
  }
  const match = /\s*!([a-z]{1,3})$/i.exec(text) ?? /\s+([a-z]{1,3})$/i.exec(text);
  let base = text;
  if (match && codes.has(match[1].toLowerCase())) {
    const candidate = text.slice(0, match.index).trim();
    if ([...candidate].length >= 2) base = candidate;
  }
  return [...base].length >= 2 ? `${base} !${code}` : null;
}
