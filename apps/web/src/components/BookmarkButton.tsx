import { useLayoutEffect, useRef, useState } from "react";
import { ApiError, bookmarkStatus, removeResultBookmark, saveBookmark } from "../api";
import type { Result } from "../types";

interface Props {
  result: Pick<Result, "url" | "title">;
  /** 批量状态接口给出的已收藏 id；有值就直接显示「已在书签」 */
  bookmarkId?: number;
  /** 收藏/撤销后回传最新 id，便于列表内其它地方复用 */
  onChange?: (url: string, id: number | null) => void;
}

/** 官方入口与普通结果共用收藏状态：初始来自批量状态，保存先乐观更新，失败回滚。 */
export default function BookmarkButton({ result, bookmarkId, onChange }: Props) {
  const [localId, setLocalId] = useState<number>();
  const [operation, setOperation] = useState<"save" | "undo" | null>(null);
  const pending = useRef(false);
  const saveButton = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  const [error, setError] = useState("");
  const [newId, setNewId] = useState<number>();
  const id = onChange ? bookmarkId : localId;

  useLayoutEffect(() => {
    if (!restoreFocus.current || operation) return;
    restoreFocus.current = false;
    if (!id && document.activeElement === document.body) saveButton.current?.focus();
  }, [id, operation]);

  const update = (id: number | null) => {
    if (onChange) onChange(result.url, id);
    else setLocalId(id ?? undefined);
  };

  const save = async () => {
    if (pending.current || id) return;
    pending.current = true;
    setOperation("save");
    setError("");
    try {
      const response = await saveBookmark({ url: result.url, title: result.title });
      const nextId = response.item?.id ?? (await bookmarkStatus([result.url]))[result.url];
      if (!nextId) throw new Error("缺少书签编号");
      update(nextId);
      setNewId(response.deduplicated ? undefined : nextId);
    } catch {
      setError("收藏失败，请重试");
    } finally {
      pending.current = false;
      setOperation(null);
    }
  };

  const undo = async (button: HTMLButtonElement) => {
    if (pending.current || !id) return;
    pending.current = true;
    setOperation("undo");
    setError("");
    try {
      try {
        await removeResultBookmark(id, result.url);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
      }
      restoreFocus.current = document.activeElement === button;
      update(null);
      setNewId(undefined);
    } catch {
      setError("撤销收藏失败，请重试");
    } finally {
      pending.current = false;
      setOperation(null);
    }
  };

  const saved = Boolean(id) || operation === "save";
  const state = operation === "save" ? "saved" : id ? (id === newId ? "saved" : "exists") : "idle";
  const label = state === "saved" ? "已收藏" : state === "exists" ? "已在书签" : "收藏";

  return (
    <>
      <button ref={saveButton} className={`card__save card__save--${state}`} type="button"
        onClick={() => void save()} disabled={saved || operation !== null}
        title={saved ? "已收藏到本机书签" : "收藏到本机书签"}
        aria-pressed={saved}>
        {label}
      </button>
      {id && operation !== "save" ? (
        <button className="card__undo" type="button" aria-disabled={operation === "undo"}
          onClick={event => void undo(event.currentTarget)} title="从本机书签移除">
          {operation === "undo" ? "正在撤销…" : "撤销收藏"}
        </button>
      ) : null}
      <span className="card__bookmark-status" role="status">{error}</span>
    </>
  );
}
