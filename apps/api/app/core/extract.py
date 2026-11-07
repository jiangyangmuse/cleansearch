"""正文提取：trafilatura（可选）→ 标准库回退。

trafilatura 未安装时走自带的 HTMLParser 提取器：丢掉脚本/导航/表单等噪声，
按块级标签切段，够 M4 的摘要与死链场景使用。
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser

try:  # 可选依赖：装了就用，没装不报错
    import trafilatura as _trafilatura
except Exception:  # pragma: no cover - 取决于环境
    _trafilatura = None

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
SKIP_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "form", "nav", "header",
    "footer", "aside", "iframe", "template", "button", "select", "input",
}
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "br", "tr",
    "table", "blockquote", "pre", "figure", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD = re.compile(r"[A-Za-z0-9']+")
WHITESPACE = re.compile(r"[ \t\f\v]+")
MAX_TEXT_CHARS = 40_000


@dataclass
class Article:
    url: str
    title: str
    text: str
    byline: str | None
    published: str | None
    word_count: int
    read_minutes: int
    content_hash: str
    extractor: str


class _BlockTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self.byline: str | None = None
        self.published: str | None = None
        self._in_title = False
        self._in_body = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # XHTML 自闭合标签不参与嵌套计数
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        # 元信息要先收，再判断是否跳过（meta / time 不是正文块）
        if tag == "meta":
            name = values.get("name", "").lower() or values.get("property", "").lower()
            content = values.get("content", "").strip()
            if name in ("author", "article:author") and content and not self.byline:
                self.byline = content
            if name in ("article:published_time", "date", "pubdate") and content and not self.published:
                self.published = content
        if tag == "time" and values.get("datetime") and not self.published:
            self.published = values["datetime"]

        if tag in VOID_TAGS:
            # <input> 之类没有结束标签，误计入 skip_depth 会吞掉整页正文
            return
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self._buffer.append(data)

    def _flush(self) -> None:
        if not self._buffer:
            return
        text = WHITESPACE.sub(" ", "".join(self._buffer)).strip()
        self._buffer = []
        if len(text) >= 2:
            self.blocks.append(text)

    def close(self) -> None:  # type: ignore[override]
        self._flush()
        super().close()


NAV_HINT = re.compile(r"^(navigation|index|modules|next|previous|skip to|contents|menu)\b", re.I)
SEPARATORS = re.compile(r"[|»›/]{1}")
SENTENCE_ENDERS = re.compile(r"[。！？!?.;；]")


def _is_navigation(line: str) -> bool:
    if NAV_HINT.match(line):
        return True
    if ("»" in line or "›" in line) and not SENTENCE_ENDERS.search(line):
        return True
    if line.rstrip().endswith(("»", "›", "|")):
        return True
    separators = len(SEPARATORS.findall(line))
    # 面包屑/工具条：分隔符多、句子成分少
    return separators >= 3 and len(SENTENCE_ENDERS.findall(line)) == 0


def _clean_blocks(blocks: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        line = " ".join(block.split())
        if not line or line in seen:
            continue
        if len(line) < 8 and not CJK.search(line):
            continue
        if _is_navigation(line):
            continue
        seen.add(line)
        cleaned.append(line)

    # 有足够多「像句子」的块时，把没有标点的碎行当噪声丢掉
    prose = [line for line in cleaned if SENTENCE_ENDERS.search(line) or len(line) >= 80]
    if len(prose) >= 2:
        return prose
    return cleaned


def _count_units(text: str) -> int:
    cjk = len(CJK.findall(text))
    latin = len(LATIN_WORD.findall(text))
    return cjk + latin


def extract_article(html: str, url: str = "", fallback_title: str = "") -> Article:
    parser = _BlockTextParser()
    parser.feed(html)
    parser.close()

    title = (parser.title or fallback_title or "").strip()
    blocks = _clean_blocks(parser.blocks)
    text = "\n".join(blocks)
    extractor = "stdlib"

    if _trafilatura is not None:
        try:
            extracted = _trafilatura.extract(
                html, url=url or None, include_comments=False, include_tables=False
            )
            if extracted and len(extracted) > len(text) * 0.5:
                text = extracted.strip()
                extractor = "trafilatura"
        except Exception:  # pragma: no cover - 解析器内部异常不影响回退
            pass

    text = text[:MAX_TEXT_CHARS]
    units = _count_units(text)
    read_minutes = max(1, math.ceil(units / 400)) if units else 0
    digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
    return Article(
        url=url,
        title=title,
        text=text,
        byline=parser.byline,
        published=parser.published,
        word_count=units,
        read_minutes=read_minutes,
        content_hash="sha1:" + digest,
        extractor=extractor,
    )