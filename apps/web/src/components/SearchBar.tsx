import { useEffect, useRef } from "react";

interface Props {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function SearchBar({ value, busy, onChange, onSubmit }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      if (event.key === "/" && !typing) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <form
      className="searchbar"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <input
        ref={inputRef}
        className="searchbar__input"
        type="search"
        name="q"
        value={value}
        placeholder="输入关键词，或用 g / b / zh 指定引擎或地区"
        autoComplete="off"
        autoFocus
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        aria-label="搜索查询"
      />
      <button className="searchbar__button" type="submit" disabled={busy || !value.trim()}>
        {busy ? "搜索中…" : "搜索"}
      </button>
    </form>
  );
}
