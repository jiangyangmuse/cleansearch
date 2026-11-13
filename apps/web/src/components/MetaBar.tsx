import type { ParsedQuery, SearchMeta } from "../types";

const ROUTER_LABEL: Record<ParsedQuery["router"], string> = {
  suffix: "后缀路由",
  bang: "bang",
  default: "默认聚合",
};

/** 统计条：默认一行 `N 条 · 缓存 · ms`，其余进「检索详情」收起。 */
export default function MetaBar({ meta, parsed }: { meta: SearchMeta; parsed: ParsedQuery }) {
  const providerLabel = meta.provider === "fixture" ? "固定样本" : "SearXNG";
  const displayed = meta.total + (meta.official ?? 0);
  const route = [
    ROUTER_LABEL[parsed.router],
    parsed.engine !== "default" ? parsed.engine : null,
    parsed.region ? `地区 ${parsed.region}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className="metabar">
      <p className="metabar__summary">
        <span>展示 {displayed} 条</span>
        {meta.cached ? <span className="badge badge--cached" title="命中本地缓存">缓存</span> : null}
        <span>{meta.ms} ms</span>
      </p>
      <details className="metabar__more">
        <summary>检索详情 <i className="ws-icon ws-icon--chevron" aria-hidden="true" /></summary>
        <dl className="metabar__details">
          <div><dt>来源</dt><dd>{providerLabel}</dd></div>
          <div><dt>上游</dt><dd>{meta.upstream_total} 条</dd></div>
          <div><dt>去重</dt><dd>{meta.filtered.dup} 条</dd></div>
          <div><dt>拦截</dt><dd>{meta.filtered.risk} 条</dd></div>
          <div><dt>官方入口</dt><dd>{meta.official} 条{meta.directory > 0 ? `（目录直达 ${meta.directory}）` : ""}</dd></div>
          <div><dt>路由</dt><dd>{route}</dd></div>
          <div><dt>引擎</dt><dd>{meta.engines.length ? meta.engines.join(" / ") : "（未上报）"}</dd></div>
          {meta.unresponsive.length > 0 ? (
            <div><dt>不可用</dt><dd className="metabar__warn">{meta.unresponsive.join(" / ")}</dd></div>
          ) : null}
          <div><dt>会话</dt><dd className="metabar__sid">sid {meta.sid}</dd></div>
        </dl>
      </details>
    </div>
  );
}
