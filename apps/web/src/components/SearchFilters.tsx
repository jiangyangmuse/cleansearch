import { useEffect, useId, useImperativeHandle, useRef, useState, type Ref } from "react";
import { normalizeSite, type SearchUrlState } from "../urlState";
/** 筛选条：时间范围 / 语言 / 站点限定 / 去重强度；状态由 URL 驱动，可分享。 */
export interface Filters {
  timeRange: "" | "day" | "week" | "month" | "year";
  language: string;
  site: string;
  dedupe: "off" | "normal" | "strict";
}

export const DEFAULT_FILTERS: Filters = { timeRange: "", language: "", site: "", dedupe: "normal" };

export function filtersFromUrl({ range, lang, site, dedupe }: SearchUrlState): Filters {
  return { timeRange: range, language: lang, site, dedupe };
}

export function sameFilters(left: Filters, right: Filters): boolean {
  return left.timeRange === right.timeRange && left.language === right.language && left.site === right.site && left.dedupe === right.dedupe;
}

const RANGES: { value: Filters["timeRange"]; label: string }[] = [
  { value: "", label: "全部时间" },
  { value: "day", label: "一天内" },
  { value: "week", label: "一周内" },
  { value: "month", label: "一月内" },
  { value: "year", label: "一年内" },
];

const LANGUAGES: { value: string; label: string }[] = [
  { value: "", label: "不限语言" },
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "ja", label: "日文" },
  { value: "ko", label: "韩文" },
  { value: "fr", label: "法文" },
  { value: "de", label: "德文" },
  { value: "es", label: "西班牙文" },
];

const DEDUPE: { value: Filters["dedupe"]; label: string }[] = [
  { value: "normal", label: "标准（同网址合并）" },
  { value: "strict", label: "严格（同名也合并）" },
  { value: "off", label: "关闭（全部保留）" },
];

export function activeFilterCount(filters: Filters): number {
  return [filters.timeRange, filters.language, filters.site, filters.dedupe !== "normal" ? "1" : ""]
    .filter(Boolean).length;
}

export function describeFilters(filters: Filters): string {
  const parts: string[] = [];
  const range = RANGES.find(item => item.value === filters.timeRange);
  if (filters.timeRange && range) parts.push(range.label);
  const language = LANGUAGES.find(item => item.value === filters.language);
  if (filters.language) parts.push(language?.label ?? filters.language);
  if (filters.site) parts.push(`site:${filters.site}`);
  if (filters.dedupe === "strict") parts.push("严格去重");
  if (filters.dedupe === "off") parts.push("关闭去重");
  return parts.join(" · ");
}

interface Props {
  filters: Filters;
  onChange: (next: Filters) => void;
  ref?: Ref<FilterPanel>;
}

export type FilterPanel = { close: () => void; isOpen: () => boolean };

export default function SearchFilters({ filters, onChange, ref }: Props) {
  const count = activeFilterCount(filters);
  const update = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const [siteDraft, setSiteDraft] = useState(filters.site);
  const [siteError, setSiteError] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const supported = typeof HTMLElement.prototype.showPopover === "function";
  const [fallbackOpen, setFallbackOpen] = useState(false);

  useEffect(() => { setSiteDraft(filters.site); setSiteError(false); }, [filters.site]);

  useImperativeHandle(ref, () => ({
    close: () => {
      if (supported) panel.current?.hidePopover();
      else setFallbackOpen(false);
      setSiteDraft(filters.site);
      setSiteError(false);
    },
    isOpen: () => supported ? Boolean(panel.current?.matches(":popover-open")) : fallbackOpen,
  }), [supported, fallbackOpen, filters.site]);

  useEffect(() => {
    if (!fallbackOpen) return;
    const close = () => { setFallbackOpen(false); setSiteDraft(filters.site); setSiteError(false); };
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !trigger.current?.contains(target)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      close();
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [fallbackOpen, filters.site]);

  return (
    <div className="filters">
      <button type="button" className="filters__toggle" ref={trigger} popoverTarget={supported ? id : undefined}
        aria-controls={id} aria-expanded={supported ? undefined : fallbackOpen}
        onClick={supported ? undefined : () => setFallbackOpen(open => !open)}>筛选
        {count > 0 ? <span className="filters__badge" aria-label={`${count} 个筛选条件`}>{count}</span> : null}
        <i className="ws-icon ws-icon--chevron" aria-hidden="true" />
      </button>
      <div id={id} ref={panel} className="filters__body" popover={supported ? "auto" : undefined}
        hidden={!supported && !fallbackOpen} onToggle={event => {
          if (!event.currentTarget.matches(":popover-open")) {
            setSiteDraft(filters.site);
            setSiteError(false);
          }
        }}>
        <fieldset className="filters__group">
          <legend>时间范围</legend>
          <div className="filters__chips">
            {RANGES.map(({ value, label }) => (
              <button key={label} type="button" className={filters.timeRange === value ? "chip chip--active" : "chip"}
                aria-pressed={filters.timeRange === value}
                onClick={() => update({ timeRange: value })}>{label}</button>
            ))}
          </div>
        </fieldset>
        <label className="filters__field">语言
          <select value={filters.language}
            onChange={(event) => update({ language: event.target.value })}>
            {LANGUAGES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            {filters.language && !LANGUAGES.some(option => option.value === filters.language) &&
              <option value={filters.language}>{filters.language}</option>}
          </select>
        </label>
        <form className="filters__site" onSubmit={event => {
          event.preventDefault();
          const site = normalizeSite(siteDraft);
          setSiteError(site === null);
          if (site !== null) { setSiteDraft(site); update({ site }); }
        }}>
          <label className="filters__field">站点限定
            <input value={siteDraft} placeholder="example.com" inputMode="url" maxLength={253}
              aria-invalid={siteError || undefined} aria-describedby={siteError ? `${id}-error` : undefined}
              onChange={event => { setSiteDraft(event.target.value); setSiteError(false); }} />
          </label>
          <button type="submit" className="chip">应用站点</button>
          {siteError && <span id={`${id}-error`} role="alert">请输入域名，例如 example.com</span>}
        </form>
        <label className="filters__field">去重
          <select value={filters.dedupe}
            onChange={(event) => update({ dedupe: event.target.value as Filters["dedupe"] })}>
            {DEDUPE.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <div className="filters__actions">
          <button type="button" className="button button--ghost" disabled={count === 0 && !siteDraft}
            onClick={() => { setSiteDraft(""); setSiteError(false); onChange(DEFAULT_FILTERS); }}>重置筛选</button>
          <span className="filters__hint">筛选会写进地址栏，可分享；站点限定只接受域名。</span>
        </div>
      </div>
    </div>
  );
}
