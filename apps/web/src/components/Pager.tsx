import { MAX_PAGE } from "../urlState";

interface Props {
  page: number;
  /** 本页结果条数（不含官方入口） */
  count: number;
  canNext: boolean;
  busy?: boolean;
  position: "top" | "bottom";
  onPrev: () => void;
  onNext: () => void;
}

export default function Pager({ page, count, canNext, busy, position, onPrev, onNext }: Props) {
  return (
    <nav className={`pager pager--${position}`} aria-label={`分页（${position === "top" ? "顶部" : "底部"}）`}>
      <button className="chip" type="button" disabled={busy || page <= 1} onClick={onPrev}
        title="上一页（快捷键 [）">上一页</button>
      <span className="pager__label" tabIndex={-1}>第 {page} 页 · {count > 0 ? `本页 ${count} 条` : "本页无结果"}</span>
      <button className="chip" type="button" disabled={busy || page >= MAX_PAGE || !canNext} onClick={onNext}
        title="下一页（快捷键 ]）">下一页</button>
      <span className="pager__keys" aria-hidden="true"><kbd>[</kbd><kbd>]</kbd></span>
    </nav>
  );
}
