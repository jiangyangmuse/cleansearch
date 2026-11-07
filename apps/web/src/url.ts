/** 渲染前拒绝有凭证或可能被浏览器重新解释主机的链接。 */
export function safeHref(url: string): string | null {
  const candidate = url.trim();
  if (candidate.length > 2048 || /[\x00-\x1f\x7f\\]/.test(candidate)) return null;
  const authority = /^https?:\/\/([^/?#]+)/i.exec(candidate)?.[1];
  if (!authority || /[@%]/.test(authority)) return null;

  try {
    const parsed = new URL(candidate);
    if (!parsed.hostname || parsed.hostname.startsWith(".") || parsed.hostname.endsWith(".")) {
      return null;
    }
    return parsed.href;
  } catch {
    return null;
  }
}
