import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, streamSummary } from "../api";
import type { Citation, SummaryDone, SummaryMeta } from "../api";

type Status = "idle" | "streaming" | "done" | "error";

interface Props {
  sid: string | null;
  query: string;
  revealResult?: (id: string) => void;
}

const FLASH_MS = 1500;

export default function SummaryPanel({ sid, query, revealResult }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [text, setText] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [meta, setMeta] = useState<SummaryMeta | null>(null);
  const [doneInfo, setDoneInfo] = useState<SummaryDone | null>(null);
  const [mode, setMode] = useState<"fast" | "full">("fast");
  const [error, setError] = useState<{ code: string; message: string; retryable: boolean } | null>(null);

  const controller = useRef<AbortController | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // 组件卸载（切查询 / 重排）时中止旧流，避免把上一轮的文本接到新查询上
  useEffect(() => {
    return () => {
      controller.current?.abort();
    };
  }, []);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [text]);

  const run = useCallback(async (nextMode: "fast" | "full" = "fast") => {
    if (!sid) return;
    setMode(nextMode);
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;

    setStatus("streaming");
    setText("");
    setCitations([]);
    setError(null);
    setDoneInfo(null);
    setMeta(null);

    try {
      await streamSummary(
        sid,
        {
          onMeta: setMeta,
          onCite: (cite) => setCitations((list) => [...list, cite]),
          onToken: (chunk) => setText((prev) => prev + chunk),
          onDone: (info) => {
            setDoneInfo(info);
            setStatus("done");
          },
          onError: (err) => {
            setError(err);
            setStatus("error");
          },
        },
        current.signal,
        nextMode,
      );
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (current.signal.aborted) return;
      setError(
        caught instanceof ApiError
          ? { code: caught.code, message: caught.message, retryable: caught.retryable }
          : { code: "UNKNOWN", message: "总结失败，查看控制台", retryable: true },
      );
      setStatus("error");
    }
  }, [sid]);

  const stop = () => {
    controller.current?.abort();
    setStatus("idle");
    setText("");
    setCitations([]);
    setDoneInfo(null);
  };

  // 快捷键 s：由 App 派发，侧栏自己决定按当前模式跑
  useEffect(() => {
    const handler = () => {
      if (status !== "streaming") void run(mode);
    };
    window.addEventListener("cs:summarize", handler);
    return () => window.removeEventListener("cs:summarize", handler);
  }, [run, mode, status]);

  const citationById = new Map(citations.map((cite) => [cite.i, cite]));

  const seek = (resultId: string) => {
    revealResult?.(resultId);
    const target = document.getElementById(`result-${resultId}`);
    if (!target) return;
    const group = target.closest("details");
    if (group) group.open = true;
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("card--flash");
    window.setTimeout(() => target.classList.remove("card--flash"), FLASH_MS);
  };

  const renderBody = () => {
    if (status === "idle" && !text) {
      return (
        <p className="summary__hint">
          用本次通过过滤的 {sid ? "结果摘要" : "结果"}生成一段带引用的总结。点击正文里的 [n] 会跳到对应结果卡片。
        </p>
      );
    }
    const parts = text.split(/(\[\d+\])/g);
    return (
      <div className="summary__text">
        {parts.map((part, index) => {
          const match = part.match(/^\[(\d+)\]$/);
          if (!match) return <span key={index}>{part}</span>;
          const number = Number(match[1]);
          const cite = citationById.get(number);
          if (!cite) return <span key={index}>{part}</span>;
          const material = cite.material === "full" ? "正文节选" : cite.material === "truncated" ? "截断正文" : "搜索摘要";
          return (
            <button
              key={index}
              type="button"
              className="citation"
              title={`${cite.title} · ${material}`}
              onClick={() => seek(cite.result_id)}
            >
              {part}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <section className="summary" aria-label="AI 总结">
      <header className="summary__head">
        <h2 className="summary__title">AI 总结</h2>
        <div className="summary__actions">
          {status === "streaming" ? (
            <button className="button button--ghost" type="button" onClick={stop}>
              停止
            </button>
          ) : null}
          <button
            className="button"
            type="button"
            onClick={() => void run(mode === "full" ? "full" : "fast")}
            disabled={!sid || status === "streaming"}
          >
            {(doneInfo || error) && status !== "streaming" ? "重新生成" : "生成总结"}
          </button>
          {doneInfo && status === "done" && mode === "fast" ? (
            <button className="button button--ghost" type="button" onClick={() => void run("full")}>
              增强（抓正文）
            </button>
          ) : null}
        </div>
      </header>

      <div className="summary__body" ref={bodyRef}>
        {renderBody()}
        {status === "streaming" ? <span className="summary__cursor" aria-hidden="true" /> : null}
        {status === "error" && error ? (
          <div className="summary__error" role="alert">
            <strong>{error.code === "LLM_TIMEOUT" ? "生成超时" : "生成失败"}</strong>
            <p>{error.message}</p>
            {error.retryable ? (
              <button className="button button--ghost" type="button" onClick={() => void run()}>
                重试
              </button>
            ) : null}
            <p className="summary__hint">结果列表不受影响，可以继续点开链接或换个查询。</p>
          </div>
        ) : null}
      </div>

      <footer className="summary__foot">
        <span>{meta ? `模型 ${meta.model}` : "未生成"}</span>
        {meta ? <span>来源 {meta.sources}</span> : null}
        {doneInfo ? <span>{doneInfo.tokens} 段 / {doneInfo.ms} ms</span> : null}
        {meta ? <span>{meta.mode === "full" ? "正文增强" : "摘要模式"}</span> : null}
        {meta && meta.mode === "full" ? (
          <span className={meta.degraded ? "metabar__warn" : undefined}>
            抓取 {meta.fetched}
            {meta.failed ? ` / 降级 ${meta.failed}` : ""}
            {meta.truncated ? ` / 截断 ${meta.truncated}` : ""}
          </span>
        ) : null}
        {status === "streaming" ? <span className="summary__live">生成中…</span> : null}
        {sid ? <span className="summary__sid" title={query}>sid {sid}</span> : null}
      </footer>
    </section>
  );
}
