import { useState } from "react";
import { ApiError, faviconUrl, saveBookmark } from "../api";
import type { Result } from "../types";
import { safeHref } from "../url";

interface Props {
  result: Result;
  index: number;
  selected?: boolean;
  onSelect?: () => void;
}

const RISK_FLAG = 0.35;

type SaveState = "idle" | "saving" | "saved" | "exists" | "error";

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

  const [saveState, setSaveState] = useState<SaveState>("idle");

  const save = async () => {
    if (saveState === "saving" || saveState === "saved" || saveState === "exists") return;
    setSaveState("saving");
    try {
      const response = await saveBookmark({ url: result.url, title: result.title });
      setSaveState(response.deduplicated ? "exists" : "saved");
    } catch (caught) {
      setSaveState("error");
      if (!(caught instanceof ApiError)) console.error(caught);
    }
  };

  const saveLabel =
    saveState === "saving"
      ? "收藏中…"
      : saveState === "saved"
        ? "已收藏"
        : saveState === "exists"
          ? "已在书签"
          : saveState === "error"
            ? "收藏失败"
            : "收藏";

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
        {result.go_url ? <span className="card__tag" title="打开前会先确认">中转确认</span> : null}
        <button
          className={`card__save card__save--${saveState}`}
          type="button"
          onClick={() => void save()}
          disabled={saveState === "saving"}
          title="收藏到本机书签"
        >
          {saveLabel}
        </button>
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