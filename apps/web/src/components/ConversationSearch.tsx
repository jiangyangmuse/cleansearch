import { useEffect, useRef, useState } from "react";
import { ApiError, searchConversation, type ConversationReply } from "../api";
import ResultList from "./ResultList";

type Turn = { id: number; message: string; reply?: ConversationReply; error?: ApiError };

export function ConversationForm({ compact = false, busy, onSubmit }: {
  compact?: boolean; busy: boolean; onSubmit: (message: string) => void;
}) {
  const [input, setInput] = useState("");
  return (
    <form className="conversation-form" onSubmit={event => {
      event.preventDefault();
      const message = input.trim();
      if (!message || busy) return;
      onSubmit(message);
      setInput("");
    }}>
      <label>{compact ? "想找什么网页？" : "搜索需求"}
        <textarea name={compact ? "conversation-quick" : "conversation"} value={input}
          placeholder={compact ? "描述你想找的内容" : "例如：想自学 Python，找官方教程和中文视频"}
          maxLength={1500} rows={compact ? 3 : 2} required onChange={event => setInput(event.target.value)} />
      </label>
      <button className="button" type="submit" disabled={busy || !input.trim()}>
        {busy ? "搜索中…" : "对话搜索"}
      </button>
    </form>
  );
}

export function useConversationSearch() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  useEffect(() => () => request.current?.abort(), []);

  const send = async (message: string, retryId?: number) => {
    if (request.current) return;
    const current = new AbortController();
    request.current = current;
    const id = retryId ?? ++nextId.current;
    const previous = turns.filter(turn => turn.id < id);
    setTurns([...previous, { id, message }]);
    setBusy(true);
    try {
      const history = previous.slice(-6).map(turn => ({
        message: turn.message, directions: turn.reply?.groups.map(group => group.label) ?? [],
      }));
      const reply = await searchConversation(message, history, current.signal);
      if (!current.signal.aborted) {
        setTurns([...previous, { id, message, reply: {
          ...reply, groups: reply.groups.map(group => ({ ...group, results: group.results.map(item => ({
            ...item, id: `${id}_${item.id}`,
          })) })),
        } }]);
      }
    } catch (error) {
      if (!current.signal.aborted) setTurns([...previous, {
        id, message, error: error instanceof ApiError ? error : new ApiError("无法连接本机搜索服务", "NETWORK_ERROR", 0),
      }]);
    } finally {
      if (request.current === current) {
        request.current = null;
        setBusy(false);
      }
    }
  };

  const reset = () => {
    request.current?.abort();
    request.current = null;
    setBusy(false);
    setTurns([]);
  };
  return { turns, busy, send, reset };
}

export default function ConversationSearch({ conversation, selectedId, onSelect }: {
  conversation: ReturnType<typeof useConversationSearch>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { turns, busy, send, reset } = conversation;
  const latest = useRef<HTMLElement>(null);
  const [session, setSession] = useState(0);
  const lastId = turns.at(-1)?.id;
  useEffect(() => {
    latest.current?.scrollIntoView({ block: "start" });
  }, [lastId]);

  return (
    <div className="conversation-view">
      <header className="conversation-view__header">
        <h1>AI 对话搜索</h1>
        {turns.length > 0 && (
          <button className="button button--ghost" type="button" onClick={() => { reset(); setSession(id => id + 1); }}>
            新对话
          </button>
        )}
      </header>
      {!turns.length && <p className="conversation-view__hint">说说你想找什么。可以同时找教程、视频或其他资料，也可以继续追问。</p>}
      {turns.map((turn, index) => {
        const last = index === turns.length - 1;
        return (
          <section className="conversation-turn" key={turn.id} ref={last ? latest : undefined}
            aria-label={`第 ${index + 1} 轮搜索`}>
            <p className="conversation-turn__message">{turn.message}</p>
            {turn.reply && (
              <div className="conversation-turn__reply">
                <p className="conversation-turn__model">{turn.reply.model}</p>
                {turn.reply.groups.map(group => (
                  <section className="conversation-direction" key={group.query} aria-label={group.label}>
                    <h2>{group.label}</h2>
                    <p>搜索词 <span>{group.query}</span></p>
                    {group.error ? <p role="status">{group.error}</p> : group.results.length ? (
                      <ResultList title="网页" results={group.results} selectedId={selectedId} onSelect={onSelect} />
                    ) : <p>这个方向没有找到更多网页。</p>}
                  </section>
                ))}
              </div>
            )}
            {last && busy && <p className="conversation-turn__status" role="status">正在分析需求并查找网页…</p>}
            {turn.error && (
              <div className="conversation-turn__status" role="alert">
                <p>{turn.error.message}</p>
                {last && turn.error.retryable && (
                  <button className="chip" type="button" onClick={() => void send(turn.message, turn.id)}>重试</button>
                )}
              </div>
            )}
          </section>
        );
      })}
      <ConversationForm key={session} busy={busy} onSubmit={message => void send(message)} />
    </div>
  );
}
