import { faviconUrl } from "../api";
import BookmarkButton from "./BookmarkButton";
import type { Result } from "../types";
import { safeHref } from "../url";

interface Props {
  result: Result;
  index: number;
  selected?: boolean;
  onSelect?: () => void;
}

const RISK_FLAG = 0.35;

export default function ResultCard({ result, index, selected, onSelect }: Props) {
  // /go 中转是站内相对地址，直接放行；外链还要过 safeHref
  const goPath = result.go_url && result.go_url.startsWith("/go?u=") ? result.go_url : null;
  const href = goPath ?? safeHref(result.url);
  let host = "";
  try {
    host = new URL(result.url).hostname;
  } catch {
    host = "";
  }
  const flagged = result.risk >= RISK_FLAG;
  const explanation = result.reasons.join("；");

  return (
    <article
      id={`result-${result.id}`}
      tabIndex={-1}
      data-result-id={result.id}
      className={[
        "card",
        flagged ? "card--flagged" : "",
        selected ? "card--selected" : "",
      ].filter(Boolean).join(" ")}
      onMouseEnter={() => onSelect?.()}
      onClick={() => onSelect?.()}
      onFocus={() => onSelect?.()}
    >
      <div className="card__meta">
        <span className="card__index">{index}</span>
        {result.favicon || host ? (
          <img
            className="card__favicon"
            src={faviconUrl(host) ?? result.favicon ?? ""}
            alt=""
            width={16}
            height={16}
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.visibility = "hidden";
            }}
          />
        ) : null}
        <span className="card__url" title={result.url}>
          {result.display_url}
        </span>
        {result.published ? <span className="card__tag">{result.published.slice(0, 10)}</span> : null}
        {result.engine.map((engine) => (
          <span className="card__tag" key={engine}>
            {engine}
          </span>
        ))}
        {flagged ? (
          <span className="card__risk" title={explanation}>
            可疑 · {result.risk.toFixed(2)}
          </span>
        ) : null}
        {result.brand_warning ? <span className="card__risk" title={result.brand_warning}>品牌身份未核验</span> : null}
        {result.go_url ? <span className="card__tag" title="打开前会先确认">中转确认</span> : null}
        <BookmarkButton result={result} />
      </div>
      <h2 className="card__title">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" title={explanation}>
            {result.title}
          </a>
        ) : (
          <span title={result.url}>{result.title}</span>
        )}
      </h2>
      {result.snippet ? <p className="card__snippet">{result.snippet}</p> : null}
    </article>
  );
}
