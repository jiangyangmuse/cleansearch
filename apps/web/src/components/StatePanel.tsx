import type { ApiError } from "../api";

const UPSTREAM_HINT = [
  "# 检查自建 SearXNG 是否可达且开启了 json",
  'curl "$SEARXNG_URL/search?q=test&format=json" | head -c 300',
  "# 本机没装 Docker 时，用固定样本验收闭环",
  ".\\scripts\\serve.ps1 -Provider fixture",
].join("\n");

interface EmptyProps {
  title: string;
  detail: string;
  onChangeKeyword: () => void;
  clearSuffix?: { label: string; action: () => void };
  onViewAll?: () => void;
}

export function EmptyState({ title, detail, onChangeKeyword, clearSuffix, onViewAll }: EmptyProps) {
  return (
    <div className="state state--empty">
      <h2 tabIndex={-1}>{title}</h2>
      <p>{detail}</p>
      <div className="state__actions">
        <button className="button" type="button" onClick={onChangeKeyword}>换关键词</button>
        {clearSuffix
          ? <button className="button button--ghost" type="button" onClick={clearSuffix.action}>{clearSuffix.label}</button>
          : null}
        {onViewAll ? <button className="button button--ghost" type="button" onClick={onViewAll}>查看全部结果</button> : null}
      </div>
    </div>
  );
}

interface ErrorProps {
  error: ApiError;
  query: string;
  onRetry: () => void;
  onChangeKeyword: () => void;
  /** 只有 fixture / ?debug=1 才展示错误码与诊断命令 */
  diagnostics?: boolean;
}

export function searchErrorMessage(error: ApiError): { title: string; detail: string } {
  switch (error.code) {
    case "NETWORK_ERROR":
      return { title: "本机搜索服务未连接", detail: "确认本机 CleanSearch 服务正在运行，然后重试。" };
    case "SEARCH_ENGINES_DISABLED":
      return { title: "普通搜索已暂停", detail: "在设置中启用默认搜索引擎，或指定一个可用的引擎后缀。" };
    case "FILTERS_UNAVAILABLE":
      return { title: "本机服务尚未支持搜索筛选", detail: "加载新版 CleanSearch 后端后重试，或重置筛选后继续搜索。" };
    case "ENGINE_UNAVAILABLE":
      return { title: "指定引擎暂时不可用", detail: "稍后重试，或修改查询改用其他引擎。" };
    case "UPSTREAM_TIMEOUT":
      return { title: "搜索服务响应超时", detail: "稍后重试，或改用其他搜索引擎。" };
    case "UPSTREAM_BAD_RESPONSE":
      return { title: "搜索服务返回了无效响应", detail: "稍后重试，或检查搜索引擎设置。" };
    default:
      if (error.code.startsWith("UPSTREAM_")) {
        return { title: "搜索服务暂时不可用", detail: "上游搜索服务未正常响应，请稍后重试。" };
      }
      return { title: "请求失败", detail: error.retryable ? "稍后重试，或修改查询后再搜索。" : "修改查询或检查设置后再搜索。" };
  }
}

export function ErrorState({ error, query, onRetry, onChangeKeyword, diagnostics = false }: ErrorProps) {
  const { title, detail } = searchErrorMessage(error);
  return (
    <div className="state state--error">
      <h2 tabIndex={-1}>{title}</h2>
      <p>{detail}</p>
      <div className="state__actions">
        {error.retryable ? <button className="button" type="button" onClick={onRetry}>重试</button>
          : <button className="button" type="button" onClick={onChangeKeyword}>换关键词</button>}
        <a className="button button--ghost" href="/settings#engine-settings">打开设置</a>
      </div>
      {diagnostics ? (
        <details className="state__diagnostics">
          <summary>诊断详情</summary>
          <p className="state__hint">
            错误码 <code>{error.code}</code>
            {error.status ? <> · HTTP {error.status}</> : null} · 查询「{query}」
          </p>
          <p className="state__hint">{error.message}</p>
          {error.code === "NETWORK_ERROR" || error.code.startsWith("UPSTREAM_")
            ? <pre className="state__cmd">{UPSTREAM_HINT}</pre> : null}
        </details>
      ) : null}
    </div>
  );
}
