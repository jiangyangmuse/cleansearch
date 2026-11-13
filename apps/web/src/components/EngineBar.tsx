import { useState } from "react";
import type { EngineInfo } from "../types";
import { ENGINE_SECTIONS, engineStatusLabel } from "../engineQuery";

const PRIMARY = new Set(["g", "b", "d", "y", "gc", "w", "sc", "sg"]);

interface Props {
  engines: EngineInfo[];
  busy: boolean;
  canPick: boolean;
  onPick: (code: string) => void;
}

function statusText(engine: EngineInfo): string {
  if (engine.kind === "website") return "显示可在新标签页打开的搜索链接";
  if (engine.kind === "region") return "使用此语言或地区的聚合搜索";
  if (engine.selectable === false) return "当前来源及回退来源均在冷却期，请稍后重试";
  if (engine.status === "cooldown") {
    const minutes = Math.max(1, Math.ceil(engine.remaining_seconds / 60));
    const fallback = engine.can_fallback ? "；可尝试回退来源" : "";
    return `主引擎冷却中，约 ${minutes} 分钟${fallback}；${engine.last_error ?? ""}`.trim();
  }
  if (engine.status === "ok") {
    const latency = engine.avg_ms ? `，平均 ${engine.avg_ms} ms` : "";
    return `最近成功${latency}`;
  }
  return "尚未验证；先输入查询词再点后缀";
}

export default function EngineBar({ engines, busy, canPick, onPick }: Props) {
  const [expanded, setExpanded] = useState(false);
  if (engines.length === 0) return null;

  const shown = expanded ? engines : engines.filter((engine) => engine.section || PRIMARY.has(engine.code));
  const hiddenCount = engines.length - shown.length;

  return (
    <div className="engines" aria-label="搜索引擎后缀">
      {ENGINE_SECTIONS.map(({ section, title }) => {
        const items = shown.filter(engine => (engine.section ?? null) === section);
        if (!items.length) return null;
        return <div className="engines__section" key={section ?? "unclassified"} aria-label={title ?? undefined}>
          {title && <strong className="engines__heading">{title}</strong>}
          {items.map((engine) => {
            const disabled = busy || !canPick || engine.selectable === false;
            const hint = [engine.label, engine.note, statusText(engine)].filter(Boolean).join("；");
            const status = engineStatusLabel(engine);
            return (
              <button key={engine.code} className={`engines__chip engines__chip--${status.tone}`} type="button"
                title={hint} disabled={disabled} onClick={() => onPick(engine.code)}>
                {engine.label}<span className="engines__code">{engine.code}</span>
                <span className="engines__status">{status.text}</span>
              </button>
            );
          })}
        </div>;
      })}
      {expanded || hiddenCount > 0 ? (
        <button
          className="chip engines__more"
          type="button"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "收起" : `更多 ${hiddenCount}`}
        </button>
      ) : null}
      <a className="engines__manage" href="/settings#engine-settings">管理引擎</a>
    </div>
  );
}
