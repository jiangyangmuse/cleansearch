import { useEffect, useState } from "react";
import { listBookmarks } from "../api";
import type { Bookmark } from "../types";
import { safeHref } from "../url";

const PREFERENCE = "cs-quick-bookmarks-open";

function initiallyOpen() {
  const saved = localStorage.getItem(PREFERENCE);
  return saved === null ? matchMedia("(min-width: 901px)").matches : saved === "true";
}

export default function QuickBookmarks() {
  const [open, setOpen] = useState(initiallyOpen);
  const [items, setItems] = useState<Bookmark[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let controller: AbortController | undefined;
    const refresh = () => {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      setFailed(false);
      void listBookmarks({ limit: 6 }, request.signal).then((response) => {
        if (!request.signal.aborted) setItems(response.items.filter(item => safeHref(item.url)));
      }).catch(() => {
        if (!request.signal.aborted) setFailed(true);
      });
    };
    refresh();
    window.addEventListener("cs:bookmark-saved", refresh);
    return () => {
      controller?.abort();
      window.removeEventListener("cs:bookmark-saved", refresh);
    };
  }, [open]);

  return (
    <section className="quick-bookmarks" aria-labelledby="quick-bookmarks-title">
      <h2 id="quick-bookmarks-title">
        <button type="button" className="quick-bookmarks__toggle" aria-expanded={open}
          aria-controls="quick-bookmarks-items" onClick={() => {
            localStorage.setItem(PREFERENCE, String(!open));
            setOpen(!open);
          }}>
          <span className="quick-bookmarks__icon"><i className="ws-icon ws-icon--bookmark" aria-hidden="true" /></span>
          书签快捷栏
          <i className="ws-icon ws-icon--chevron" aria-hidden="true" />
        </button>
      </h2>
      <div id="quick-bookmarks-items" className="quick-bookmarks__body" hidden={!open}>
        {failed ? <p role="status">暂时无法读取书签。</p> : items === null ? (
          <p role="status">正在读取书签…</p>
        ) : items.length === 0 ? (
          <p>收藏搜索结果后，可以在这里快速打开。</p>
        ) : (
          <ul>
            {items.map((item) => {
              const href = safeHref(item.url);
              if (!href) return null;
              const host = new URL(href).hostname;
              return (
                <li key={item.id}>
                  <a className="quick-bookmarks__item" href={href} target="_blank" rel="noopener noreferrer">
                    <span className="quick-bookmarks__letter" aria-hidden="true">
                      {host.replace(/^www\./, "").charAt(0).toUpperCase()}
                    </span>
                    <span className="quick-bookmarks__description">
                      <strong>{item.title || host}</strong><small>{host}</small>
                    </span>
                    <span className="quick-bookmarks__external" aria-hidden="true">↗</span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
        <a className="quick-bookmarks__all" href="/bookmarks">全部书签 <span aria-hidden="true">→</span></a>
      </div>
    </section>
  );
}
