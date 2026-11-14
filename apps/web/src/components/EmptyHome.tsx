import { useEffect, useState } from "react";
import { HISTORY_CHANGED, HISTORY_KEY, deleteSearchHistoryEntry, readSearchHistory, type HistoryEntry } from "../searchHistory";

interface Props {
  /** 点示例或历史词：填进搜索框并直接检索。 */
  onSearch: (entry: HistoryEntry) => void;
  /** 快捷入口：书签页 / 单页总结由链接处理，AI 对话开右侧工具面板。 */
  onOpenConversation: () => void;
}

const SAMPLES = ["python asyncio 教程", "本地大模型 部署", "本周 AI 新闻"];

/** 空首页：给第一次使用的人一个起点，而不是一整屏空白。 */
export default function EmptyHome({ onSearch, onOpenConversation }: Props) {
  const [history, setHistory] = useState(() => readSearchHistory().slice(0, 8));

  useEffect(() => {
    const sync = () => setHistory(readSearchHistory().slice(0, 8));
    const onStorage = (event: StorageEvent) => {
      if (event.key === HISTORY_KEY || event.key === null) sync();
    };
    sync();
    window.addEventListener(HISTORY_CHANGED, sync);
    window.addEventListener("storage", onStorage);
    window.addEventListener("pageshow", sync);
    return () => {
      window.removeEventListener(HISTORY_CHANGED, sync);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("pageshow", sync);
    };
  }, []);

  return (
    <section className="empty-home" aria-label="开始搜索">
      {history.length > 0 && (
        <div className="empty-home__block">
          <h2 className="empty-home__title">最近搜索</h2>
          <ul className="empty-home__chips">
            {history.map(entry => (
              <li key={`${entry.query}|${entry.literal ? 1 : 0}`} className="empty-home__chip">
                <button type="button" className="chip" onClick={() => onSearch(entry)}>
                  {entry.query}
                </button>
                <button type="button" className="empty-home__remove" aria-label={`删除历史 ${entry.query}`}
                  onClick={event => {
                    const button = event.currentTarget;
                    const item = button.closest("li");
                    const neighbor = item?.nextElementSibling ?? item?.previousElementSibling;
                    const next = neighbor?.querySelector<HTMLButtonElement>(".empty-home__remove")
                      ?? button.closest(".empty-home")?.querySelector<HTMLButtonElement>(".empty-home__examples button");
                    if (deleteSearchHistoryEntry(entry) && document.activeElement === button) next?.focus();
                  }}>×</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="empty-home__block">
        <h2 className="empty-home__title">试试这些</h2>
        <ul className="empty-home__chips empty-home__examples">
          {SAMPLES.map(sample => (
            <li key={sample}>
              <button type="button" className="chip" onClick={() => onSearch({ query: sample, literal: false })}>{sample}</button>
            </li>
          ))}
        </ul>
      </div>

      <div className="empty-home__block">
        <h2 className="empty-home__title">也可以直接</h2>
        <ul className="empty-home__links">
          <li><a href="/bookmarks">书签</a></li>
          <li><a href="/s">单页总结</a></li>
          <li><button type="button" onClick={onOpenConversation}>AI 对话</button></li>
        </ul>
        <p className="empty-home__hint">
          按 <kbd>/</kbd> 聚焦搜索框，<kbd>?</kbd> 查看全部快捷键。
        </p>
      </div>
    </section>
  );
}
