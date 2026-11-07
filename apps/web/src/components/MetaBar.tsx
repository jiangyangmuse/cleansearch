import type { ParsedQuery, SearchMeta } from "../types";

const ROUTER_LABEL: Record<ParsedQuery["router"], string> = {
  suffix: "后缀路由",
  bang: "bang",
  default: "默认聚合",
};

export default function MetaBar({ meta, parsed }: { meta: SearchMeta; parsed: ParsedQuery }) {
  const providerLabel = meta.provider === "fixture" ? "固定样本" : "SearXNG";
  const routed = parsed.router !== "default";
  return (
    <div className="metabar">
      <span className={`badge badge--${meta.provider}`}>{providerLabel}</span>
      {meta.cached ? <span className="badge badge--cached" title="命中本地缓存">缓存</span> : null}
      <span>
        展示 {meta.total} 条
        {meta.upstream_total !== meta.total ? <span className="metabar__muted"> / 上游 {meta.upstream_total}</span> : null}
      </span>
      {meta.filtered.dup > 0 ? <span>去重 {meta.filtered.dup}</span> : null}
      {meta.filtered.risk > 0 ? <span className="metabar__warn">拦截 {meta.filtered.risk}</span> : null}
      <span>{meta.ms} ms</span>
      {routed ? (
        <span className="metabar__route">
          {ROUTER_LABEL[parsed.router]}
          {parsed.engine !== "default" ? ` · ${parsed.engine}` : ""}
          {parsed.region ? ` · 地区 ${parsed.region}` : ""}
        </span>
      ) : null}
      {meta.engines.length > 0 ? <span className="metabar__muted">引擎 {meta.engines.join(" / ")}</span> : null}
      {meta.unresponsive.length > 0 ? (
        <span className="metabar__warn">不可用引擎 {meta.unresponsive.join(" / ")}</span>
      ) : null}
      <span className="metabar__sid">sid {meta.sid}</span>
    </div>
  );
}