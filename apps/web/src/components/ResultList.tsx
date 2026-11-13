import ResultCard from "./ResultCard";
import type { Result } from "../types";

interface Props {
  title: string;
  query?: string;
  saved?: Record<string, number>;
  onBookmarkChange?: (url: string, id: number | null) => void;
  results: Result[];
  hint?: string;
  collapsible?: boolean;
  defaultOpen?: boolean;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export default function ResultList({
  title,
  query,
  saved,
  onBookmarkChange,
  results,
  hint,
  collapsible,
  defaultOpen,
  selectedId,
  onSelect,
}: Props) {
  if (results.length === 0) return null;

  const header = (
    <>
      {title} <span className="group__count">{results.length}</span>
      {hint ? <span className="group__hint">{hint}</span> : null}
    </>
  );

  const cards = (
    <div className="group__list">
      {results.map((result, offset) => (
        <ResultCard
          key={result.id}
          result={result}
          index={offset + 1}
          query={query}
          bookmarkId={saved?.[result.url]}
          onBookmarkChange={onBookmarkChange}
          selected={selectedId === result.id}
          onSelectId={onSelect}
        />
      ))}
    </div>
  );

  if (collapsible) {
    return (
      <details className="group group--collapsible" open={defaultOpen}>
        <summary className="group__title">{header}</summary>
        {cards}
      </details>
    );
  }

  return (
    <section className="group" aria-label={title}>
      <h2 className="group__title">{header}</h2>
      {cards}
    </section>
  );
}