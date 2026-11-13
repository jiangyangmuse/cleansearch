import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, summarizePage } from "./api";
import type { PageSummary } from "./api";
import AppShell from "./components/AppShell";
import { safeHref } from "./url";

type Status = "idle" | "loading" | "ready" | "error";

/** 空态示例：都是公网可抓取的静态页，避免内网/回环被拒 */
const EXAMPLES = [
  { label: "Python 文档", url: "https://docs.python.org/3/tutorial/index.html" },
  { label: "W3C 无障碍规范", url: "https://www.w3.org/TR/WCAG22/" },
  { label: "维基百科", url: "https://zh.wikipedia.org/wiki/Python" },
];

export default function PageSummaryPage() {
  const [initial] = useState(() => new URLSearchParams(window.location.search).get("u") ?? "");
  const [url, setUrl] = useState(initial);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<PageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const run = useCallback(async (target: string) => {
    const value = target.trim();
    if (!value || request.current) return;
    if (!safeHref(value)) {
      setError("请输入有效的 HTTP(S) 网页地址");
      setStatus("error");
      return;
    }
    const current = new AbortController();
    request.current = current;
    setStatus("loading");
    setError(null);
    setData(null);
    window.history.replaceState(window.history.state, "", "/s?u=" + encodeURIComponent(value));
    try {
      const result = await summarizePage(value, current.signal);
      if (!current.signal.aborted) {
        setData(result);
        setStatus("ready");
      }
    } catch (caught) {
      if (!current.signal.aborted) {
        setError(caught instanceof ApiError ? caught.message : "总结失败，请确认本机服务已启动后重试");
        setStatus("error");
      }
    } finally {
      if (request.current === current) request.current = null;
    }
  }, []);

  // 带 ?u= 直接进页面时自动跑一次
  useEffect(() => {
    const start = window.setTimeout(() => { if (initial) void run(initial); }, 0);
    return () => {
      window.clearTimeout(start);
      request.current?.abort();
      request.current = null;
    };
  }, [initial, run]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(url);
  };

  return (
    <AppShell current="summary" title="单页总结 · CleanSearch" maxWidth={880}>
      <main id="main" tabIndex={-1} className="shell-main">
        <h1 className="shell-title">单页总结</h1>
        <form className="searchbar" onSubmit={submit}>
          <input
            className="searchbar__input"
            ref={input}
            type="url"
            required
            maxLength={2048}
            value={url}
            placeholder="粘贴要总结的网页地址（只抓公网 http/https）"
            onChange={(event) => setUrl(event.target.value)}
            aria-label="网页地址"
          />
          <button className="searchbar__button" type="submit" disabled={status === "loading"}>
            {status === "loading" ? "抓取中…" : "总结这一页"}
          </button>
        </form>

        <p className="state__hint" style={{ marginTop: 10 }}>
          抓取会拒绝内网与回环地址，单次最多 2MB、2.5 秒超时；正文提取失败时会明确提示。
        </p>

        {status === "idle" || status === "error" ? (
          <section className="state page-summary__examples" aria-label="示例地址">
            <h2>试试这几个页面</h2>
            <p>点一下会直接填入并开始总结，公网地址才抓得到。</p>
            <div className="state__actions">
              {EXAMPLES.map(({ label, url: sample }) => (
                <button key={sample} type="button" className="button button--ghost"
                  onClick={() => {
                    input.current?.focus({ preventScroll: true });
                    setUrl(sample);
                    void run(sample);
                  }}>
                  {label}
                </button>
              ))}
            </div>
            <p className="state__hint">也可以把浏览器地址栏里的链接直接粘到上面的输入框。</p>
          </section>
        ) : null}

        <div role="status" className={status === "loading" ? "state state--loading" : "sr-only"}>
          {status === "loading" && <>
            <span className="spinner" aria-hidden="true" />
            <p>正在抓取并提取正文…</p>
          </>}
          {status === "ready" && "单页总结已生成"}
        </div>

        {status === "error" && error ? (
          <div className="state state--error" role="alert">
            <h2>这一页总结不了</h2>
            <p>{error}</p>
            <p className="state__hint">可能是付费墙、反爬、纯图片页面，或地址指向了内网。</p>
          </div>
        ) : null}

        {status === "ready" && data ? (
          <article className="page-summary">
            <h2 className="page-summary__title">{data.title || data.url}</h2>
            <p className="page-summary__meta">
              {data.byline ? <span>{data.byline} · </span> : null}
              {data.published ? <span>{data.published.slice(0, 10)} · </span> : null}
              <span>{data.word_count} 字 · 约 {data.read_minutes} 分钟 · </span>
              <span>提取器 {data.extractor}</span>
              {data.truncated ? <span> · 已截断</span> : null}
            </p>
            <section className="page-summary__block">
              <h3>一句话结论</h3>
              <p>{data.summary.one_liner || "（材料不足，未生成结论）"}</p>
            </section>
            {data.summary.bullets.length > 0 ? (
              <section className="page-summary__block">
                <h3>要点</h3>
                <ul>
                  {data.summary.bullets.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {data.key_data.length > 0 ? (
              <section className="page-summary__block">
                <h3>关键数据</h3>
                <ul>
                  {data.key_data.map((item, index) => (
                    <li key={index}>
                      {item.label ? <span className="page-summary__label">{item.label}：</span> : null}
                      <strong>{item.value}</strong>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {data.summary.caveats.length > 0 ? (
              <section className="page-summary__block">
                <h3>分歧与不确定</h3>
                <ul>
                  {data.summary.caveats.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {data.anchors.length > 0 ? (
              <section className="page-summary__block">
                <h3>原文锚点</h3>
                <ol>
                  {data.anchors.map((anchor) => (
                    <li key={anchor.i} value={anchor.i}>
                      {anchor.text}
                      {anchor.text.length >= 80 ? "…" : ""}
                    </li>
                  ))}
                </ol>
                <p className="state__hint">按段落在原文里的序号标注，回原文时可按序号定位。</p>
              </section>
            ) : null}
            <p className="page-summary__foot">
              模型 {data.model} · <a href={data.final_url} target="_blank" rel="noopener noreferrer">打开原页面</a>
            </p>
          </article>
        ) : null}
      </main>

      <footer className="footer">CleanSearch · 单页总结只读原文，不写入书签或历史</footer>
    </AppShell>
  );
}
