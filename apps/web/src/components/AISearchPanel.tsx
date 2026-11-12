import type { ApiError } from "../api";
import type { AISearchResponse } from "../types";
import ContentModules from "./ContentModules";
import ResultList from "./ResultList";

export type AISearchState =
  | { phase: "loading" }
  | { phase: "ok"; data: AISearchResponse }
  | { phase: "error"; error: ApiError };

export default function AISearchPanel({ state, onRetry, selectedId, onSelect }: {
  state: AISearchState;
  onRetry: () => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="ai-search" aria-labelledby="ai-search-title" aria-busy={state.phase === "loading"}>
      <header className="ai-search__head">
        <h2 id="ai-search-title">AI 检索</h2>
        {state.phase === "ok" && (
          <span>{state.data.provider}{state.data.cached ? " · 缓存" : ""}</span>
        )}
      </header>
      {state.phase === "loading" && <p role="status">正在检索网页…</p>}
      {state.phase === "error" && (
        <div role="status">
          <p>{state.error.message}</p>
          {state.error.retryable && <button className="chip" type="button" onClick={onRetry}>重试 AI 检索</button>}
        </div>
      )}
      {state.phase === "ok" && (state.data.results.length ? (
        <>
          <ContentModules results={state.data.results} selectedId={selectedId} onSelect={onSelect} />
          <ResultList title="网页" results={state.data.results.filter(result => !result.category)}
            selectedId={selectedId} onSelect={onSelect} />
        </>
      ) : <p role="status">AI 检索没有找到可展示的网页。</p>)}
    </section>
  );
}
