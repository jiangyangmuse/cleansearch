import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getSearchProvider, search } from "./api";
import MetaBar from "./components/MetaBar";
import ResultList from "./components/ResultList";
import SearchBar from "./components/SearchBar";
import SummaryPanel from "./components/SummaryPanel";
import { EmptyState, ErrorState, LoadingState } from "./components/StatePanel";
import ThemeToggle from "./components/ThemeToggle";
import type { SearchResponse } from "./types";

type Phase = "idle" | "loading" | "ok" | "empty" | "error";

const SAMPLES = [
  { label: "有结果", q: "python 文档" },
  { label: "零结果", q: "__empty 不存在的词" },
  { label: "上游不可用", q: "__fail 上游挂了" },
  { label: "恶意链接", q: "__risky 账号验证" },
];

function readInitialQuery(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("q") ?? "";
}

export default function App() {
  const [input, setInput] = useState(readInitialQuery);
  const [query, setQuery] = useState(readInitialQuery);
  const [phase, setPhase] = useState<Phase>("idle");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [showSamples, setShowSamples] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 键盘连按时 setState 尚未生效，用 ref 保证 j/k 连续移动不丢步
  const selectedRef = useRef<string | null>(null);
  const select = useCallback((id: string | null) => {
    selectedRef.current = id;
    setSelectedId(id);
  }, []);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(1);
  const drawerToggle = useRef<HTMLButtonElement>(null);
  const controller = useRef<AbortController | null>(null);
  const bootstrapped = useRef(false);

  const runSearch = useCallback(async (raw: string, nextPage = 1) => {
    const q = raw.trim();
    if (!q) return;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;

    setQuery(q);
    setPage(nextPage);
    setPhase("loading");
    setError(null);
    select(null);
    setDrawerOpen(false);
    const params = new URLSearchParams(window.location.search);
    if (params.get("q") !== q) {
      params.set("q", q);
      window.history.replaceState(null, "", `?${params.toString()}`);
    }

    try {
      const response = await search({ q, page: nextPage, opts: { safe: true } }, current.signal);
      if (current.signal.aborted) return;
      setData(response);
      setPhase(response.meta.total > 0 ? "ok" : "empty");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (current.signal.aborted) return;
      setData(null);
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("未知错误，查看浏览器控制台", "UNKNOWN", 0),
      );
      setPhase("error");
    }
  }, [select]);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    const initial = readInitialQuery().trim();
    if (initial) void runSearch(initial);
  }, [runSearch]);

  useEffect(() => {
    const check = new AbortController();
    void getSearchProvider(check.signal).then((provider) => {
      if (!check.signal.aborted) setShowSamples(provider === "fixture");
    }).catch(() => { /* 搜索不依赖自检入口 */ });
    return () => check.abort();
  }, []);

  const groups = data?.groups ?? { strong: [], related: [], weak: [] };

  // 键盘用：只统计当前可见的卡片（弱相关折叠时不参与 j/k）
  const visibleResults = useCallback(() => {
    if (!data) return [];
    const weakOpen = document.querySelector<HTMLDetailsElement>("details.group--collapsible")?.open;
    return [
      ...data.groups.strong,
      ...data.groups.related,
      ...(weakOpen ? data.groups.weak : []),
    ];
  }, [data]);

  useEffect(() => {
    let pendingG = false;
    let pendingTimer = 0;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      const typing = target?.closest("input, textarea, select") || target?.isContentEditable;

      if (event.key === "Escape") {
        select(null);
        setDrawerOpen(false);
        const toggle = drawerToggle.current;
        if (toggle?.getAttribute("aria-expanded") === "true" && toggle.getClientRects().length) {
          toggle.focus();
        } else if (typing) {
          target?.blur();
        }
        return;
      }
      if (event.key === "/" && !typing) {
        event.preventDefault();
        document.querySelector<HTMLInputElement>('input[name="q"]')?.focus();
        return;
      }
      if (typing) return;

      if (event.key === "g") {
        pendingG = true;
        window.clearTimeout(pendingTimer);
        pendingTimer = window.setTimeout(() => { pendingG = false; }, 800);
        return;
      }
      if (pendingG && event.key === "s") {
        window.location.href = "/";
        return;
      }
      pendingG = false;
      if (phase !== "ok") return;

      const list = visibleResults();
      if (!list.length) return;
      const index = list.findIndex((item) => item.id === selectedRef.current);

      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        const nextIndex =
          event.key === "j" ? Math.min(list.length - 1, index + 1) : Math.max(0, index - 1);
        const id = list[index === -1 ? 0 : nextIndex].id;
        select(id);
        const card = document.getElementById(`result-${id}`);
        card?.focus({ preventScroll: true });
        card?.scrollIntoView({ block: "nearest" });
        return;
      }
      const card = index < 0 ? null : document.getElementById(`result-${list[index].id}`);
      if (event.key === "Enter") {
        if (target?.closest("a[href], button, summary, [role=button], [role=link]")) return;
        const link = card?.querySelector<HTMLAnchorElement>(".card__title a[href]");
        if (link) {
          event.preventDefault();
          link.click();
        }
        return;
      }
      if (event.key === "b") {
        if (!event.repeat) card?.querySelector<HTMLButtonElement>(".card__save")?.click();
        return;
      }
      if (event.key === "s") {
        window.dispatchEvent(new CustomEvent("cs:summarize"));
        setDrawerOpen(true);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(pendingTimer);
    };
  }, [phase, select, visibleResults]);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">CleanSearch</span>
          <span className="brand__tag">M4 · 正文增强</span>
        </div>
        <span className="header__links">
          <ThemeToggle />
          <a className="header__link header__link--active" href="/s">
            单页总结
          </a>
          <a className="header__link header__link--active" href="/tools">
            一键添加
          </a>
          <a className="header__link header__link--active" href="/bookmarks">
            书签启动台
          </a>
        </span>
      </header>

      <main className="main">
        <SearchBar
          value={input}
          busy={phase === "loading"}
          onChange={setInput}
          onSubmit={() => void runSearch(input)}
        />

        {showSamples ? <div className="samples">
          <span>自检样本：</span>
          {SAMPLES.map((sample) => (
            <button
              key={sample.label}
              className="chip"
              type="button"
              onClick={() => {
                setInput(sample.q);
                void runSearch(sample.q);
              }}
            >
              {sample.label}
            </button>
          ))}
        </div> : null}

        {phase === "idle" ? (
          <div className="state state--idle">
            <h2>输入关键词开始</h2>
            <p>
              支持后缀路由（数分知识点 g）与 bang（python !b）。结果按强相关 / 相关 / 弱相关三档展示，弱相关默认折叠；刷新后按地址栏的 q 复现同一查询。
            </p>
          </div>
        ) : null}

        {phase === "loading" ? <LoadingState query={query} /> : null}

        {phase === "error" && error ? (
          <ErrorState error={error} query={query} onRetry={() => void runSearch(query)} />
        ) : null}

        {phase === "empty" ? (
          <>
            <EmptyState query={query} />
            {page > 1 ? (
              <div className="pager">
                <button className="chip" type="button" onClick={() => void runSearch(query, page - 1)}>
                  上一页
                </button>
                <span className="pager__label">第 {page} 页</span>
              </div>
            ) : null}
          </>
        ) : null}

        {phase === "ok" && data ? (
          <div className="layout">
            <div className="layout__results">
              <MetaBar meta={data.meta} parsed={data.parsed} />
              {data.parsed.expanded.length > 0 ? (
                <p className="shortcuts">已扩展同义词：{data.parsed.expanded.join(" / ")}</p>
              ) : null}
              <div className="pager">
                <button
                  className="chip"
                  type="button"
                  disabled={page <= 1}
                  onClick={() => void runSearch(query, Math.max(1, page - 1))}
                >
                  上一页
                </button>
                <span className="pager__label">第 {page} 页</span>
                <button
                  className="chip"
                  type="button"
                  disabled={data.meta.total === 0}
                  onClick={() => void runSearch(query, page + 1)}
                >
                  下一页
                </button>
              </div>
              <ResultList
                title="强相关"
                results={groups.strong}
                hint="默认展开"
                selectedId={selectedId}
                onSelect={select}
              />
              <ResultList
                title="相关"
                results={groups.related}
                hint="默认展开"
                selectedId={selectedId}
                onSelect={select}
              />
              <ResultList
                title="弱相关"
                results={groups.weak}
                hint="默认折叠"
                collapsible
                defaultOpen={false}
                selectedId={selectedId}
                onSelect={select}
              />
              <p className="shortcuts">
                <kbd>/</kbd> 聚焦 · <kbd>j</kbd>/<kbd>k</kbd> 选择 · <kbd>Enter</kbd> 打开 ·{" "}
                <kbd>b</kbd> 收藏 · <kbd>s</kbd> 总结 · <kbd>Esc</kbd> 取消
              </p>
            </div>
            <aside id="search-summary" className={drawerOpen ? "layout__side layout__side--open" : "layout__side"}>
              <SummaryPanel key={data.meta.sid} sid={data.meta.sid} query={data.parsed.q} />
            </aside>
            <button
              className="summary-toggle"
              type="button"
              ref={drawerToggle}
              onClick={() => setDrawerOpen((open) => !open)}
              aria-expanded={drawerOpen}
              aria-controls="search-summary"
            >
              {drawerOpen ? "收起总结" : "AI 总结"}
            </button>
          </div>
        ) : null}
      </main>

      <footer className="footer">
        CleanSearch · 本机单用户 · 检索层 SearXNG，前端 React + Vite，后端 FastAPI
      </footer>
    </div>
  );
}