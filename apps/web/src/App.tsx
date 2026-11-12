import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError, getEngines, getSearchProvider, search, searchAI } from "./api";
import AISearchPanel, { type AISearchState } from "./components/AISearchPanel";
import ContentModules from "./components/ContentModules";
import EngineBar from "./components/EngineBar";
import { engineQuery, hasAISuffix } from "./engineQuery";
import MetaBar from "./components/MetaBar";
import OfficialPanel from "./components/OfficialPanel";
import PageBatchSummary from "./components/PageBatchSummary";
import QuickBookmarks from "./components/QuickBookmarks";
import ResultList from "./components/ResultList";
import SearchBar from "./components/SearchBar";
import SummaryPanel from "./components/SummaryPanel";
import TranslationPanel from "./components/TranslationPanel";
import { EmptyState, ErrorState, LoadingState } from "./components/StatePanel";
import WorkspaceHeader from "./components/WorkspaceHeader";
import { rememberSearch } from "./searchHistory";
import { readDailyAI, saveDailyAI } from "./searchPreferences";
import type { EngineInfo, ResultCategory, SearchResponse } from "./types";

type Phase = "idle" | "loading" | "ok" | "empty" | "error";
type View = "all" | ResultCategory;
type SidePanel = "ai" | "summary" | "translate";
type SearchOptions = { page?: number; paging?: boolean; record?: boolean; literal?: boolean };

const VIEWS: { id: View; label: string; icon: string }[] = [
  { id: "all", label: "首页", icon: "home" },
  { id: "encyclopedia", label: "百科", icon: "book" },
  { id: "video", label: "视频", icon: "video" },
  { id: "download", label: "下载", icon: "download" },
];

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

function readInitialLiteral(): boolean {
  return new URLSearchParams(window.location.search).get("literal") === "1";
}

function readView(): View {
  const id = new URLSearchParams(window.location.search).get("category");
  return VIEWS.find(view => view.id === id)?.id ?? "all";
}

