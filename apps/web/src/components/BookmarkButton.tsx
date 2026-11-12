import { useState } from "react";
import { ApiError, saveBookmark } from "../api";
import type { Result } from "../types";

/** 官方入口与普通结果共用收藏状态和幂等保存。 */
export default function BookmarkButton({ result }: { result: Pick<Result, "url" | "title"> }) {
  const [state, setState] = useState("idle");
  const save = async () => {
    if (["saving", "saved", "exists"].includes(state)) return;
    setState("saving");
    try {
      const response = await saveBookmark({ url: result.url, title: result.title });
      setState(response.deduplicated ? "exists" : "saved");
      if (!response.deduplicated) window.dispatchEvent(new Event("cs:bookmark-saved"));
    } catch (error) {
      setState("error");
      if (!(error instanceof ApiError)) console.error(error);
    }
  };
  const label = state === "saving" ? "收藏中…" : state === "saved" ? "已收藏"
    : state === "exists" ? "已在书签" : state === "error" ? "收藏失败" : "收藏";
  return (
    <button className={`card__save card__save--${state}`} type="button"
      onClick={() => void save()} disabled={state === "saving"} title="收藏到本机书签">
      {label}
    </button>
  );
}
