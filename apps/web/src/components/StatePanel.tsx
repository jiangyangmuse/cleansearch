import type { ApiError } from "../api";

const UPSTREAM_HINT = [
  "# 检查自建 SearXNG 是否可达且开启了 json",
  'curl "$SEARXNG_URL/search?q=test&format=json" | head -c 300',
  "# 本机没装 Docker 时，用固定样本验收闭环",
  "SEARCH_PROVIDER=fixture python -m app.main",
].join("\n");

export function EmptyState({ query }: { query: string }) {
  return (
    <div className="state state--empty" role="status">
      <h2>没有结果</h2>
      <p>
        查询「{query}」没有可展示的结果。试试换一组关键词，或取消指定引擎。
      </p>
    </div>
  );
}

export function ErrorState({
  error,
  query,
  onRetry,
}: {
  error: ApiError;
  query: string;
  onRetry: () => void;
}) {
  const upstream = error.code.startsWith("UPSTREAM") || error.code === "NETWORK_ERROR";
  return (
    <div className="state state--error" role="alert">
      <h2>{upstream ? "上游不可用" : "请求失败"}</h2>
      <p>{error.message}</p>
      <p className="state__hint">
        错误码 <code>{error.code}</code>
        {error.status ? <> · HTTP {error.status}</> : null} · 查询「{query}」
      </p>
      {upstream ? <pre className="state__cmd">{UPSTREAM_HINT}</pre> : null}
      <button className="button" type="button" onClick={onRetry} disabled={!error.retryable}>
        重试
      </button>
    </div>
  );
}

export function LoadingState({ query }: { query: string }) {
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>正在检索「{query}」…</p>
    </div>
  );
}