export default function App() {
  const [input, setInput] = useState(readInitialQuery);
  const [inputLiteral, setInputLiteral] = useState(readInitialLiteral);
  const [query, setQuery] = useState(readInitialQuery);
  const [literal, setLiteral] = useState(readInitialLiteral);
  const [phase, setPhase] = useState<Phase>("idle");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [showSamples, setShowSamples] = useState(false);
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 键盘连按时 setState 尚未生效，用 ref 保证 j/k 连续移动不丢步
  const selectedRef = useRef<string | null>(null);
  const select = useCallback((id: string | null) => {
    selectedRef.current = id;
    setSelectedId(id);
  }, []);
  const [view, setView] = useState(readView);
  const [sidePanel, setSidePanel] = useState<SidePanel | null>(null);
  const [page, setPage] = useState(1);
  const aiToggle = useRef<HTMLButtonElement>(null);
  const summaryToggle = useRef<HTMLButtonElement>(null);
  const translateToggle = useRef<HTMLButtonElement>(null);
  const enginesDisclosure = useRef<HTMLDetailsElement>(null);
  const controller = useRef<AbortController | null>(null);
  const aiController = useRef<AbortController | null>(null);
  const [dailyAI, setDailyAI] = useState(readDailyAI);
  const dailyAIRef = useRef(dailyAI);
  const [aiState, setAIState] = useState<AISearchState | null>(null);
  const bootstrapped = useRef(false);

  const changeView = useCallback((next: View) => {
    setView(next);
    select(null);
    const url = new URL(window.location.href);
    if (next === "all") url.searchParams.delete("category");
    else url.searchParams.set("category", next);
    window.history.replaceState(null, "", url);
  }, [select]);

  const runAISearch = useCallback(async (q: string, literal: boolean) => {
    aiController.current?.abort();
    const current = new AbortController();
    aiController.current = current;
    setAIState({ phase: "loading" });
    setSidePanel("ai");
    try {
      const data = await searchAI(q, current.signal, literal);
      if (!current.signal.aborted) setAIState({ phase: "ok", data });
    } catch (error) {
      if (!current.signal.aborted) {
        setAIState({ phase: "error", error: error instanceof ApiError
          ? error : new ApiError("AI 检索暂不可用", "AI_SEARCH_ERROR", 0) });
      }
    }
  }, []);

  const runSearch = useCallback(async (raw: string, options: SearchOptions = {}) => {
    const { page: nextPage = 1, paging = false, record = true, literal = false } = options;
    const q = raw.trim();
    if (!q) return;
    if (record && !paging) rememberSearch({ query: q, literal });
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    if (!paging) {
      if (dailyAIRef.current || (!literal && hasAISuffix(q))) {
        void runAISearch(q, literal);
      } else {
        aiController.current?.abort();
        setAIState(null);
      }
    }

    setQuery(q);
    setLiteral(literal);
    setPage(nextPage);
    setPhase("loading");
    setError(null);
    select(null);
    if (!paging) setSidePanel(currentPanel => currentPanel === "summary" ? null : currentPanel);
    const params = new URLSearchParams(window.location.search);
    params.set("q", q);
    if (literal) params.set("literal", "1");
    else params.delete("literal");
    window.history.replaceState(null, "", `?${params.toString()}`);

    try {
      const response = await search({ q, page: nextPage, opts: { safe: true, literal } }, current.signal);
      if (current.signal.aborted) return;
      setData(response);
      const hasOfficial = (response.official?.entries.length ?? 0) > 0;
      setPhase(response.meta.total > 0 || hasOfficial ? "ok" : "empty");
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
    } finally {
      // 每次请求后刷新健康状态；旧请求的目录响应不能覆盖新请求。
      if (!current.signal.aborted) {
        void getEngines(current.signal).then((payload) => {
          if (!current.signal.aborted && payload.provider === "searxng") setEngines(payload.engines);
        }).catch(() => { /* 目录失败不影响搜索结果 */ });
      }
    }
  }, [runAISearch, select]);

  useEffect(() => {
    const sync = () => {
      const enabled = readDailyAI();
      dailyAIRef.current = enabled;
      setDailyAI(enabled);
      if (!enabled && (literal || !hasAISuffix(query))) {
        aiController.current?.abort();
        setAIState(null);
      }
    };
    window.addEventListener("pageshow", sync);
    return () => window.removeEventListener("pageshow", sync);
  }, [query, literal]);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    const initial = readInitialQuery().trim();
    if (initial) void runSearch(initial, { record: false, literal: readInitialLiteral() });
  }, [runSearch]);

  useEffect(() => {
    const check = new AbortController();
    void getSearchProvider(check.signal).then((provider) => {
      if (!check.signal.aborted) setShowSamples(provider === "fixture");
    }).catch(() => { /* 搜索不依赖自检入口 */ });
    return () => check.abort();
  }, []);

  useEffect(() => {
    const check = new AbortController();
    void getEngines(check.signal).then((payload) => {
      if (!check.signal.aborted && !controller.current && payload.provider === "searxng") setEngines(payload.engines);
    }).catch(() => { /* 引擎目录不可用时保持纯文本后缀 */ });
    return () => check.abort();
  }, []);

  const pickEngine = useCallback(
    (code: string) => {
      const next = engineQuery(input, code, engines, inputLiteral);
      if (next === null) return;
      if (enginesDisclosure.current) enginesDisclosure.current.open = false;
      setInput(next);
      setInputLiteral(false);
      void runSearch(next);
    },
    [input, inputLiteral, engines, runSearch],
  );

  const groups = data?.groups ?? { strong: [], related: [], weak: [] };
  const groupedContent = [...groups.strong, ...groups.related, ...groups.weak];
  const currentView = VIEWS.find(item => item.id === view) ?? VIEWS[0];
  const categoryResults = groupedContent.filter(item => item.category === view);
  const summaryData = phase === "ok" ? data : null;
  const canSummarize = summaryData && (
    groupedContent.some(item => !item.brand_warning) ||
    summaryData.official?.entries.some(entry => entry.origin !== "directory")
  );

  useEffect(() => {
    let pendingG = false;
    let pendingTimer = 0;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      const typing = target?.closest("input, textarea, select") || target?.isContentEditable;

      if (event.key === "Escape") {
        select(null);
        const disclosure = enginesDisclosure.current;
        if (disclosure?.open) {
          disclosure.open = false;
          if (disclosure.contains(target)) disclosure.querySelector("summary")?.focus();
          return;
        }
        if (sidePanel) {
          setSidePanel(null);
          ({ ai: aiToggle, summary: summaryToggle, translate: translateToggle })[sidePanel].current?.focus();
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
      if (event.key === "s" && phase === "ok") {
        window.dispatchEvent(new CustomEvent("cs:summarize"));
        setSidePanel("summary");
        return;
      }

      // 只导航当前分区及已展开的面板与分组。
      const list = Array.from(document.querySelectorAll<HTMLElement>(".workspace [id^='result-']"))
        .filter(card => card.getClientRects().length && !card.closest("details:not([open])"));
      if (!list.length) return;
      const index = list.findIndex(card => card.id === `result-${selectedRef.current}`);

      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        const nextIndex =
          event.key === "j" ? Math.min(list.length - 1, index + 1) : Math.max(0, index - 1);
        const card = list[index === -1 ? 0 : nextIndex];
        select(card.id.slice("result-".length));
        card.focus({ preventScroll: true });
        card.scrollIntoView({ block: "nearest" });
        return;
      }
      const card = list[index];
      if (event.key === "Enter") {
        if (target?.closest("a[href], button, summary, [role=button], [role=link]")) return;
        const link = card?.querySelector<HTMLAnchorElement>(".card__title a[href], .official__link[href]");
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
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(pendingTimer);
    };
  }, [phase, select, sidePanel]);

  return (
    <div className="workspace-app">
      <WorkspaceHeader onHistorySearch={({ query: previous, literal }) => {
        changeView("all");
        setInput(previous);
        setInputLiteral(literal);
        void runSearch(previous, { literal });
      }} />
      <div className="workspace">
        <nav className="workspace-nav" aria-label="搜索分类">
          <div className="workspace-nav__items">
            {VIEWS.map(({ id, label, icon }) => (
              <button key={id} type="button" className="workspace-nav__item"
                aria-current={view === id ? "page" : undefined} onClick={() => changeView(id)}>
                <i className={`ws-icon ws-icon--${icon}`} aria-hidden="true" />{label}
              </button>
            ))}
          </div>
        </nav>

        <main className="workspace-main">
          <div className="workspace-search">
            <SearchBar value={input} busy={phase === "loading"} onChange={value => {
              setInput(value);
              setInputLiteral(false);
            }} onSubmit={() => void runSearch(input, { literal: inputLiteral })} />
            <div className="workspace-search__options">
              {engines.length > 0 && (
                <details className="workspace-engines" ref={enginesDisclosure}>
                  <summary>引擎后缀 <i className="ws-icon ws-icon--chevron" aria-hidden="true" /></summary>
                  <EngineBar engines={engines} busy={phase === "loading"}
                    canPick={engineQuery(input, "g", engines, inputLiteral) !== null} onPick={pickEngine} />
                </details>
              )}
              <label className="workspace-ai-setting"
                title={dailyAI ? "随每次搜索请求 AI 服务，可能产生 API 费用" : "输入 ds 后缀可单次启用"}>
                <input className="workspace-switch" type="checkbox" role="switch" checked={dailyAI}
                  onChange={(event) => {
                    const next = event.target.checked;
                    dailyAIRef.current = next;
                    setDailyAI(next);
                    saveDailyAI(next);
                    if (!next && (literal || !hasAISuffix(query))) {
                      aiController.current?.abort();
                      setAIState(null);
                      setSidePanel(current => current === "ai" ? null : current);
                    }
                  }} />
                日常 AI 检索
              </label>
              <span className={dailyAI ? "workspace-search__cost" : "workspace-search__keys"}>
                {dailyAI ? "每次搜索可能产生 API 费用" : <><kbd>/</kbd> 聚焦搜索</>}
              </span>
            </div>
            {showSamples && (
              <div className="samples">
                <span>自检样本</span>
                {SAMPLES.map((sample) => (
                  <button key={sample.label} className="chip" type="button" onClick={() => {
                    setInput(sample.q);
                    setInputLiteral(false);
                    void runSearch(sample.q);
                  }}>
                    {sample.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="workspace-results">
            {view !== "all" && <h1 className="workspace-results__title">{currentView.label}</h1>}
            {view !== "all" && phase === "idle" && (
              <p className="workspace-results__hint">输入关键词，查看{currentView.label}结果。</p>
            )}
            {phase === "loading" && <LoadingState query={query} />}
            {phase === "error" && error && (
              <ErrorState error={error} query={query}
                onRetry={() => void runSearch(query, { page, paging: page > 1, literal, record: false })} />
            )}
            {phase === "empty" && (
              <>
                <EmptyState query={query} />
                {page > 1 && (
                  <div className="pager">
                    <button className="chip" type="button" onClick={() => void runSearch(query, { page: page - 1, paging: true, literal })}>
                      上一页
                    </button>
                    <span className="pager__label">第 {page} 页</span>
                  </div>
                )}
              </>
            )}
            {phase === "ok" && data && (
              <>
                {view === "all" && (
                  <>
                    <MetaBar meta={data.meta} parsed={data.parsed} />
                    <OfficialPanel section={data.official} selectedId={selectedId} onSelect={select} />
                    {data.parsed.expanded.length > 0 && (
                      <p className="shortcuts">已扩展同义词：{data.parsed.expanded.join(" / ")}</p>
                    )}
                  </>
                )}
                <div className="pager">
                  <button className="chip" type="button" disabled={page <= 1}
                    onClick={() => void runSearch(query, { page: page - 1, paging: true, literal })}>
                    上一页
                  </button>
                  <span className="pager__label">第 {page} 页</span>
                  <button className="chip" type="button" disabled={page >= 10 || data.meta.total === 0}
                    onClick={() => void runSearch(query, { page: page + 1, paging: true, literal })}>
                    下一页
                  </button>
                </div>
                {view === "all" ? (
                  <>
                    <ContentModules results={groupedContent} selectedId={selectedId} onSelect={select} />
                    <ResultList title="强相关" results={groups.strong.filter(result => !result.category)}
                      selectedId={selectedId} onSelect={select} />
                    <ResultList title="相关" results={groups.related.filter(result => !result.category)}
                      selectedId={selectedId} onSelect={select} />
                    <ResultList title="弱相关" results={groups.weak.filter(result => !result.category)}
                      collapsible defaultOpen={false} selectedId={selectedId} onSelect={select} />
                  </>
                ) : categoryResults.length ? (
                  <ResultList title={`${currentView.label}结果`} results={categoryResults}
                    selectedId={selectedId} onSelect={select} />
                ) : (
                  <p className="workspace-results__hint" role="status">本页没有{currentView.label}结果。</p>
                )}
                <p className="shortcuts">
                  <kbd>j</kbd>/<kbd>k</kbd> 选择 · <kbd>Enter</kbd> 打开 ·{" "}
                  <kbd>b</kbd> 收藏 · <kbd>s</kbd> 总结 · <kbd>Esc</kbd> 取消
                </p>
              </>
            )}
          </div>
        </main>

        <aside className="workspace-side" aria-label="搜索辅助">
          <QuickBookmarks />
          <div className="workspace-tools">
            <div className="workspace-tools__toggles">
              <button type="button" ref={aiToggle} aria-expanded={sidePanel === "ai"} aria-controls="search-ai"
                onClick={() => setSidePanel(current => current === "ai" ? null : "ai")}>
                <i className="ws-icon ws-icon--spark" aria-hidden="true">✦</i>AI 检索
              </button>
              <button type="button" ref={summaryToggle} aria-expanded={sidePanel === "summary"} aria-controls="search-summary"
                onClick={() => setSidePanel(current => current === "summary" ? null : "summary")}>
                <i className="ws-icon ws-icon--text" aria-hidden="true" />AI 总结
              </button>
              <button type="button" ref={translateToggle} aria-expanded={sidePanel === "translate"} aria-controls="search-translate"
                onClick={() => setSidePanel(current => current === "translate" ? null : "translate")}>
                <i className="ws-icon ws-icon--language" aria-hidden="true">文</i>翻译
              </button>
            </div>
            <div className="workspace-tools__panels">
              <div id="search-ai" hidden={sidePanel !== "ai"}>
                {aiState ? (
                  <AISearchPanel state={aiState} selectedId={selectedId} onSelect={select}
                    onRetry={() => void runAISearch(query, literal)} />
                ) : (
                  <section className="workspace-tool-empty" aria-label="AI 检索">
                    <h2>AI 检索</h2>
                    <p>{dailyAI
                      ? "提交搜索后，AI 检索结果会显示在这里。"
                      : <>在搜索词末尾加 <kbd>ds</kbd>，即可单次启用。</>}</p>
                  </section>
                )}
              </div>
              <div id="search-summary" hidden={sidePanel !== "summary"}>
                <PageBatchSummary />
                {summaryData ? (
                  <SummaryPanel key={summaryData.meta.sid} sid={canSummarize ? summaryData.meta.sid : null}
                    query={summaryData.parsed.q} revealResult={(id) => {
                      if (view !== "all" && !document.getElementById(`result-${id}`)) {
                        flushSync(() => changeView("all"));
                      }
                    }} />
                ) : (
                  <section className="workspace-tool-empty" aria-label="AI 总结">
                    <h2>AI 总结</h2><p>找到搜索结果后，即可生成带引用的总结。</p>
                  </section>
                )}
              </div>
              <div id="search-translate" hidden={sidePanel !== "translate"}>
                <TranslationPanel onSearch={text => {
                  const chars = Array.from(text.replace(/\s+/g, " ").trim());
                  const value = chars.slice(0, 512).join("");
                  changeView("all");
                  setInput(value);
                  setInputLiteral(true);
                  if (chars.length > 512) {
                    document.querySelector<HTMLInputElement>('input[name="q"]')?.focus();
                    return false;
                  }
                  void runSearch(value, { literal: true });
                  return true;
                }} />
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
