import { useEffect, useId, useRef, useState } from "react";
import { buildSuggestions, type Suggestion } from "../searchSuggest";
import { HISTORY_CHANGED, readSearchHistory, type HistoryEntry } from "../searchHistory";
import type { EngineInfo } from "../types";

interface Props {
  value: string;
  busy: boolean;
  engines?: EngineInfo[];
  onChange: (value: string) => void;
  /** 提交时可以带上刚选中的建议值，避免用到上一轮的输入状态 */
  onSubmit: (suggestion?: Suggestion) => void;
}

export default function SearchBar({ value, busy, engines = [], onChange, onSubmit }: Props) {
  const [history, setHistory] = useState<HistoryEntry[]>(readSearchHistory);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const composing = useRef(false);
  const suggestions = buildSuggestions(value, history, engines);
  const expanded = open && suggestions.length > 0;
  const active = expanded ? suggestions.findIndex(item => item.id === activeId) : -1;
  const optionId = active >= 0 ? `${listId}-${active}` : undefined;

  const close = () => {
    setOpen(false);
    setActiveId(null);
  };

  useEffect(() => {
    const sync = () => setHistory(readSearchHistory());
    window.addEventListener(HISTORY_CHANGED, sync);
    window.addEventListener("pageshow", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(HISTORY_CHANGED, sync);
      window.removeEventListener("pageshow", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // 输入变化时重置高亮项，避免选中错位的旧建议
  useEffect(() => setActiveId(null), [value]);
  useEffect(() => {
    if (optionId) document.getElementById(optionId)?.scrollIntoView({ block: "nearest" });
  }, [optionId]);

  // 快捷键再次唤起时输入框可能已经聚焦，focus 事件不会重放，由外部显式通知
  useEffect(() => {
    const node = input.current;
    if (!node) return;
    const openList = () => setOpen(true);
    node.addEventListener("cs:search-focus", openList);
    return () => node.removeEventListener("cs:search-focus", openList);
  }, []);

  const choose = (item: Suggestion) => {
    if (busy) return;
    input.current?.focus();
    close();
    onSubmit(item);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (composing.current || event.nativeEvent.isComposing || event.keyCode === 229 ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && suggestions.length) {
      event.preventDefault();
      setOpen(true);
      const next = event.key === "ArrowDown" ? (active + 1) % suggestions.length
        : active <= 0 ? suggestions.length - 1 : active - 1;
      setActiveId(suggestions[next].id);
      return;
    }
    if (event.key === "Enter" && expanded && active >= 0 && suggestions[active]) {
      event.preventDefault();
      choose(suggestions[active]);
      return;
    }
    if (event.key === "Escape" && expanded) {
      // 只收起建议：阻止 type=search 的原生清空，否则会立刻重新展开列表
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) setActiveId(null);
  };

  return (
    <form
      className="searchbar"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        if (busy || composing.current || !value.trim()) return;
        close();
        onSubmit();
      }}
    >
      <div className="searchbar__field">
        <i className="ws-icon ws-icon--search" aria-hidden="true" />
        <input
          className="searchbar__input"
          type="search"
          name="q"
          value={value}
          ref={input}
          placeholder="输入关键词搜索"
          autoComplete="off"
          spellCheck={false}
          role="combobox"
          aria-label="搜索查询"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={expanded ? listId : undefined}
          aria-activedescendant={optionId}
          onChange={(event) => {
            onChange(event.target.value);
            setActiveId(null);
            if (!composing.current) setOpen(true);
          }}
          onCompositionStart={() => { composing.current = true; close(); }}
          onCompositionEnd={() => { composing.current = false; setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={close}
          onKeyDown={onKeyDown}
        />
        {expanded ? (
          <ul className="suggest" id={listId} role="listbox" aria-label="搜索建议">
            {suggestions.map((item, index) => (
              <li key={item.id} id={`${listId}-${index}`} role="option" aria-selected={index === active}
                className={index === active ? "suggest__item suggest__item--active" : "suggest__item"}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(item)}>
                <span className="suggest__label">{item.label}</span>
                <span className="suggest__hint">{item.hint}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <button className="searchbar__button" type="submit" disabled={busy || !value.trim()}>
        {busy ? "搜索中…" : "搜索"}
      </button>
    </form>
  );
}
