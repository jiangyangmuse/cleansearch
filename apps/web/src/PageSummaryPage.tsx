import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, summarizePage } from "./api";
import type { PageSummary } from "./api";
import ThemeToggle from "./components/ThemeToggle";

type Status = "idle" | "loading" | "ready" | "error";

export default function PageSummaryPage() {
  const initial = new URLSearchParams(window.location.search).get("u") ?? "";
  const [url, setUrl] = useState(initial);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<PageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (target: string) => {
    const value = target.trim();
    if (!value) return;
    setStatus("loading");
    setError(null);
    setData(null);
    window.history.replaceState(null, "", "/s?u=" + encodeURIComponent(value));
    try {
      setData(await summarizePage(value));
      setStatus("ready");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "总结失败");
      setStatus("error");
    }
  };

  // 带 ?u= 直接进页面时自动跑一次
  useEffect(() => {
    const initialUrl = new URLSearchParams(window.location.search).get("u");
    if (initialUrl) void run(initialUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(url);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">CleanSearch</span>
          <span className="brand__tag">M4 · 单页总结</span>
        </div>
        <span className="header__links">
          <ThemeToggle />
          <a className="header__link header__link--active" href="/">返回搜索</a>
        </span>
      </header>

      <main className="main">
        <form className="searchbar" onSubmit={submit}>
          <input
            className="searchbar__input"
            type="url"
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

        {status === "loading" ? (
          <div className="state state--loading" role="status">
            <span className="spinner" aria-hidden="true" />
            <p>正在抓取并提取正文…</p>
          </div>
        ) : null}

        {status === "error" && error ? (
          <div className="state state--error" role="alert">
            <h2>这一页总结不了</h2>
            <p>{error}</p>
            <p className="state__hint">可能是付费墙、反爬、纯图片页面，或地址指向了内网。</p>
          </div>
        ) : null}

        {status === "ready" && data ? (
          <article className="page-summary">
            <h1 className="page-summary__title">{data.title || data.url}</h1>
            <p className="page-summary__meta">
              {data.byline ? <span>{data.byline} · </span> : null}
              {data.published ? <span>{data.published.slice(0, 10)} · </span> : null}
              <span>{data.word_count} 字 · 约 {data.read_minutes} 分钟 · </span>
              <span>提取器 {data.extractor}</span>
              {data.truncated ? <span> · 已截断</span> : null}
            </p>
            <section className="page-summary__block">
              <h2>一句话结论</h2>
              <p>{data.summary.one_liner || "（材料不足，未生成结论）"}</p>
            </section>
            {data.summary.bullets.length > 0 ? (
              <section className="page-summary__block">
                <h2>要点</h2>
                <ul>
                  {data.summary.bullets.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {data.key_data.length > 0 ? (
              <section className="page-summary__block">
                <h2>关键数据</h2>
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
                <h2>分歧与不确定</h2>
                <ul>
                  {data.summary.caveats.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {data.anchors.length > 0 ? (
              <section className="page-summary__block">
                <h2>原文锚点</h2>
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
    </div>
  );
}