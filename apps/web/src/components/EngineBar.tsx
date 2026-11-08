import { useState } from "react";
import type { EngineInfo } from "../types";

const PRIMARY = new Set(["g", "b", "d", "y", "gc", "w", "sc", "sg"]);

interface Props {
  engines: EngineInfo[];
  busy: boolean;
  canPick: boolean;
  onPick: (code: string) => void;
}

function statusText(engine: EngineInfo): string {
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

  const shown = expanded ? engines : engines.filter((engine) => PRIMARY.has(engine.code));
  const hiddenCount = engines.length - shown.length;

  return (
    <div className="engines" aria-label="搜索引擎后缀">
      <span className="engines__label">引擎后缀</span>
      {shown.map((engine) => {
        const disabled = busy || !canPick || engine.selectable === false;
        const title = [engine.label, engine.note, statusText(engine)].filter(Boolean).join("；");
        return (
          <button
            key={engine.code}
            className="chip engines__chip"
            type="button"
            title={title}
            disabled={disabled}
            onClick={() => onPick(engine.code)}
          >
            <span className={`engines__dot engines__dot--${engine.status}`} aria-hidden="true" />
            {engine.label}
            <span className="engines__code">{engine.code}</span>
          </button>
        );
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
    </div>
  );
}
