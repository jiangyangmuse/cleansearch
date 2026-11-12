import { useEffect, useRef, useState } from "react";
import { translateText } from "../api";

const LANGUAGES = [
  ["zh", "简体中文"], ["en", "英语"], ["ja", "日语"], ["ko", "韩语"],
  ["fr", "法语"], ["de", "德语"], ["es", "西班牙语"], ["ru", "俄语"],
];

export default function TranslationPanel({ onSearch }: { onSearch: (text: string) => boolean }) {
  const [input, setInput] = useState("");
  const [target, setTarget] = useState("zh");
  const [result, setResult] = useState<{ text: string; model: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  const submit = async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setResult(null);
    setError("");
    setNotice("");
    try {
      setResult(await translateText(input.trim(), target, controller.signal));
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "翻译失败");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return (
    <section className="workspace-task" aria-label="翻译">
      <h2>翻译</h2>
      <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <label>原文
          <textarea value={input} rows={4} maxLength={8000} required disabled={busy}
            placeholder="输入要翻译的文段" onChange={event => { setInput(event.target.value); setResult(null); }} />
        </label>
        <label>目标语言
          <select value={target} disabled={busy} onChange={event => { setTarget(event.target.value); setResult(null); }}>
            {LANGUAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <button className="button" type="submit" disabled={busy || !input.trim()}>{busy ? "翻译中…" : "翻译"}</button>
      </form>
      {error && <p className="workspace-form-error" role="alert">{error}</p>}
      {result && (
        <div className="workspace-task__output" aria-live="polite">
          <p className="workspace-task__model">{result.model}</p>
          <p className="workspace-task__text">{result.text}</p>
          <button className="button button--ghost" type="button" onClick={() => {
            setNotice(onSearch(result.text) ? "" : "译文超过 512 字，已填入前 512 字。可编辑后搜索。");
          }}>搜索</button>
          {notice && <p role="status">{notice}</p>}
        </div>
      )}
    </section>
  );
}
