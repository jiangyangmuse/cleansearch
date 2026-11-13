"""书签仓储：SQLite + FTS5（不可用时降级 LIKE），单人单进程使用。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from app.core.netscape import export_netscape, parse_netscape
from app.core.normalize import canonical_url, favicon_for, is_renderable_url

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

FTS_DDL = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
        title, url, note,
        content='bookmarks', content_rowid='id'
    )""",
    """CREATE TRIGGER IF NOT EXISTS bookmarks_ai AFTER INSERT ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(rowid, title, url, note)
        VALUES (new.id, new.title, new.url, new.note);
    END""",
    """CREATE TRIGGER IF NOT EXISTS bookmarks_ad AFTER DELETE ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, url, note)
        VALUES ('delete', old.id, old.title, old.url, old.note);
    END""",
    """CREATE TRIGGER IF NOT EXISTS bookmarks_au AFTER UPDATE ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, url, note)
        VALUES ('delete', old.id, old.title, old.url, old.note);
        INSERT INTO bookmarks_fts(rowid, title, url, note)
        VALUES (new.id, new.title, new.url, new.note);
    END""",
]


class BookmarkError(ValueError):
    """可预期的输入错误，路由层转成 400。"""


def _fts_query(text: str) -> str:
    tokens = [token.replace('"', "") for token in text.split() if token.strip()]
    if not tokens:
        return '""'
    return " ".join(f'"{token}"*' for token in tokens)


