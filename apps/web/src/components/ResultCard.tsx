import { Fragment, memo, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { faviconUrl } from "../api";
import BookmarkButton from "./BookmarkButton";
import { breadcrumb, splitHighlight, searchTerms } from "../highlight";
import type { Result } from "../types";
import { safeHref } from "../url";

interface Props {
  result: Result;
  index: number;
  /** 当前查询，用于标题/摘要高亮 */
  query?: string;
  /** 批量状态接口给出的书签 id */
  bookmarkId?: number;
  onBookmarkChange?: (url: string, id: number | null) => void;
  selected?: boolean;
  /** 传 id 而不是闭包，配合 memo 才能真的跳过重渲染 */
  onSelectId?: (id: string) => void;
}

const RISK_FLAG = 0.35;
const MAX_ENGINE_TAGS = 2;
const SNIPPET_LINES = 3;

function Marked({ text, terms }: { text: string; terms: string[] }) {
  const segments = splitHighlight(text, terms);
  return <>{segments.map((segment, index) => segment.hit
    ? <mark className="hl" key={index}>{segment.text}</mark>
    : <Fragment key={index}>{segment.text}</Fragment>)}</>;
}

function ResultCard({ result, index, query = "", bookmarkId, onBookmarkChange, selected, onSelectId }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [clipped, setClipped] = useState(false);
  const [feedback, setFeedback] = useState("");
  const actions = useRef<HTMLDetailsElement>(null);
  const actionTimer = useRef<number | undefined>(undefined);
  const snippet = useRef<HTMLParagraphElement>(null);
  const snippetId = useId();
  const terms = searchTerms(query);
  const title = breadcrumb(result.url, result.display_url);
  // /go 中转是站内相对地址，直接放行；外链还要过 safeHref
  const goPath = result.go_url && result.go_url.startsWith("/go?u=") ? result.go_url : null;
  const safeUrl = safeHref(result.url);
  const href = goPath ?? safeUrl;
  let host = "";
  try {
    host = new URL(result.url).hostname;
  } catch {
    host = "";
  }
  const flagged = result.risk >= RISK_FLAG;
  const explanation = result.reasons.join("；");
  const riskId = `card-risk-${result.id}`;
  const engines = result.engine.length > MAX_ENGINE_TAGS
    ? result.engine.slice(0, MAX_ENGINE_TAGS)
    : result.engine;
  const hiddenEngines = result.engine.length - engines.length;
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  const closeActions = () => {
    const menu = actions.current;
    if (!menu?.open) return;
    if (menu.contains(document.activeElement)) menu.querySelector("summary")?.focus({ preventScroll: true });
    menu.open = false;
  };

  useLayoutEffect(() => {
    const node = snippet.current;
    if (!node) return;
    const measure = () => {
      if (!node.clientWidth) return;
      const lineHeight = Number.parseFloat(getComputedStyle(node).lineHeight);
      setClipped(node.scrollHeight > Math.round(lineHeight * SNIPPET_LINES) + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [query, result.snippet]);

  useEffect(() => () => window.clearTimeout(actionTimer.current), []);

  const reportAction = (message: string) => {
    window.clearTimeout(actionTimer.current);
    setFeedback(message);
    actionTimer.current = window.setTimeout(() => setFeedback(""), 3000);
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(result.url);
      reportAction("已复制链接");
    } catch {
      reportAction("复制链接失败");
    }
    closeActions();
  };

  const share = async () => {
    try {
      await navigator.share?.({
        title: result.title,
        // 部分平台只取 text，标题和链接都放进分享文案
        text: `${result.title}\n${result.url}`,
        url: result.url,
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) reportAction("分享链接失败");
    }
    closeActions();
  };

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
      aria-describedby={flagged && explanation ? riskId : undefined}
      onMouseEnter={() => onSelectId?.(result.id)}
      onClick={() => onSelectId?.(result.id)}
      onFocus={() => onSelectId?.(result.id)}
    >
      <details className="card__actions" name="result-actions" ref={actions}
        onKeyDown={event => {
          if (event.key !== "Escape" || !event.currentTarget.open) return;
          event.preventDefault();
          event.stopPropagation();
          closeActions();
        }}>
        <summary aria-label={`更多操作：${result.title}`} title="更多操作">
          <i className="ws-icon ws-icon--more" aria-hidden="true" />
        </summary>
        <div className="card__actions-menu">
          <BookmarkButton result={result} bookmarkId={bookmarkId} onChange={onBookmarkChange} />
          {safeUrl ? <button type="button" onClick={() => void copyLink()}>复制链接</button> : null}
          {safeUrl && canShare ? <button type="button" onClick={() => void share()}>分享</button> : null}
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer" onClick={closeActions}>打开链接</a>
          ) : null}
        </div>
      </details>
      <span className="card__action-status" role="status">{feedback}</span>

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
        <span className="card__url" title={result.url}>{title}</span>
        <span className="card__tags">
          {engines.map((engine) => (
            <span className="card__tag" key={engine}>{engine}</span>
          ))}
          {hiddenEngines > 0 ? (
            <span className="card__tag card__tag--more" title={result.engine.join(" / ")}>+{hiddenEngines}</span>
          ) : null}
        </span>
        <span className="card__flags">
          {result.published ? <span className="card__tag">{result.published.slice(0, 10)}</span> : null}
          {flagged ? <span className="card__risk" title={explanation}>可疑 · {result.risk.toFixed(2)}</span> : null}
          {result.brand_warning ? <span className="card__risk" title={result.brand_warning}>品牌身份未核验</span> : null}
          {result.go_url ? <span className="card__tag" title="打开前会先确认">中转确认</span> : null}
        </span>
        {flagged && explanation ? <span className="sr-only" id={riskId}>{explanation}</span> : null}
      </div>
      <h3 className="card__title">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" title={explanation}>
            <Marked text={result.title} terms={terms} />
          </a>
        ) : (
          <span title={result.url}><Marked text={result.title} terms={terms} /></span>
        )}
      </h3>
      {result.snippet ? (
        <>
          <p ref={snippet} id={snippetId} className={expanded ? "card__snippet card__snippet--open" : "card__snippet"}>
            <Marked text={result.snippet} terms={terms} />
          </p>
          {clipped || expanded ? (
            <button type="button" className="card__snippet-toggle" aria-expanded={expanded}
              aria-controls={snippetId} onClick={() => setExpanded(value => !value)}>
              {expanded ? "收起摘要" : "展开摘要"}
            </button>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

// 卡片是长列表里最贵的节点，props 稳定时直接复用上次渲染
export default memo(ResultCard);
