import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  checkDeadLinks,
  createGroup,
  deleteBookmark,
  faviconUrl,
  importJobStatus,
  listBookmarks,
  moveBookmark,
  saveBookmark,
  startImportJob,
} from "./api";
import AppShell from "./components/AppShell";
import { notifyBookmarksChanged } from "./bookmarkChanges";
import type { Bookmark, BookmarkGroup } from "./types";
import { safeHref } from "./url";

type Status = "loading" | "ready" | "error";
const PAGE_SIZE = 48;

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function findSharedUrl(params: URLSearchParams): string | null {
  const direct = safeHref(params.get("url") ?? "");
  if (direct) return direct;
  const text = (params.get("text") ?? "").trim();
  if (!/[\s，。！？；、（）【】「」『』《》]/.test(text)) {
    const whole = safeHref(text);
    if (whole) return whole;
  }
  for (const match of text.matchAll(/https?:\/\/[^\s<>"'，。！？；、（）【】「」『』《》]+/gi)) {
    let candidate = match[0].replace(/[,.!?;]+$/, "");
    while (candidate.endsWith(")") && candidate.split(")").length > candidate.split("(").length) {
      candidate = candidate.slice(0, -1);
    }
    const url = safeHref(candidate);
    if (url) return url;
  }
  return null;
}

export default function BookmarkPage() {
  const [items, setItems] = useState<Bookmark[]>([]);
  const [groups, setGroups] = useState<BookmarkGroup[]>([]);
  const [query, setQuery] = useState("");
  const [view, setView] = useState({
    q: "",
    group: null as number | null,
    tag: null as string | null,
    offset: 0,
  });
  const [tagOptions, setTagOptions] = useState<{ tag: string; count: number }[]>([]);
  const [total, setTotal] = useState(0);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [adding, setAdding] = useState(false);
  const addRequest = useRef(false);
  const [moving, setMoving] = useState<Set<number>>(() => new Set());
  // 窄屏默认收起添加表单，桌面保持展开
  const [addOpen, setAddOpen] = useState(() => !window.matchMedia("(max-width: 900px)").matches);

  const [addUrl, setAddUrl] = useState("");
  const [addTitle, setAddTitle] = useState("");
  const [addGroup, setAddGroup] = useState("");
  const [addTags, setAddTags] = useState("");
  const [groupName, setGroupName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [checking, setChecking] = useState(false);
  const [importProgress, setImportProgress] = useState<{ processed: number; total: number } | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);

  // Android 分享的链接也可能藏在 text 的一段说明中。
  useEffect(() => {
    const pageUrl = new URL(window.location.href);
    const fragment = new URLSearchParams(pageUrl.hash.slice(1));
    const fromFragment = fragment.get("shared") === "1";
    const params = fromFragment ? fragment : pageUrl.searchParams;
    if (!["shared", "url", "text", "title", "files"].some(name => params.has(name))) return;
    const sharedUrl = findSharedUrl(params);
    const sharedTitle = [...(params.get("title") ?? "").trim()].slice(0, 512).join("");
    const hasFiles = params.get("files") === "1";
    if (fromFragment) pageUrl.hash = "";
    for (const name of ["shared", "url", "text", "title", "files"]) pageUrl.searchParams.delete(name);
    window.history.replaceState(window.history.state, "", pageUrl);
    if (!sharedUrl) {
      setMessage(hasFiles ? "书签只保存网页链接。请分享或粘贴网页地址。" : "分享内容中没有可收藏的 HTTP(S) 链接");
      return;
    }
    setAddUrl(sharedUrl);
    setAddTitle(sharedTitle);
    setAddOpen(true);
    setMessage("来自分享：确认标题和分组后点「收藏」");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    setError(null);
    void listBookmarks({ ...view, limit: PAGE_SIZE }, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        if (view.offset > 0 && view.offset >= data.total) {
          const offset = Math.floor(Math.max(0, data.total - 1) / PAGE_SIZE) * PAGE_SIZE;
          setView((current) => ({ ...current, offset }));
          return;
        }
        setItems(data.items);
        setGroups(data.groups);
        setTagOptions(data.tags ?? []);
        setTotal(data.total);
        setStatus("ready");
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(caught instanceof ApiError ? caught.message : "加载书签失败");
        setStatus("error");
      });
    return () => controller.abort();
  }, [view, revision]);

  const reload = (firstPage = false) => {
    if (firstPage) setView((current) => ({ ...current, offset: 0 }));
    setRevision((current) => current + 1);
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setView({ q: query.trim(), group: view.group, tag: view.tag, offset: 0 });
  };

  const selectGroup = (group: number | null) => {
    setView({ q: query.trim(), group, tag: null, offset: 0 });
  };

  const selectTag = (tag: string | null) => {
    setView({ q: query.trim(), group: view.group, tag, offset: 0 });
  };

  const addBookmark = async (event: FormEvent) => {
    event.preventDefault();
    if (!addUrl.trim() || addRequest.current) return;
    addRequest.current = true;
    setAdding(true);
    setError(null);
    try {
      const result = await saveBookmark({
        url: addUrl.trim(),
        title: addTitle.trim() || undefined,
        group_id: addGroup ? Number(addGroup) : null,
        tags: addTags
          .split(/[,，\s]+/)
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
      setMessage(result.deduplicated ? "这个链接已在书签里，未重复添加" : "已收藏");
      setAddUrl("");
      setAddTitle("");
      setAddTags("");
      reload(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "收藏失败");
    } finally {
      addRequest.current = false;
      setAdding(false);
    }
  };

  const createNewGroup = async (event: FormEvent) => {
    event.preventDefault();
    if (!groupName.trim()) return;
    try {
      await createGroup(groupName.trim());
      setGroupName("");
      setMessage("分组已创建");
      reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "创建分组失败");
    }
  };

  const remove = async (bookmark: Bookmark) => {
    try {
      await deleteBookmark(bookmark.id);
      reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "删除失败");
    }
  };

  const move = async (bookmark: Bookmark, groupId: number | null) => {
    if (bookmark.group_id === groupId || moving.has(bookmark.id)) return;
    setMoving((current) => new Set(current).add(bookmark.id));
    setMessage(null);
    setError(null);
    try {
      const updated = await moveBookmark(bookmark.id, groupId);
      setMessage(updated.group_name ? `已移至「${updated.group_name}」` : "已移至未分组");
      reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "移动书签失败");
    } finally {
      setMoving((current) => {
        const next = new Set(current);
        next.delete(bookmark.id);
        return next;
      });
    }
  };

  const runDeadCheck = async () => {
    if (checking || status !== "ready" || items.length === 0) return;
    setChecking(true);
    setMessage(null);
    setError(null);
    try {
      const result = await checkDeadLinks(items.map((item) => item.id));
      setMessage(`本页检查 ${result.checked} 条：${result.dead} 条失效，${result.unknown} 条暂无法确认`);
      reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "死链检测失败");
    } finally {
      setChecking(false);
    }
  };

  const importFile = async (file: File | undefined) => {
    if (!file || importing) return;
    setImporting(true);
    setError(null);
    setImportProgress(null);
    try {
      const { id } = await startImportJob(file);
      // 轮询到结束：大文件导入时用户能看到进度而不是干等
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const job = await importJobStatus(id);
        setImportProgress({ processed: job.processed, total: job.total });
        if (job.state === "done") {
          if (job.created > 0) notifyBookmarksChanged();
          setMessage(
            `导入 ${job.total} 条：新增 ${job.created}，跳过 ${job.skipped} 条，新建分组 ${job.groups_created}`,
          );
          reload(true);
          break;
        }
        if (job.state === "error") throw new Error(job.error || "导入失败");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "导入失败");
    } finally {
      setImporting(false);
      setImportProgress(null);
    }
  };

  return (
    <AppShell current="bookmarks" title="书签启动台 · CleanSearch" maxWidth={1120}>
      <main id="main" tabIndex={-1} className="shell-main">
        <h1 className="shell-title">书签启动台</h1>
        <section className="bm-toolbar">
          <form className="bm-search" onSubmit={submitSearch}>
            <input
              className="searchbar__input"
              type="search"
              maxLength={200}
              value={query}
              placeholder="按标题或网址搜索书签"
              onChange={(event) => setQuery(event.target.value)}
              aria-label="搜索书签"
            />
            <button className="button" type="submit">
              搜索
            </button>
          </form>
          <div className="bm-actions">
            <input
              ref={fileRef}
              type="file"
              accept=".html,.htm,text/html"
              hidden
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                void importFile(file);
              }}
            />
            <button className="button button--ghost" type="button" disabled={importing} onClick={() => fileRef.current?.click()}>
              {importing
                ? importProgress && importProgress.total > 0
                  ? `导入中 ${importProgress.processed}/${importProgress.total}`
                  : "导入中…"
                : "导入 HTML"}
            </button>
            <a className="button button--ghost" href="/api/bookmarks/export" download>
              导出 HTML
            </a>
            <button className="button button--ghost" type="button" onClick={() => void runDeadCheck()}
              disabled={checking || status !== "ready" || items.length === 0}>
              {checking ? "检测中…" : "检测本页死链"}
            </button>
          </div>
        </section>

        <section className="bm-groups" aria-label="分组">
          <button
            className={view.group === null ? "chip chip--active" : "chip"}
            aria-pressed={view.group === null}
            type="button"
            onClick={() => selectGroup(null)}
          >
            全部
          </button>
          {groups.map((group) => (
            <button
              key={group.id}
              className={view.group === group.id ? "chip chip--active" : "chip"}
              aria-pressed={view.group === group.id}
              type="button"
              onClick={() => selectGroup(group.id)}
              onDragOver={(event) => {
                if (dragging !== null) event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                const raw = event.dataTransfer.getData("text/plain");
                const id = Number(raw || dragging);
                const item = items.find((candidate) => candidate.id === id);
                setDragging(null);
                if (item) void move(item, group.id);
              }}
            >
              {group.name} <span className="chip__count">{group.count}</span>
            </button>
          ))}
          <form className="bm-newgroup" onSubmit={createNewGroup}>
            <input
              value={groupName}
              placeholder="新建分组"
              onChange={(event) => setGroupName(event.target.value)}
              aria-label="新建分组名"
            />
            <button className="chip" type="submit">
              +
            </button>
          </form>
        </section>

        {tagOptions.length > 0 ? (
          <section className="bm-tags" aria-label="标签">
            <span className="pager__label">标签：</span>
            {tagOptions.map(({ tag, count }) => (
              <button
                key={tag}
                type="button"
                className={view.tag === tag ? "bm-tag bm-tag--active" : "bm-tag"}
                aria-pressed={view.tag === tag}
                onClick={() => selectTag(view.tag === tag ? null : tag)}
              >
                {tag} {count}
              </button>
            ))}
          </section>
        ) : null}

        <details className="bm-add-details" open={addOpen}
          onToggle={event => setAddOpen(event.currentTarget.open)}>
          <summary className="bm-add-details__summary">
            <i className="ws-icon ws-icon--chevron" aria-hidden="true" />手动添加书签
          </summary>
          <form className="bm-add" onSubmit={addBookmark}>
          <input
            value={addUrl}
            type="url"
            required
            maxLength={2048}
            placeholder="粘贴网址"
            onChange={(event) => setAddUrl(event.target.value)}
            aria-label="新书签网址"
          />
          <input
            value={addTitle}
            maxLength={512}
            placeholder="标题（可选）"
            onChange={(event) => setAddTitle(event.target.value)}
            aria-label="新书签标题"
          />
          <input
            value={addTags}
            placeholder="标签（逗号分隔，可选）"
            onChange={(event) => setAddTags(event.target.value)}
            aria-label="新书签标签"
          />
          <select value={addGroup} onChange={(event) => setAddGroup(event.target.value)} aria-label="选择分组">
            <option value="">未分组</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
          <button className="button" type="submit" disabled={adding}>
            {adding ? "收藏中…" : "收藏"}
          </button>
          </form>
        </details>

        {message ? <p className="bm-message" role="status">{message}</p> : null}
        {error ? <p className="bm-message bm-message--error" role="alert">{error}</p> : null}

        {status === "loading" ? <p className="bm-empty">加载中…</p> : null}
        {status === "ready" && items.length === 0 ? (
          <p className="bm-empty">
            {view.q || view.group !== null
              ? "没有符合当前筛选条件的书签。"
              : "还没有书签。从搜索结果点「收藏」，或导入浏览器导出的 HTML。"}
          </p>
        ) : null}
        {status === "ready" && total > 0 ? (
          <nav className="bm-pagination" aria-label="书签分页">
            <span>第 {view.offset + 1}–{view.offset + items.length} 条，共 {total} 条</span>
            {total > PAGE_SIZE ? (
              <>
                <button className="chip" type="button" disabled={view.offset === 0}
                  onClick={() => setView({ ...view, offset: view.offset - PAGE_SIZE })}>
                  上一页
                </button>
                <button className="chip" type="button" disabled={view.offset + PAGE_SIZE >= total}
                  onClick={() => setView({ ...view, offset: view.offset + PAGE_SIZE })}>
                  下一页
                </button>
              </>
            ) : null}
          </nav>
        ) : null}

        <div className="bm-grid">
          {status === "ready" && items.map((item) => {
            const href = safeHref(item.url);
            return (
              <article
                className={item.dead ? "bm-card bm-card--dead" : "bm-card"}
                key={item.id}
                data-bookmark-id={item.id}
                draggable
                onDragStart={(event) => {
                  setDragging(item.id);
                  event.dataTransfer.setData("text/plain", String(item.id));
                  event.dataTransfer.effectAllowed = "move";
                }}
                onDragEnd={() => setDragging(null)}
                style={dragging === item.id ? { opacity: 0.4 } : undefined}
              >
                <div className="bm-card__meta">
                  {item.favicon || hostOf(item.url) ? (
                    <img
                      src={faviconUrl(hostOf(item.url)) ?? item.favicon ?? ""}
                      alt=""
                      width={16}
                      height={16}
                      loading="lazy"
                      onError={(event) => {
                        event.currentTarget.style.visibility = "hidden";
                      }}
                    />
                  ) : null}
                  <span>{hostOf(item.url)}</span>
                  {item.group_name ? <span className="card__tag">{item.group_name}</span> : null}
                  {item.dead ? (
                    <span
                      className="bm-card__dead"
                      title={
                        item.dead_checked_at
                          ? `检查于 ${new Date(item.dead_checked_at * 1000).toLocaleString()}`
                          : "尚未记录检查时间"
                      }
                    >
                      失效{item.dead_status ? ` · ${item.dead_status}` : ""}
                    </span>
                  ) : null}
                </div>
                <h2 className="bm-card__title">
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      {item.title || item.url}
                    </a>
                  ) : (
                    <span>{item.title || item.url}</span>
                  )}
                </h2>
                {item.note ? <p className="bm-card__note">{item.note}</p> : null}
                {item.tags.length > 0 ? (
                  <div className="bm-card__tags">
                    {item.tags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        className="bm-tag"
                        onClick={() => selectTag(tag)}
                        title="按这个标签筛选"
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="bm-card__actions">
                  <select
                    value={item.group_id ?? ""}
                    aria-label={`移动「${item.title || item.url}」的分组`}
                    disabled={moving.has(item.id)}
                    onChange={(event) => void move(item, event.target.value ? Number(event.target.value) : null)}
                  >
                    <option value="">未分组</option>
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>{group.name}</option>
                    ))}
                  </select>
                  <button className="bm-card__remove" type="button" disabled={moving.has(item.id)} onClick={() => void remove(item)}>
                    删除
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </main>

      <footer className="footer">CleanSearch · 书签存在本机 SQLite（data/cs.db），导入导出用 Netscape HTML</footer>
    </AppShell>
  );
}
