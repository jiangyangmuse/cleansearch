"""Netscape Bookmark HTML 解析与导出（浏览器互迁格式）。

Chrome / Edge / Firefox 导出的都是这一套：
<DL><p> 表示一层目录，<DT><H3> 是目录名，<DT><A> 是书签。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser

HEADER = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file. -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
"""


@dataclass
class ParsedBookmark:
    url: str
    title: str
    folder: tuple[str, ...] = ()


class _NetscapeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[ParsedBookmark] = []
        self.has_doctype = False
        self.has_list = False
        self._folders: list[str] = []
        self._pending_folder: str | None = None
        self._in_h3 = False
        self._h3_text = ""
        self._current: ParsedBookmark | None = None
        self._text: list[str] = []

    def handle_decl(self, decl: str) -> None:
        if decl.lower().split() == ["doctype", "netscape-bookmark-file-1"]:
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            self._in_h3 = True
            self._h3_text = ""
        elif tag == "dl":
            self.has_list = True
            if self._pending_folder is not None:
                self._folders.append(self._pending_folder.strip())
                self._pending_folder = None
            else:
                self._folders.append("")
        elif tag == "a" and self._folders:
            values = {key: (value or "") for key, value in attrs}
            href = values.get("href", "").strip()
            self._current = ParsedBookmark(
                url=href,
                title="",
                folder=tuple(folder for folder in self._folders if folder),
            )
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_h3:
            self._h3_text += data
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3":
            self._in_h3 = False
            self._pending_folder = self._h3_text.strip()
        elif tag == "a" and self._current is not None:
            self._current.title = "".join(self._text).strip()
            if self._current.url:
                self.items.append(self._current)
            self._current = None
        elif tag == "dl" and self._folders:
            self._folders.pop()


def parse_netscape(text: str) -> list[ParsedBookmark]:
    parser = _NetscapeParser()
    parser.feed(text)
    parser.close()
    if not parser.has_list or not (parser.has_doctype or parser.items):
        raise ValueError("不是 Netscape 书签 HTML")
    return parser.items


def export_netscape(
    bookmarks: list[dict],
    folders: dict[int, tuple[str, ...]],
    now: int | None = None,
) -> str:
    stamp = now or int(time.time())
    by_group: dict[int | None, list[dict]] = {}
    for item in bookmarks:
        by_group.setdefault(item.get("group_id"), []).append(item)
    lines: list[str] = [HEADER.rstrip(), "<DL><p>"]
    lines.extend(_item_lines(by_group.get(None, []), stamp))
    previous: tuple[str, ...] = ()
    for group_id, path in sorted(folders.items(), key=lambda entry: entry[1]):
        shared = 0
        for last, current in zip(previous, path):
            if last != current:
                break
            shared += 1
        lines.extend("    </DL><p>" for _ in previous[shared:])
        for name in path[shared:]:
            lines.extend([f"    <DT><H3>{escape(name)}</H3>", "    <DL><p>"])
        lines.extend(_item_lines(by_group.get(group_id, []), stamp))
        previous = path
    lines.extend("    </DL><p>" for _ in previous)
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def _item_lines(items: list[dict], stamp: int) -> list[str]:
    lines: list[str] = []
    for item in items:
        created = int(item.get("created_at") or stamp)
        title = escape(item.get("title") or "")
        lines.append(f'        <DT><A HREF="{escape(item["url"], quote=True)}" ADD_DATE="{created}">{title}</A>')
    return lines
