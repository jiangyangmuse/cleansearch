import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError, bookmarkStatus, getEngines, getSearchProvider, search, searchAI } from "./api";
import AISearchPanel, { type AISearchState } from "./components/AISearchPanel";
import AppShell from "./components/AppShell";
import ContentModules from "./components/ContentModules";
import ConversationSearch, { ConversationForm, useConversationSearch } from "./components/ConversationSearch";
import EngineBar from "./components/EngineBar";
import { engineQuery, hasAISuffix } from "./engineQuery";
import MetaBar from "./components/MetaBar";
import Pager from "./components/Pager";
import OfficialPanel from "./components/OfficialPanel";
import PageBatchSummary from "./components/PageBatchSummary";
import QuickBookmarks from "./components/QuickBookmarks";
import ResultList from "./components/ResultList";
import SearchBar from "./components/SearchBar";
import SearchFilters, { activeFilterCount, describeFilters, filtersFromUrl, sameFilters, type Filters, type FilterPanel } from "./components/SearchFilters";
import ShortcutsDialog from "./components/ShortcutsDialog";
import SummaryPanel from "./components/SummaryPanel";
import ToolDrawer from "./components/ToolDrawer";
import TranslationPanel from "./components/TranslationPanel";
import ResultSkeleton, { SearchProgress } from "./components/ResultSkeleton";
import { EmptyState, ErrorState, searchErrorMessage } from "./components/StatePanel";
import { rememberSearch } from "./searchHistory";
import { readDailyAI, saveDailyAI } from "./searchPreferences";
import { markPanelOpen, markPanelReady, markSearchEnd } from "./perf";
import type { EngineInfo, ResultCategory, SearchResponse } from "./types";
import { safeHref } from "./url";
import { useMediaQuery } from "./useMediaQuery";
import { MAX_PAGE, readUrlState, writeUrl, type HistoryMode } from "./urlState";

/** 与 POST /api/search 的 page 1–10 契约一致 */

type Phase = "idle" | "loading" | "ok" | "empty" | "error" | "shortcut";
type View = "all" | "conversation" | ResultCategory;
type SidePanel = "ai" | "summary" | "translate" | "conversation";
type SearchOptions = {
  filterChange?: boolean;
  page?: number;
  paging?: boolean;
  scroll?: boolean;
  retry?: boolean;
  record?: boolean;
  literal?: boolean;
  /** push 压新历史，replace 改当前条，none 表示这次调用来自 popstate，别再写历史。 */
  urlMode?: HistoryMode;
};

const VIEWS: { id: View; label: string; icon: string }[] = [
  { id: "all", label: "首页", icon: "home" },
  { id: "encyclopedia", label: "百科", icon: "book" },
  { id: "video", label: "视频", icon: "video" },
  { id: "download", label: "下载", icon: "download" },
  { id: "conversation", label: "AI", icon: "spark" },
];

const SAMPLES = [
  { label: "有结果", q: "python 文档" },
  { label: "零结果", q: "__empty 不存在的词" },
  { label: "上游不可用", q: "__fail 上游挂了" },
  { label: "恶意链接", q: "__risky 账号验证" },
];

function viewOf(raw: string): View {
  return VIEWS.find(view => view.id === raw)?.id ?? "all";
}

