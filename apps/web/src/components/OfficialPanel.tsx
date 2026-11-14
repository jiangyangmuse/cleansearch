import { useId } from "react";
import type { OfficialSection } from "../types";
import { safeHref } from "../url";
import BookmarkButton from "./BookmarkButton";

/**
 * 独立官方入口区：区分上游结果与目录直达。
 * 身份来自入口表（主机 + 路径 + 核验来源），不是标题或模型猜测。
 */
interface Props {
  section: OfficialSection | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  saved?: Record<string, number>;
  onBookmarkChange?: (url: string, id: number | null) => void;
  compact?: boolean;
  expanded?: boolean;
  onExpandedChange?: (open: boolean) => void;
}

export default function OfficialPanel({
  section, selectedId, onSelect, saved, onBookmarkChange, compact = false, expanded = false, onExpandedChange,
}: Props) {
  const listId = useId();
  if (!section || section.entries.length === 0) return null;
  const verified = section.entries[0]?.verified;
  const canExpand = compact && section.entries.length > 2;
  const visible = canExpand && !expanded ? section.entries.slice(0, 2) : section.entries;

  return (
    <section className="official" aria-label={`${section.brand} 官方入口`}>
      <div className="official__head">
        <h2 className="official__title">官方入口 · {section.brand}</h2>
        <span className="official__badge">入口表核验{verified ? ` · ${verified}` : ""}</span>
      </div>
      <ul className="official__list" id={listId}>
        {visible.map((entry) => {
          const href = entry.go_url?.startsWith("/go?u=") ? entry.go_url : safeHref(entry.url);
          const hint = `核验来源 ${entry.source || entry.host}（${entry.verified || "未标注"}）`;
          return (
            <li className={`official__item${selectedId === entry.id ? " card--selected" : ""}`}
              key={`${entry.role}-${entry.url}`} id={`result-${entry.id}`} data-result-id={entry.id}
              tabIndex={-1} onMouseEnter={() => onSelect?.(entry.id)}
              onClick={() => onSelect?.(entry.id)} onFocus={() => onSelect?.(entry.id)}>
              {href ? (
                <a
                  className="official__link"
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={hint}
                >
                  <span className="official__role">{entry.label}</span>
                  <span className="official__name">{entry.title}</span>
                  <span className="official__host">{entry.host} · {entry.origin === "directory" ? "目录直达" : "搜索结果"}</span>
                  {entry.risk >= 0.35 ? <span className="card__risk" title={entry.reasons.join("；")}>可疑 · 打开前确认</span> : null}
                </a>
              ) : (
                <span className="official__name">{entry.title}</span>
              )}
              <BookmarkButton result={entry} bookmarkId={saved?.[entry.url]}
                onChange={onBookmarkChange} />
            </li>
          );
        })}
      </ul>
      {canExpand ? (
        <button type="button" className="chip official__more" aria-expanded={expanded} aria-controls={listId}
          onClick={() => onExpandedChange?.(!expanded)}>
          {expanded ? "收起" : `查看全部 ${section.entries.length} 条`}
        </button>
      ) : null}
      <p className="official__note">
        目录直达来自已核验入口表，不计作搜索结果或总结材料；核验日期不代表当前可访问性。
      </p>
    </section>
  );
}
