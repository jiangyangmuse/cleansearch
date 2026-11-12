import { useEffect, useRef, useState } from "react";
import ThemeToggle from "./ThemeToggle";
import { clearSearchHistory, HISTORY_CHANGED, historySearchHref, readSearchHistory, type HistoryEntry } from "../searchHistory";

export default function WorkspaceHeader({ settings = false, onHistorySearch }: {
  settings?: boolean; onHistorySearch?: (entry: HistoryEntry) => void;
}) {
  const [history, setHistory] = useState(readSearchHistory);
  const [showHistory, setShowHistory] = useState(false);
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const sync = () => setHistory(readSearchHistory());
    const dismiss = (event: PointerEvent) => {
      if (menu.current?.open && !menu.current.contains(event.target as Node)) menu.current.open = false;
    };
    window.addEventListener(HISTORY_CHANGED, sync);
    window.addEventListener("storage", sync);
    window.addEventListener("pageshow", sync);
    document.addEventListener("pointerdown", dismiss);
    return () => {
      window.removeEventListener(HISTORY_CHANGED, sync);
      window.removeEventListener("storage", sync);
      window.removeEventListener("pageshow", sync);
      document.removeEventListener("pointerdown", dismiss);
    };
  }, []);

  return (
    <header className="workspace-header">
      <a className="workspace-brand" href="/">
        <span className="workspace-brand__mark" aria-hidden="true"><i className="ws-icon ws-icon--search" /></span>
        CleanSearch
      </a>
      <nav className="workspace-header__actions" aria-label="全站导航">
        <a className="workspace-header__tool" href="/s">单页总结</a>
        <a className="workspace-header__tool" href="/tools">一键添加</a>
        <ThemeToggle />
        <a className="workspace-header__link" href="/bookmarks">
          <i className="ws-icon ws-icon--bookmark" aria-hidden="true" />书签
        </a>
        <a className="workspace-header__link" href="/settings" aria-current={settings ? "page" : undefined}>
          设置
        </a>
        <details ref={menu} className="workspace-more" onKeyDown={(event) => {
          if (event.key === "Escape" && menu.current?.open) {
            event.stopPropagation();
            menu.current.open = false;
            menu.current.querySelector("summary")?.focus();
          }
        }}>
          <summary aria-label="更多" title="更多"><i className="ws-icon ws-icon--more" aria-hidden="true" /></summary>
          <div className="workspace-more__menu">
            <button className="workspace-more__history" type="button" aria-expanded={showHistory}
              aria-controls="workspace-history" onClick={() => setShowHistory(!showHistory)}>
              搜索历史 <i className="ws-icon ws-icon--chevron" aria-hidden="true" />
            </button>
            <div id="workspace-history" hidden={!showHistory}>
              {history.length ? (
                <>
                  <ul>
                    {history.map(entry => (
                      <li key={entry.query}>
                        <a href={historySearchHref(entry)} title={entry.query} onClick={(event) => {
                          if (!onHistorySearch || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                          event.preventDefault();
                          if (menu.current) menu.current.open = false;
                          onHistorySearch(entry);
                        }}>{entry.query}</a>
                      </li>
                    ))}
                  </ul>
                  <button type="button" className="workspace-more__clear" onClick={clearSearchHistory}>清空历史</button>
                </>
              ) : <p>暂无搜索历史。</p>}
            </div>
          </div>
        </details>
      </nav>
    </header>
  );
}