export default function App() {
  const initial = useRef(readUrlState());
  const [input, setInput] = useState(initial.current.q);
  const [inputLiteral, setInputLiteral] = useState(initial.current.literal);
  const [query, setQuery] = useState(initial.current.q);
  const [literal, setLiteral] = useState(initial.current.literal);
  const [page, setPage] = useState(initial.current.page);
  const [filters, setFilters] = useState(() => filtersFromUrl(initial.current));
  const filtersRef = useRef(filters);
  const filterPanel = useRef<FilterPanel>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [startedAt, setStartedAt] = useState(0);
  const [resultPage, setResultPage] = useState<{ response: SearchResponse; page: number } | null>(null);
  const data = resultPage?.response;
  const resultsRef = useRef<HTMLDivElement>(null);
  const scrollAfterPage = useRef(false);
  // 已收藏网址 → 书签 id，来自批量状态接口与本地乐观更新
  const [savedUrls, setSavedUrls] = useState<Record<string, number>>({});
  const [bookmarkRevision, setBookmarkRevision] = useState(0);
  const bookmarkRequest = useRef<AbortController | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [showSamples, setShowSamples] = useState(false);
  // 当前页面的诊断开关在搜索与分类切换时继续生效。
  const [debugMode] = useState(() => new URLSearchParams(window.location.search).get("debug") === "1");
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 键盘连按时 setState 尚未生效，用 ref 保证 j/k 连续移动不丢步
  const selectedRef = useRef<string | null>(null);
  const select = useCallback((id: string | null) => {
    selectedRef.current = id;
    setSelectedId(id);
  }, []);
  const [view, setView] = useState<View>(() => viewOf(initial.current.category));
  // 写 URL 与 popstate 还原都要读最新值，避免闭包拿到上一轮状态
  const queryRef = useRef(initial.current.q);
  const pageRef = useRef(initial.current.page);
  const literalRef = useRef(initial.current.literal);
  const viewRef = useRef<View>(view);
  const conversation = useConversationSearch();
  const [sidePanel, setSidePanel] = useState<SidePanel | null>(null);
  const drawerMode = useMediaQuery("(max-width: 900px)");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerToggle = useRef<HTMLButtonElement>(null);
  const lastPanel = useRef<SidePanel>("summary");
  const aiToggle = useRef<HTMLButtonElement>(null);
  const summaryToggle = useRef<HTMLButtonElement>(null);
  const translateToggle = useRef<HTMLButtonElement>(null);
  const conversationToggle = useRef<HTMLButtonElement>(null);
  const enginesDisclosure = useRef<HTMLDetailsElement>(null);
  const controller = useRef<AbortController | null>(null);
  const aiController = useRef<AbortController | null>(null);
  const [dailyAI, setDailyAI] = useState(readDailyAI);
  const dailyAIRef = useRef(dailyAI);
  const [aiState, setAIState] = useState<AISearchState | null>(null);
  // 面板收起后仍在跑的流：结果区顶部给「后台生成中」提示与停止入口
  const [summaryBusy, setSummaryBusy] = useState(false);
  const aiBusy = aiState?.phase === "loading";
  const visibleTool = drawerMode && !drawerOpen ? null : sidePanel;
  const summaryInBackground = summaryBusy && visibleTool !== "summary";
  const aiInBackground = aiBusy && (visibleTool !== "ai" || view === "conversation");
  const bootstrapped = useRef(false);

  const changeView = useCallback((next: View, mode: HistoryMode = "push") => {
    filterPanel.current?.close();
    viewRef.current = next;
    setView(next);
    select(null);
    if (enginesDisclosure.current) enginesDisclosure.current.open = false;
    writeUrl({
      q: queryRef.current, literal: literalRef.current, page: pageRef.current, category: next,
      range: filtersRef.current.timeRange, lang: filtersRef.current.language,
      site: filtersRef.current.site, dedupe: filtersRef.current.dedupe,
    }, mode);
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
    const { page: nextPage = 1, paging = false, scroll = false, retry = false, record = true, literal = false, urlMode = "push", filterChange = false } = options;
    const q = raw.trim();
    if (!q) return;
    if (!filterChange) filterPanel.current?.close();
    scrollAfterPage.current = scroll;
    if (enginesDisclosure.current) enginesDisclosure.current.open = false;
    if (record && !paging) rememberSearch({ query: q, literal });
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    if (!paging && !retry && !filterChange) {
      if (urlMode !== "none" && (dailyAIRef.current || (!literal && hasAISuffix(q)))) {
        void runAISearch(q, literal);
      } else {
        aiController.current?.abort();
        setAIState(null);
        setSidePanel(panel => panel === "ai" ? null : panel);
      }
    }

    const searchStarted = performance.now();
    queryRef.current = q;
    pageRef.current = nextPage;
    literalRef.current = literal;
    setQuery(q);
    setLiteral(literal);
    setPage(nextPage);
    setStartedAt(searchStarted);
    const results = resultsRef.current;
    if (results?.contains(document.activeElement)) results.focus({ preventScroll: true });
    setPhase("loading");
    setError(null);
    // 新查询清掉旧结果（骨架），翻页保留旧列表并降透明度
    if (!paging) setResultPage(null);
    select(null);
    if (!paging) setSidePanel(currentPanel => currentPanel === "summary" ? null : currentPanel);
    // 新查询、分类、页码都进历史；重试与 popstate 还原不重复入栈。
    writeUrl({
      q, literal, page: nextPage, category: viewRef.current,
      range: filtersRef.current.timeRange, lang: filtersRef.current.language,
      site: filtersRef.current.site, dedupe: filtersRef.current.dedupe,
    }, urlMode);

    try {
      const active = filtersRef.current;
      const response = await search({
        q,
        page: nextPage,
        opts: {
          safe: true,
          literal,
          time_range: active.timeRange || null,
          language: active.language || null,
          site: active.site || null,
          dedupe: active.dedupe,
        },
      }, current.signal);
      if (current.signal.aborted) return;
      if (activeFilterCount(active) && !response.meta.filters) {
        throw new ApiError("当前本机服务尚未支持搜索筛选，请重新加载新版后端", "FILTERS_UNAVAILABLE", 409);
      }
      markSearchEnd(searchStarted);
      setResultPage({ response, page: nextPage });
      if (response.parsed.open_url) {
        aiController.current?.abort();
        setAIState(null);
        setSidePanel(panel => panel === "ai" ? null : panel);
        setPhase("shortcut");
        return;
      }
      const hasOfficial = (response.official?.entries.length ?? 0) > 0;
      setPhase(response.meta.total > 0 || hasOfficial ? "ok" : "empty");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (current.signal.aborted) return;
      setResultPage(null);
      setError(caught instanceof ApiError ? caught : new ApiError("未知错误，查看浏览器控制台", "UNKNOWN", 0));
      setPhase("error");
    } finally {
      // 每次请求后刷新健康状态；旧请求的目录响应不能覆盖新请求。
      if (!current.signal.aborted) {
        void getEngines(current.signal).then((payload) => {
          if (!current.signal.aborted) setEngines(payload.engines);
        }).catch(() => { /* 目录失败不影响搜索结果 */ });
      }
    }
  }, [runAISearch, select]);

  /** 翻到目标页：夹在 1–10，保留当前查询/字面模式，并记为需要滚回结果顶部。 */
  const goToPage = useCallback((next: number) => {
    const target = Math.min(MAX_PAGE, Math.max(1, next));
    if (target === pageRef.current) return;
    void runSearch(queryRef.current, {
      page: target, paging: true, scroll: true, literal: literalRef.current, urlMode: "push",
    });
  }, [runSearch]);

  // 面板内容渲染完成：结束「面板打开耗时」测量
  useEffect(() => {
    if ((!drawerMode || drawerOpen) && (sidePanel || drawerOpen)) markPanelReady();
  }, [sidePanel, drawerOpen, drawerMode]);

  // 结果到达后批量查已收藏状态（结果卡 + 官方入口，最多 40 个）
  useEffect(() => {
    if (!resultPage) {
      setSavedUrls({});
      return;
    }
    const urls = new Set<string>();
    const collect = (items: { url: string }[]) => items.forEach(item => {
      if (safeHref(item.url)) urls.add(item.url);
    });
    const { groups, official } = resultPage.response;
    collect([...groups.strong, ...groups.related, ...groups.weak]);
    if (official) collect(official.entries);
    if (!urls.size) {
      setSavedUrls({});
      return;
    }
    const refresh = () => {
      bookmarkRequest.current?.abort();
      const request = new AbortController();
      bookmarkRequest.current = request;
      void bookmarkStatus([...urls], request.signal).then(map => {
        if (!request.signal.aborted) setSavedUrls(map);
      }).catch(() => { /* 状态查询失败不影响结果展示 */ });
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) refresh();
    };
    refresh();
    window.addEventListener("pageshow", onPageShow);
    return () => {
      bookmarkRequest.current?.abort();
      window.removeEventListener("pageshow", onPageShow);
    };
  }, [bookmarkRevision, resultPage]);

  const rememberBookmark = useCallback((url: string, id: number | null) => {
    bookmarkRequest.current?.abort();
    setSavedUrls(current => {
      const next = { ...current };
      if (id != null) next[url] = id;
      else {
        const removed = current[url];
        delete next[url];
        for (const key of Object.keys(next)) {
          if (next[key] === removed) delete next[key];
        }
      }
      return next;
    });
    setBookmarkRevision(revision => revision + 1);
  }, []);

  // 翻页完成后回到结果区顶部，避免停在页面中段
  useEffect(() => {
    if (phase === "loading" || !scrollAfterPage.current) return;
    scrollAfterPage.current = false;
    if ((phase === "ok" || phase === "empty" || phase === "error") && view !== "conversation") {
      resultsRef.current?.scrollIntoView({ block: "start" });
    }
  }, [phase, resultPage, view]);

  useEffect(() => {
    const onPopState = () => {
      const restored = readUrlState();
      const nextView = viewOf(restored.category);
      const q = restored.q.trim();
      const sameQuery = q === queryRef.current && restored.literal === literalRef.current;
      const nextFilters = filtersFromUrl(restored);
      const filtersUnchanged = sameFilters(nextFilters, filtersRef.current);
      const sameSearch = sameQuery && filtersUnchanged && restored.page === pageRef.current;
      filterPanel.current?.close();
      if (sameSearch && nextView === viewRef.current) return; // 例如从跳转链接的 #main 返回

      if (!filtersUnchanged) {
        filtersRef.current = nextFilters;
        setFilters(nextFilters);
      }
      changeView(nextView, "none");
      setInput(restored.q);
      setInputLiteral(restored.literal);
      setDrawerOpen(false);
      if (!q) {
        scrollAfterPage.current = false;
        controller.current?.abort();
        controller.current = null;
        aiController.current?.abort();
        setAIState(null);
        setSidePanel(null);
        queryRef.current = "";
        pageRef.current = 1;
        literalRef.current = false;
        setQuery("");
        setLiteral(false);
        setPage(1);
        setResultPage(null);
        setError(null);
        setPhase("idle");
      } else if (!sameSearch) {
        void runSearch(q, {
          page: restored.page, paging: sameQuery && filtersUnchanged, literal: restored.literal,
          record: false, urlMode: "none",
        });
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [changeView, runSearch]);

  // 标题跟随查询与页码，多标签、历史记录、分享预览才有辨识度。
  useEffect(() => {
    if (view === "conversation") {
      document.title = "AI 对话搜索 · CleanSearch";
    } else if (!query) {
      document.title = "CleanSearch";
    } else {
      document.title = page > 1 ? `第 ${page} 页 · ${query} · CleanSearch` : `${query} · CleanSearch`;
    }
  }, [view, query, page]);

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
    if (bootstrapped.current || view === "conversation") return;
    bootstrapped.current = true;
    const state = readUrlState();
    const initialQuery = state.q.trim();
    if (initialQuery && !controller.current) {
      void runSearch(initialQuery, {
        page: state.page, paging: state.page > 1, record: false,
        literal: state.literal, urlMode: "replace",
      });
    }
  }, [runSearch, view]);

  // 引擎后缀弹层：点外部、滚动、路由变化都收起，避免遮挡统计与结果。
  useEffect(() => {
    const close = (event: PointerEvent) => {
      const target = event.target as Node;
      const disclosure = enginesDisclosure.current;
      if (disclosure?.open && !disclosure.contains(target)) disclosure.open = false;
      // 卡片右上角的操作菜单也只在点它自己时保持打开
      document.querySelectorAll<HTMLDetailsElement>("details.card__actions[open]").forEach(node => {
        if (!node.contains(target)) node.open = false;
      });
    };
    const onScroll = () => {
      const disclosure = enginesDisclosure.current;
      if (disclosure?.open) disclosure.open = false;
    };
    document.addEventListener("pointerdown", close);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

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
      if (!check.signal.aborted && !controller.current) setEngines(payload.engines);
    }).catch(() => { /* 引擎目录不可用时保持纯文本后缀 */ });
    return () => check.abort();
  }, []);

  // 回到桌面宽度时收起抽屉，避免抽屉在后台保持「打开」语义。
  useEffect(() => {
    if (!drawerMode) setDrawerOpen(false);
  }, [drawerMode]);

  useEffect(() => {
    const results = resultsRef.current;
    if (phase === "loading" || results !== document.activeElement) return;
    const target = results?.querySelector<HTMLElement>(".state--error button, .state--empty h2, .pager__label, .state--shortcut h2");
    target?.focus();
  }, [phase, page, view]);

  const pickEngine = useCallback(
    (code: string) => {
      const next = engineQuery(input, code, engines, inputLiteral);
      if (next === null) return;
      if (enginesDisclosure.current) enginesDisclosure.current.open = false;
      setInput(next);
      setInputLiteral(false);
      void runSearch(next, { urlMode: "push" });
    },
    [input, inputLiteral, engines, runSearch],
  );

  const togglePanel = (panel: SidePanel) => {
    if (sidePanel !== panel) markPanelOpen();
    lastPanel.current = panel;
    setSidePanel(current => current === panel ? null : panel);
  };

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSidePanel(null);
  }, []);

  const showBackgroundTask = (panel: "ai" | "summary") => {
    markPanelOpen();
    if (drawerMode) drawerToggle.current?.focus({ preventScroll: true });
    flushSync(() => {
      if (panel === "ai" && view === "conversation") changeView("all");
      lastPanel.current = panel;
      setSidePanel(panel);
      if (drawerMode) setDrawerOpen(true);
    });
    (panel === "ai" ? aiToggle : summaryToggle).current?.focus();
  };

  const stopBackgroundTask = (panel: "ai" | "summary", button: HTMLButtonElement) => {
    if (button === document.activeElement) {
      const target = drawerMode ? drawerToggle.current : panel === "ai" ? aiToggle.current : summaryToggle.current;
      if (target?.getClientRects().length) target.focus({ preventScroll: true });
      else document.getElementById("main")?.focus({ preventScroll: true });
    }
    if (panel === "summary") {
      window.dispatchEvent(new Event("cs:summary-stop"));
    } else {
      aiController.current?.abort();
      setAIState(null);
      setSidePanel(current => current === "ai" ? null : current);
    }
  };

  const groups = data?.groups ?? { strong: [], related: [], weak: [] };
  const groupedContent = [...groups.strong, ...groups.related, ...groups.weak];
  const currentView = VIEWS.find(item => item.id === view) ?? VIEWS[0];
  const externalSearch = data?.parsed.open_url ? safeHref(data.parsed.open_url, 8192) : null;
  const categoryResults = groupedContent.filter(item => item.category === view);
  const pageResultCount = view === "all" ? (data?.meta.total ?? 0) : categoryResults.length;
  const canNext = (data?.meta.total ?? 0) > 0;
  const summaryData = phase === "ok" ? data : null;
  const canSummarize = summaryData && (
    groupedContent.some(item => !item.brand_warning) ||
    summaryData.official?.entries.some(entry => entry.origin !== "directory")
  );

  const parsed = data?.parsed;
  const routedSuffix = parsed?.router === "bang" ? /\s*!([a-z][a-z0-9]{0,7})$/i : /\s+([a-z][a-z0-9]{0,7})$/i;
  const suffixMatch = !literal && parsed && parsed.router !== "default" && parsed.engine !== "default" &&
    routedSuffix.exec(query.normalize("NFKC"));
  const removableSuffix = suffixMatch && query.normalize("NFKC").slice(0, suffixMatch.index).trim() === parsed?.q
    ? { label: `取消引擎后缀 ${parsed.router === "bang" ? "!" : ""}${suffixMatch[1]}`, base: parsed.q }
    : null;
  const otherCategoryCount = Math.max(0, (data?.meta.total ?? 0) - categoryResults.length);
  const officialCount = data?.official?.entries.length ?? 0;
  const showDiagnostics = showSamples || debugMode;

  const focusSearch = useCallback(() => {
    const field = document.querySelector<HTMLInputElement>('input[name="q"]');
    field?.focus();
    field?.select();
  }, []);

  const clearSuffix = removableSuffix ? {
    label: removableSuffix.label,
    action: () => {
      setInput(removableSuffix.base);
      setInputLiteral(true);
      void runSearch(removableSuffix.base, { literal: true });
    },
  } : undefined;
  const viewAllResults = () => {
    resultsRef.current?.focus({ preventScroll: true });
    changeView("all");
  };

  const resultCount = data ? data.meta.total + (data.meta.official ?? 0) : 0;
  // 翻页时保留旧列表（降透明），新查询才用骨架，避免高度塌陷
  const showStale = phase === "loading" && resultCount > 0;
  const pageProgress = `正在加载第 ${page} 页`;
  const categoryCount = `本页${currentView.label} ${categoryResults.length} 条 · 本页搜索结果 ${data?.meta.total ?? 0} 条`;
  let announcement = "";
  if (phase === "loading") announcement = showStale ? pageProgress : `正在检索 ${query}`;
  if (phase === "ok") announcement = view === "all" ? `找到 ${resultCount} 条结果` : categoryCount;
  if (phase === "empty") announcement = `本页没有可展示的结果`;
  if (phase === "error" && error) {
    const { title, detail } = searchErrorMessage(error);
    announcement = `${title}。${detail}`;
  }
  const pageTitle = query ? `搜索：${query}` : "CleanSearch 搜索";
  const taskAnnouncement = [summaryInBackground && "AI 总结正在后台生成。",
    aiInBackground && "AI 检索仍在进行。"].filter(Boolean).join(" ");

  useEffect(() => {
    let pendingG = false;
    let pendingTimer = 0;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && filterPanel.current?.isOpen()) return;
      if (shortcutsOpen || drawerOpen || event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      const typing = target?.closest("input, textarea, select, [role=textbox]") || target?.isContentEditable;
      // ? 是 Shift+/，要在过滤 shiftKey 之前处理；输入框里打问号不算
      if (!typing && !event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey
        && event.key === "?") {
        event.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      if (event.altKey || event.shiftKey) return;
      if (view !== "conversation" && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const field = document.querySelector<HTMLInputElement>('input[name="q"]');
        field?.focus();
        // 已经聚焦时 focus 不会再触发，显式让建议列表重新展开
        field?.dispatchEvent(new CustomEvent("cs:search-focus", { bubbles: true }));
        return;
      }
      if (event.ctrlKey || event.metaKey) return;

      if (event.key === "Escape") {
        select(null);
        pendingG = false;
        const disclosure = enginesDisclosure.current;
        if (disclosure?.open) {
          disclosure.open = false;
          if (disclosure.contains(target)) disclosure.querySelector("summary")?.focus();
          return;
        }
        const openActions = document.querySelectorAll<HTMLDetailsElement>("details.card__actions[open]");
        if (openActions.length) {
          openActions.forEach(node => {
            if (node.contains(target)) node.querySelector("summary")?.focus({ preventScroll: true });
            node.open = false;
          });
          return;
        }
        if (sidePanel) {
          setSidePanel(null);
          ({ ai: aiToggle, summary: summaryToggle, translate: translateToggle,
            conversation: conversationToggle })[sidePanel].current?.focus();
        } else if (typing) {
          target?.blur();
        }
        return;
      }
      if (event.key === "/" && !typing) {
        event.preventDefault();
        document.querySelector<HTMLElement>(
          view === "conversation" ? 'textarea[name="conversation"]' : 'input[name="q"]',
        )?.focus();
        return;
      }
      if (typing) {
        pendingG = false;
        return;
      }

      if ((event.key === "[" || event.key === "]") && view !== "conversation" &&
          (phase === "ok" || phase === "empty")) {
        if (event.key === "[" ? page > 1 : canNext && page < MAX_PAGE) {
          event.preventDefault();
          goToPage(page + (event.key === "]" ? 1 : -1));
        }
        return;
      }

      if (event.key === "g") {
        if (event.repeat) return;
        pendingG = true;
        window.clearTimeout(pendingTimer);
        pendingTimer = window.setTimeout(() => { pendingG = false; }, 800);
        return;
      }
      if (pendingG && (event.key === "h" || event.key === "s")) {
        window.location.href = "/";
        return;
      }
      if (pendingG && event.key === "b") {
        window.location.href = "/bookmarks";
        return;
      }
      pendingG = false;
      if (event.key === "s" && phase === "ok" && view !== "conversation") {
        if (sidePanel !== "summary" || (drawerMode && !drawerOpen)) markPanelOpen();
        flushSync(() => {
          lastPanel.current = "summary";
          setSidePanel("summary");
          if (drawerMode) setDrawerOpen(true);
        });
        window.dispatchEvent(new CustomEvent("cs:summarize"));
        return;
      }

      // 保留的旧卡只用于撑住布局。
      const list = Array.from(document.querySelectorAll<HTMLElement>(".workspace [id^='result-']"))
        .filter(card => card.getClientRects().length && !card.closest("[inert], details:not([open])"));
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
        if (!event.repeat) {
          // 收藏按钮现在在卡片菜单里：先展开，操作结果才看得见
          const menu = card?.querySelector<HTMLDetailsElement>("details.card__actions");
          if (menu) {
            menu.open = true;
            menu.querySelector("summary")?.focus({ preventScroll: true });
          }
          card?.querySelector<HTMLButtonElement>(".card__save")?.click();
        }
        return;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.clearTimeout(pendingTimer);
    };
  }, [canNext, drawerMode, drawerOpen, goToPage, page, phase, select, shortcutsOpen, sidePanel, view]);

  const applyFilters = useCallback((next: Filters) => {
    if (sameFilters(next, filtersRef.current)) return;
    setFilters(next);
    filtersRef.current = next;
    if (!queryRef.current) {
      writeUrl({
        q: "", literal: literalRef.current, page: 1, category: viewRef.current,
        range: next.timeRange, lang: next.language, site: next.site, dedupe: next.dedupe,
      }, "replace");
      return;
    }
    // 换筛选条件从第 1 页重新检索，并压一条历史便于回退
    void runSearch(queryRef.current, { literal: literalRef.current, urlMode: "push", filterChange: true, record: false });
  }, [runSearch]);

  const toolsBlock = (
    <div className="workspace-tools">
      <div className="workspace-tools__tabs" role="group" aria-label="AI 与翻译工具">
        <button type="button" aria-expanded={sidePanel === "ai"} aria-controls="search-ai"
          ref={aiToggle} hidden={view === "conversation"}
          onClick={() => togglePanel("ai")}>
          <i className="ws-icon ws-icon--spark" aria-hidden="true">✦</i>AI 检索
        </button>
        <button type="button" aria-expanded={sidePanel === "summary"}
          aria-controls="search-summary" ref={summaryToggle}
          onClick={() => togglePanel("summary")}>
          <i className="ws-icon ws-icon--text" aria-hidden="true" />AI 总结
        </button>
        <button type="button" aria-expanded={sidePanel === "translate"}
          aria-controls="search-translate" ref={translateToggle}
          onClick={() => togglePanel("translate")}>
          <i className="ws-icon ws-icon--language" aria-hidden="true">文</i>翻译
        </button>
        <button type="button" aria-expanded={sidePanel === "conversation"}
          aria-controls="search-conversation" aria-label="AI 对话搜索" ref={conversationToggle}
          onClick={() => togglePanel("conversation")}>
          <i className="ws-icon ws-icon--spark" aria-hidden="true">✦</i>AI 对话
        </button>
      </div>
      <div className="workspace-tools__panels">
        <div id="search-ai" hidden={sidePanel !== "ai" || view === "conversation"}>
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
              onBusyChange={setSummaryBusy}
              query={summaryData.parsed.q} revealResult={(id) => {
                flushSync(() => {
                  if (view === "conversation" || (view !== "all" && !document.getElementById(`result-${id}`))) {
                    changeView("all");
                  }
                  if (drawerOpen) closeDrawer();
                });
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
            flushSync(() => {
              changeView("all", chars.length > 512 ? "push" : "none");
              setInput(value);
              setInputLiteral(true);
              if (drawerOpen) closeDrawer();
            });
            document.querySelector<HTMLInputElement>('input[name="q"]')?.focus();
            if (chars.length > 512) {
              return false;
            }
            void runSearch(value, { literal: true, urlMode: "push" });
            return true;
          }} />
        </div>
        <div id="search-conversation" hidden={sidePanel !== "conversation"}>
          <section className="workspace-task" aria-label="AI 对话搜索入口">
            <h2>AI 对话搜索</h2>
            <ConversationForm compact busy={conversation.busy} onSubmit={message => {
              changeView("conversation");
              setSidePanel(null);
              setDrawerOpen(false);
              void conversation.send(message);
            }} />
          </section>
        </div>
      </div>
    </div>
  );

  return (
    <AppShell maxWidth={1560} current="search" onHistorySearch={({ query: previous, literal: previousLiteral }) => {
      changeView("all", "none");
      setInput(previous);
      setInputLiteral(previousLiteral);
      void runSearch(previous, { literal: previousLiteral, urlMode: "push" });
    }}>
      <div className="workspace">
        <nav className="workspace-nav" aria-label="搜索分类">
          <div className="workspace-nav__items">
            {VIEWS.map(({ id, label, icon }) => (
              <button key={id} type="button" className="workspace-nav__item"
                aria-current={view === id ? "true" : undefined} onClick={() => changeView(id)}>
                <i className={`ws-icon ws-icon--${icon}`} aria-hidden="true">{id === "conversation" ? "✦" : null}</i>{label}
              </button>
            ))}
          </div>
        </nav>

        <main className="workspace-main" id="main" tabIndex={-1}>
          {view !== "conversation" && <>
            <h1 className="sr-only">{pageTitle}</h1>
          </>}
          <p className="sr-only" role="status" aria-live="polite">
            {[view !== "conversation" && announcement, taskAnnouncement].filter(Boolean).join(" ")}
          </p>
          <div className="workspace-search" hidden={view === "conversation"}>
            <SearchBar value={input} busy={phase === "loading"} engines={engines} onChange={value => {
              setInput(value);
              setInputLiteral(false);
            }} onSubmit={suggestion => {
              const value = (suggestion?.insert ?? input).trim();
              const nextLiteral = suggestion?.literal ?? inputLiteral;
              if (!value) return;
              setInput(value);
              setInputLiteral(nextLiteral);
              void runSearch(value, { literal: nextLiteral, urlMode: "push" });
            }} />
            <div className="workspace-search__options">
              {engines.length > 0 && (
                <details className="workspace-engines" ref={enginesDisclosure}>
                  <summary>引擎后缀 <i className="ws-icon ws-icon--chevron" aria-hidden="true" /></summary>
                  <EngineBar engines={engines} busy={phase === "loading"}
                    canPick={engineQuery(input, "g", engines, inputLiteral) !== null} onPick={pickEngine} />
                </details>
              )}
              <SearchFilters ref={filterPanel} filters={filters} onChange={applyFilters} />
              {activeFilterCount(filters) > 0 ? (
                <span className="workspace-filter-note">已筛选：{describeFilters(filters)}</span>
              ) : null}
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
                    void runSearch(sample.q, { urlMode: "push" });
                  }}>
                    {sample.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {(["summary", "ai"] as const).map(panel => {
            if (panel === "summary" ? !summaryInBackground : !aiInBackground) return null;
            const task = panel === "summary" ? "AI 总结" : "AI 检索";
            return (
              <div key={panel} className="background-task" role="group" aria-label={task}>
                <span className="background-task__dot" aria-hidden="true" />
                <span>{panel === "summary" ? "AI 总结正在后台生成" : "AI 检索仍在进行"}</span>
                <button type="button" className="background-task__action"
                  aria-label={`查看${task}`} onClick={() => showBackgroundTask(panel)}>
                  查看
                </button>
                <button type="button" className="background-task__action"
                  aria-label={`停止${task}`} onClick={event => stopBackgroundTask(panel, event.currentTarget)}>
                  停止
                </button>
              </div>
            );
          })}
          <div className="workspace-results" ref={resultsRef} tabIndex={-1} hidden={view === "conversation"}>
            {view !== "all" && <h2 className="workspace-results__title">{currentView.label}</h2>}
            {view !== "all" && phase === "idle" && (
              <p className="workspace-results__hint">输入关键词，查看{currentView.label}结果。</p>
            )}
            {phase === "loading" && (showStale
              ? <SearchProgress key={startedAt} className="results-progress" label={pageProgress} startedAt={startedAt} />
              : <ResultSkeleton key={startedAt} query={query} startedAt={startedAt} />)}
            {phase === "error" && error && (
              <ErrorState error={error} query={query} diagnostics={showDiagnostics} onChangeKeyword={focusSearch}
                onRetry={() => void runSearch(query, { page, paging: page > 1, retry: true, literal, record: false, urlMode: "replace" })} />
            )}
            {phase === "shortcut" && (
              <section className="state state--shortcut" aria-label="网页直达">
                <h2 tabIndex={-1}>网页直达</h2>
                {externalSearch ? (
                  <>
                    <p>{new URL(externalSearch).hostname} · {data?.parsed.q}</p>
                    <a className="button button--ghost" href={externalSearch} target="_blank" rel="noopener noreferrer">
                      在新标签页打开搜索 ↗
                    </a>
                  </>
                ) : <p>无法打开此搜索链接，请检查设置中的网址模板。</p>}
              </section>
            )}
            {phase === "empty" && (
              <>
                <EmptyState title="本页没有结果" detail={`查询「${query}」在本页没有可展示的结果。`}
                  onChangeKeyword={focusSearch} clearSuffix={clearSuffix} />
                {page > 1 && (
                  <Pager page={page} count={0} canNext={false}
                    position="top" onPrev={() => void goToPage(page - 1)}
                    onNext={() => void goToPage(page + 1)} />
                )}
              </>
            )}
            {(phase === "ok" || showStale) && resultPage && data && (
              <div className="results-body" aria-busy={showStale || undefined} inert={showStale}>
                {view === "all" && (
                  <>
                    <MetaBar meta={data.meta} parsed={data.parsed} />
                    <OfficialPanel section={data.official} selectedId={selectedId} onSelect={select}
                      saved={savedUrls} onBookmarkChange={rememberBookmark} />
                    {data.parsed.expanded.length > 0 && (
                      <p className="shortcuts">已扩展同义词：{data.parsed.expanded.join(" / ")}</p>
                    )}
                  </>
                )}
                <Pager page={resultPage.page} count={pageResultCount} canNext={canNext} busy={showStale} position="top"
                  onPrev={() => void goToPage(resultPage.page - 1)}
                  onNext={() => void goToPage(resultPage.page + 1)} />
                {view === "all" ? (
                  <>
                    <ContentModules results={groupedContent} selectedId={selectedId} onSelect={select}
                      query={data.parsed.q} saved={savedUrls} onBookmarkChange={rememberBookmark} />
                    <ResultList title="强相关" results={groups.strong.filter(result => !result.category)}
                      query={data.parsed.q} saved={savedUrls} onBookmarkChange={rememberBookmark}
                      selectedId={selectedId} onSelect={select} />
                    <ResultList title="相关" results={groups.related.filter(result => !result.category)}
                      query={data.parsed.q} saved={savedUrls} onBookmarkChange={rememberBookmark}
                      selectedId={selectedId} onSelect={select} />
                    <ResultList title="弱相关" results={groups.weak.filter(result => !result.category)}
                      query={data.parsed.q} saved={savedUrls} onBookmarkChange={rememberBookmark}
                      collapsible defaultOpen={false} selectedId={selectedId} onSelect={select} />
                  </>
                ) : categoryResults.length ? (
                  <>
                    <p className="workspace-results__count">{categoryCount}</p>
                    <ResultList title={`${currentView.label}结果`} results={categoryResults}
                      query={data.parsed.q} saved={savedUrls} onBookmarkChange={rememberBookmark}
                      selectedId={selectedId} onSelect={select} />
                  </>
                ) : (
                  <EmptyState title={`本页没有${currentView.label}结果`}
                    detail={[
                      otherCategoryCount > 0 ? `本页还有 ${otherCategoryCount} 条其它结果。` : "",
                      officialCount > 0 ? `另有 ${officialCount} 个官方入口。` : "",
                    ].join("")}
                    onChangeKeyword={focusSearch} onViewAll={viewAllResults} />
                )}
                <Pager page={resultPage.page} count={pageResultCount} canNext={canNext} busy={showStale} position="bottom"
                  onPrev={() => void goToPage(resultPage.page - 1)}
                  onNext={() => void goToPage(resultPage.page + 1)} />
                <div className="shortcuts-footer">
                  <p className="shortcuts">
                    <kbd>j</kbd>/<kbd>k</kbd> 选择 · <kbd>Enter</kbd> 打开 ·{" "}
                    <kbd>b</kbd> 收藏 · <kbd>s</kbd> 总结 · <kbd>[</kbd>/<kbd>]</kbd> 翻页 · <kbd>Esc</kbd> 取消
                  </p>
                  <button type="button" className="shortcuts__open"
                    aria-haspopup="dialog" onClick={() => setShortcutsOpen(true)}>
                    <kbd>?</kbd> 全部快捷键
                  </button>
                </div>
              </div>
            )}
          </div>
          {view === "conversation" && (
            <ConversationSearch conversation={conversation} selectedId={selectedId} onSelect={select} />
          )}
        </main>

        {drawerMode ? (
          <>
            <button type="button" className="workspace-drawer-fab" ref={drawerToggle}
              aria-expanded={drawerOpen} aria-controls="tool-drawer" aria-haspopup="dialog"
              onClick={() => {
                markPanelOpen();
                const panel = sidePanel ?? lastPanel.current;
                setSidePanel(view === "conversation" && panel === "ai" ? "summary" : panel);
                setDrawerOpen(true);
              }}>
              <i className="ws-icon ws-icon--spark" aria-hidden="true">✦</i>工具
            </button>
            <ToolDrawer id="tool-drawer" open={drawerOpen} label="搜索工具" onClose={closeDrawer}>
              <QuickBookmarks active={drawerOpen} />
              {toolsBlock}
            </ToolDrawer>
          </>
        ) : (
          <aside className="workspace-side" aria-label="搜索辅助">
            <QuickBookmarks />
            {toolsBlock}
          </aside>
        )}
      </div>
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </AppShell>
  );
}
