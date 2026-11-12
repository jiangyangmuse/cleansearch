import { useEffect, useRef, useState } from "react";
import { summarizePages, type BatchSummary } from "../api";
import { safeHref } from "../url";

export default function PageBatchSummary() {
  const [input, setInput] = useState("");
  const [data, setData] = useState<BatchSummary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  const submit = async () => {
    const urls = [...new Set(input.trim().split(/\s+/))];
    setData(null);
    if (urls.length > 5 || urls.some(url => !safeHref(url))) {
      setError("请填写 1–5 个有效的 HTTP(S) 网页链接，每行一个");
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setError("");
    setBusy(true);
    try {
      setData(await summarizePages(urls, controller.signal));
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "网页总结失败");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  const succeeded = data?.pages.filter(page => !page.error) ?? [];
  const failed = data?.pages.filter(page => page.error) ?? [];
  return (
    <section className="workspace-task" aria-label="网页总结">
      <h2>网页总结</h2>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label>网页链接
          <textarea value={input} rows={3} maxLength={10244} disabled={busy} required
            placeholder="每行一个网址，最多 5 个" onChange={event => setInput(event.target.value)} />
        </label>
        <button className="button" type="submit" disabled={busy || !input.trim()}>
          {busy ? "正在抓取并总结…" : "抓取并总结"}
        </button>
      </form>
      {error && <p className="workspace-form-error" role="alert">{error}</p>}
      {data && (
        <div className="workspace-task__output" aria-live="polite">
          {data.model && <p className="workspace-task__model">{data.model}</p>}
          {data.summary ? <p className="workspace-task__text">{data.summary}</p> : <p>没有成功获取正文的网页。</p>}
          {succeeded.length > 0 && (
            <ol className="workspace-task__sources">
              {succeeded.map(page => {
                const href = safeHref(page.final_url ?? page.url);
                return <li key={page.url}>
                  {href ? <a href={href} target="_blank" rel="noopener noreferrer">{page.title || href}</a> : page.title}
                  {page.truncated && <small> · 正文节选</small>}
                </li>;
              })}
            </ol>
          )}
          {failed.length > 0 && (
            <ul className="workspace-task__failures">
              {failed.map(page => <li key={page.url}><strong>{page.url}</strong><br />{page.error}</li>)}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
