-- CleanSearch 书签存储（M3）
-- 单人使用；多用户时按构建方案 Q3 再加 user_id。

CREATE TABLE IF NOT EXISTS bookmark_groups (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  folder_path TEXT,
  icon    TEXT,
  sort    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bookmarks (
  id          INTEGER PRIMARY KEY,
  url         TEXT NOT NULL,
  url_key     TEXT NOT NULL UNIQUE,   -- canonical URL，导入/重复收藏靠它去重
  title       TEXT,
  favicon     TEXT,
  group_id    INTEGER REFERENCES bookmark_groups(id) ON DELETE SET NULL,
  note        TEXT,
  created_at  INTEGER NOT NULL,
  last_visit  INTEGER,
  visits      INTEGER DEFAULT 0,
  dead        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_group ON bookmarks(group_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks(created_at DESC);

CREATE TABLE IF NOT EXISTS bookmark_tags (
  bookmark_id INTEGER REFERENCES bookmarks(id) ON DELETE CASCADE,
  tag         TEXT NOT NULL,
  PRIMARY KEY (bookmark_id, tag)
);