class BookmarkRepo:
    def __init__(self, db_path: Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # 单文件多连接：给写入排队，避免 database is locked
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.fts_enabled = self._init_schema()

    # ---------- 初始化 ----------
    def _migrate(self) -> None:
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(bookmarks)")}
        for name, ddl in (
            ("dead_status", "ALTER TABLE bookmarks ADD COLUMN dead_status INTEGER"),
            ("dead_checked_at", "ALTER TABLE bookmarks ADD COLUMN dead_checked_at INTEGER"),
        ):
            if name not in columns:
                self._conn.execute(ddl)
        self._conn.commit()

    def _init_schema(self) -> bool:
        with self._lock:
            self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            with self._conn:
                self._conn.execute("BEGIN IMMEDIATE")
                columns = self._conn.execute("PRAGMA table_info(bookmark_groups)")
                if not any(column["name"] == "folder_path" for column in columns):
                    self._conn.execute("ALTER TABLE bookmark_groups ADD COLUMN folder_path TEXT")
        try:
            with self._lock:
                for statement in FTS_DDL:
                    self._conn.execute(statement)
                self._conn.commit()
            self._migrate()
            return True
        except sqlite3.OperationalError:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- 查询 ----------
    def _filters(
        self, q: str | None, group_id: int | None, tag: str | None = None
    ) -> tuple[str, list[object]]:
        params: list[object] = []
        clauses: list[str] = []
        q = (q or "").strip()
        if q:
            # FTS 的前缀词匹配不会命中「数据分析」里的「分析」，网址中间也一样。
            matches = [f"instr(lower(b.{field}), lower(?)) > 0" for field in ("title", "url", "note")]
            params.extend([q, q, q])
            if self.fts_enabled:
                matches.append("b.id IN (SELECT rowid FROM bookmarks_fts WHERE bookmarks_fts MATCH ?)")
                params.append(_fts_query(q))
            clauses.append("(" + " OR ".join(matches) + ")")
        if group_id is not None:
            clauses.append("b.group_id = ?")
            params.append(group_id)
        tag = (tag or "").strip()
        if tag:
            clauses.append(
                "b.id IN (SELECT bookmark_id FROM bookmark_tags WHERE tag = ?)"
            )
            params.append(tag)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def _select(self, where: str, params: list[object], limit: int, offset: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT b.*, g.name AS group_name FROM bookmarks b "
            "LEFT JOIN bookmark_groups g ON g.id = b.group_id" + where +
            " ORDER BY b.created_at DESC, b.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return self._attach_tags([self._row_to_dict(row) for row in rows])

    def list(
        self,
        q: str | None = None,
        group_id: int | None = None,
        limit: int = 200,
        offset: int = 0,
        tag: str | None = None,
    ) -> list[dict]:
        where, params = self._filters(q, group_id, tag)
        with self._lock:
            return self._select(where, params, limit, offset)

    def page(
        self,
        q: str | None,
        group_id: int | None,
        limit: int,
        offset: int,
        tag: str | None = None,
    ) -> tuple[list[dict], int]:
        where, params = self._filters(q, group_id, tag)
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM bookmarks b" + where, params).fetchone()[0]
            return self._select(where, params, limit, offset), total

    def get(self, bookmark_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT b.*, g.name AS group_name FROM bookmarks b "
                "LEFT JOIN bookmark_groups g ON g.id = b.group_id WHERE b.id = ?",
                (bookmark_id,),
            ).fetchone()
        if row is None:
            return None
        return self._attach_tags([self._row_to_dict(row)])[0]

    def groups(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT g.id, g.name, g.icon, g.sort, g.folder_path, COUNT(b.id) AS count "
                "FROM bookmark_groups g LEFT JOIN bookmarks b ON b.group_id = g.id "
                "GROUP BY g.id ORDER BY g.sort, g.id"
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------- 写入 ----------
    def add(
        self,
        url: str,
        title: str | None = None,
        group_id: int | None = None,
        note: str | None = None,
        tags: list[str] | None = None,
        *,
        update_existing: bool = True,
    ) -> tuple[dict, bool]:
        url = (url or "").strip()
        if not is_renderable_url(url):
            raise BookmarkError("只支持 http(s) 链接")
        key = canonical_url(url)
        if not key:
            raise BookmarkError("URL 无法规范化")
        clean_title = (title or "").strip() or None
        clean_note = (note or "").strip() or None
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            if group_id is not None and not self._group_exists(group_id):
                raise BookmarkError(f"分组不存在：{group_id}")
            existing = self._conn.execute(
                "SELECT * FROM bookmarks WHERE url_key = ?", (key,)
            ).fetchone()
            if existing:
                if not update_existing:
                    return self._row_to_dict(existing), True
                # 重复收藏：不新增，补空标题 / 补分组 / 合并备注
                updates: dict[str, object] = {}
                if clean_title and not existing["title"]:
                    updates["title"] = clean_title
                if group_id is not None and existing["group_id"] != group_id:
                    updates["group_id"] = group_id
                if clean_note and not existing["note"]:
                    updates["note"] = clean_note
                if updates:
                    assignments = ", ".join(f"{column} = ?" for column in updates)
                    self._conn.execute(
                        f"UPDATE bookmarks SET {assignments} WHERE id = ?",
                        [*updates.values(), existing["id"]],
                    )
                if tags:
                    self._add_tags(existing["id"], tags)
                return self.get(existing["id"]) or {}, True

            bookmark_id = self._insert_bookmark(url, key, clean_title, group_id, clean_note)
            if tags:
                self._add_tags(bookmark_id, tags)
            return self.get(bookmark_id) or {}, False

    def _insert_bookmark(
        self, url: str, key: str, title: str | None, group_id: int | None, note: str | None = None
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO bookmarks (url, url_key, title, favicon, group_id, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, key, title, favicon_for(url), group_id, note, int(time.time())),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def update(self, bookmark_id: int, **fields: object) -> dict | None:
        allowed = {"title", "group_id", "note", "dead", "dead_status", "dead_checked_at"}
        changes = {
            key: value for key, value in fields.items()
            if key in allowed and (value is not None or key == "group_id")
        }
        tags = fields.get("tags")
        if not changes and tags is None:
            return self.get(bookmark_id)
        if tags is not None:
            self._replace_tags(bookmark_id, tags)  # type: ignore[arg-type]
        if not changes:
            return self.get(bookmark_id)
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._lock, self._conn:
            group_id = changes.get("group_id")
            if isinstance(group_id, int) and not self._group_exists(group_id):
                raise BookmarkError(f"分组不存在：{group_id}")
            cursor = self._conn.execute(
                f"UPDATE bookmarks SET {assignments} WHERE id = ?",
                [*changes.values(), bookmark_id],
            )
            return self.get(bookmark_id) if cursor.rowcount else None

    def delete(self, bookmark_id: int, url: str | None = None) -> bool:
        with self._lock, self._conn:
            if url is None:
                cursor = self._conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            else:
                cursor = self._conn.execute(
                    "DELETE FROM bookmarks WHERE id = ? AND url_key = ?", (bookmark_id, canonical_url(url))
                )
        return bool(cursor.rowcount)

    def save_link_checks(self, changes: list[tuple[int | None, int, str, int | None, int]]) -> None:
        """changes: (dead, id, url, http_status, checked_at)。

        dead 为 None 表示「这次没确认」：只更新状态码与检查时间，保留原标记。
        """
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE bookmarks SET dead = COALESCE(?1, dead), dead_status = ?4, dead_checked_at = ?5 "
                "WHERE id = ?2 AND url = ?3",
                changes,
            )

    def create_group(self, name: str) -> dict:
        clean = (name or "").strip()
        if not clean:
            raise BookmarkError("分组名不能为空")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO bookmark_groups (name) VALUES (?)", (clean,)
            )
            row = self._conn.execute(
                "SELECT id, name, icon, sort FROM bookmark_groups WHERE name = ?", (clean,)
            ).fetchone()
        return dict(row)

    def tags(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT tag, COUNT(*) AS count FROM bookmark_tags GROUP BY tag ORDER BY count DESC, tag"
        ).fetchall()
        return [dict(row) for row in rows]

    def _attach_tags(self, items: list[dict]) -> list[dict]:
        if not items:
            return items
        ids = [item["id"] for item in items]
        placeholders = ",".join("?" for _ in ids)
        mapping: dict[int, list[str]] = {}
        for row in self._conn.execute(
            f"SELECT bookmark_id, tag FROM bookmark_tags WHERE bookmark_id IN ({placeholders}) ORDER BY tag",
            ids,
        ):
            mapping.setdefault(row["bookmark_id"], []).append(row["tag"])
        for item in items:
            item["tags"] = mapping.get(item["id"], [])
        return items

    def _replace_tags(self, bookmark_id: int, tags: list[str] | None) -> None:
        if tags is None:
            return
        with self._lock:
            self._conn.execute("DELETE FROM bookmark_tags WHERE bookmark_id = ?", (bookmark_id,))
            for tag in {tag.strip() for tag in tags if tag and tag.strip()}:
                self._conn.execute(
                    "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag) VALUES (?, ?)",
                    (bookmark_id, tag[:64]),
                )
            self._conn.commit()

    def find_by_url(self, url: str) -> dict | None:
        key = canonical_url(url)
        if not key:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM bookmarks WHERE url_key = ?", (key,)).fetchone()
        return self._row_to_dict(row) if row else None

    def ids_for_urls(self, urls: list[str]) -> dict[str, int]:
        """按 canonical url 批量查已收藏项，返回 {传入的原始 url: bookmark_id}。"""
        keys: dict[str, str] = {}
        for url in urls:
            key = canonical_url(url)
            if key:
                keys[url] = key
        if not keys:
            return {}
        unique = list(dict.fromkeys(keys.values()))
        placeholders = ",".join("?" for _ in unique)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, url_key FROM bookmarks WHERE url_key IN ({placeholders})",
                unique,
            ).fetchall()
        by_key = {row["url_key"]: row["id"] for row in rows}
        return {url: by_key[key] for url, key in keys.items() if key in by_key}

    def _group_exists(self, group_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bookmark_groups WHERE id = ?", (group_id,)
        ).fetchone()
        return bool(row)

    def tags(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tag, COUNT(*) AS count FROM bookmark_tags "
                "GROUP BY tag ORDER BY count DESC, tag"
            ).fetchall()
        return [dict(row) for row in rows]

    def _attach_tags(self, items: list[dict]) -> list[dict]:
        if not items:
            return items
        ids = [item["id"] for item in items]
        placeholders = ",".join("?" for _ in ids)
        mapping: dict[int, list[str]] = {}
        with self._lock:
            for row in self._conn.execute(
                f"SELECT bookmark_id, tag FROM bookmark_tags "
                f"WHERE bookmark_id IN ({placeholders}) ORDER BY tag",
                ids,
            ):
                mapping.setdefault(row["bookmark_id"], []).append(row["tag"])
        for item in items:
            item["tags"] = mapping.get(item["id"], [])
        return items

    def _replace_tags(self, bookmark_id: int, tags: list[str] | None) -> None:
        if tags is None:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM bookmark_tags WHERE bookmark_id = ?", (bookmark_id,))
            for tag in {tag.strip() for tag in tags if tag and tag.strip()}:
                self._conn.execute(
                    "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag) VALUES (?, ?)",
                    (bookmark_id, tag[:64]),
                )

    def _add_tags(self, bookmark_id: int, tags: list[str]) -> None:
        for tag in {tag.strip() for tag in tags if tag and tag.strip()}:
            self._conn.execute(
                "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag) VALUES (?, ?)",
                (bookmark_id, tag),
            )

    # ---------- 导入导出 ----------
    def import_netscape(self, text: str, progress=None) -> dict:
        """导入规则：已存在的 URL 一律跳过，不覆盖已有标题与分组。

        分组按需创建，只给真正新增的条目建，避免留下空分组。
        """
        try:
            items = parse_netscape(text)
        except ValueError as exc:
            raise BookmarkError(str(exc)) from exc
        created = skipped = groups_created = 0
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            groups = self.groups()
            known_groups = {self._folder_path(group): group["id"] for group in groups}
            used_names = {group["name"] for group in groups}
            total = len(items)
            processed = 0
            for item in items:
                processed += 1
                if progress and (processed % 50 == 0 or processed == total):
                    progress(processed, total)
                key = canonical_url(item.url) if is_renderable_url(item.url) else ""
                if not key or self._conn.execute("SELECT 1 FROM bookmarks WHERE url_key = ?", (key,)).fetchone():
                    skipped += 1
                    continue
                group_id = None
                if item.folder:
                    if item.folder not in known_groups:
                        known_groups[item.folder] = self._insert_import_group(item.folder, used_names)
                        groups_created += 1
                    group_id = known_groups[item.folder]
                self._insert_bookmark(item.url, key, item.title or None, group_id)
                created += 1
        return {
            "total": len(items),
            "created": created,
            "updated": 0,
            "skipped": skipped,
            "groups_created": groups_created,
        }

    def export_netscape(self) -> str:
        with self._lock:
            items = self.list(limit=-1)
            folders = {group["id"]: self._folder_path(group) for group in self.groups()}
        return export_netscape(items, folders)

    @staticmethod
    def _folder_path(group: dict) -> tuple[str, ...]:
        stored = group["folder_path"]
        return tuple(json.loads(stored)) if stored else (group["name"],)

    def _insert_import_group(self, path: tuple[str, ...], used_names: set[str]) -> int:
        base = " / ".join(path)
        name = base
        suffix = 2
        while name in used_names:
            name = f"{base}（{suffix}）"
            suffix += 1
        cursor = self._conn.execute(
            "INSERT INTO bookmark_groups (name, folder_path) VALUES (?, ?)",
            (name, json.dumps(path, ensure_ascii=False)),
        )
        used_names.add(name)
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    # ---------- 内部 ----------
    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data.setdefault("group_name", None)
        return data
