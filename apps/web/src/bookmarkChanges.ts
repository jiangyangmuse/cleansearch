export const BOOKMARKS_CHANGED = "cs:bookmarks-changed";

export function notifyBookmarksChanged(): void {
  try {
    localStorage.setItem(BOOKMARKS_CHANGED, `${Date.now()}-${Math.random()}`);
  } catch {
    // 同页通知仍可用；切回标签页时也会重新读取。
  }
  window.dispatchEvent(new Event(BOOKMARKS_CHANGED));
}
