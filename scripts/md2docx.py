# -*- coding: utf-8 -*-
"""Markdown -> DOCX converter (subset: headings, tables, code fences, lists, quotes, bold, inline code, links)."""
import re
import sys
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

CN_FONT = "Microsoft YaHei"
EN_FONT = "Segoe UI"
CODE_FONT = "Consolas"
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)


def set_run_font(run, name, size=None, bold=None, color=None, ea=CN_FONT):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), ea)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade(paragraph, fill):
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def cell_shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def add_inline(paragraph, text, size=10.0, base_bold=False):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            r = paragraph.add_run(part[2:-2])
            set_run_font(r, EN_FONT, size, bold=True)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            r = paragraph.add_run(part[1:-1])
            set_run_font(r, CODE_FONT, size - 0.5, color=RGBColor(0xA3, 0x15, 0x15))
        elif part.startswith("[") and "](" in part:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            label, url = m.group(1), m.group(2)
            r = paragraph.add_run(label)
            set_run_font(r, EN_FONT, size, color=RGBColor(0x0B, 0x57, 0xD0))
            if url not in label:
                r2 = paragraph.add_run(f" ({url})")
                set_run_font(r2, EN_FONT, size - 1, color=RGBColor(0x66, 0x66, 0x66))
        else:
            r = paragraph.add_run(part)
            set_run_font(r, EN_FONT, size, bold=base_bold)


def add_code_block(doc, lines):
    if not lines:
        lines = [""]
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(3)
    pf.space_after = Pt(8)
    pf.left_indent = Cm(0.15)
    pf.line_spacing = 1.0
    pf.keep_together = True
    shade(p, "F4F5F7")
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        r = p.add_run(line.rstrip())
        set_run_font(r, CODE_FONT, 8.2, ea=CN_FONT)


def add_hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    ppr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "CCCCCC")
    pbdr.append(bottom)
    ppr.append(pbdr)


def _clean_len(txt):
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)
    txt = txt.replace("**", "").replace("`", "")
    w = 0
    for ch in txt:
        w += 2 if ord(ch) > 0x2E80 else 1
    return w


def _fit_columns(table, rows, total_cm=16.2):
    cols = len(rows[0])
    weights = []
    for i in range(cols):
        vals = [_clean_len(r[i]) if i < len(r) else 0 for r in rows]
        avg = sum(vals) / max(1, len(vals))
        weights.append(max(5.0, min(26.0, avg)))
    s = sum(weights)
    table.autofit = False
    for i, w in enumerate(weights):
        cm = max(1.7, w / s * total_cm)
        for row in table.rows:
            row.cells[i].width = Cm(cm)


def _repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trpr.append(el)


def add_table(doc, rows):
    header, body = rows[0], rows[1:]
    cols = len(header)
    t = doc.add_table(rows=1, cols=cols)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    hdr = t.rows[0].cells
    for i, txt in enumerate(header):
        hdr[i].text = ""
        para = hdr[i].paragraphs[0]
        para.paragraph_format.space_after = Pt(1)
        add_inline(para, txt, size=9.0, base_bold=True)
        cell_shade(hdr[i], "E8EEF6")
    for row in body:
        cells = t.add_row().cells
        for i in range(cols):
            txt = row[i] if i < len(row) else ""
            cells[i].text = ""
            para = cells[i].paragraphs[0]
            para.paragraph_format.space_after = Pt(1)
            add_inline(para, txt, size=9.0)
    _fit_columns(t, rows)
    _repeat_header(t.rows[0])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run("干净搜索聚合器 · 构建方案 v1.0    —  ")
    set_run_font(r1, EN_FONT, 8, color=RGBColor(0x88, 0x88, 0x88))

    def field(name):
        run = p.add_run()
        set_run_font(run, EN_FONT, 8, color=RGBColor(0x88, 0x88, 0x88))
        b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin")
        i = OxmlElement("w:instrText"); i.set(qn("xml:space"), "preserve"); i.text = name
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end")
        run._r.append(b); run._r.append(i); run._r.append(e)

    field("PAGE")
    r2 = p.add_run(" / ")
    set_run_font(r2, EN_FONT, 8, color=RGBColor(0x88, 0x88, 0x88))
    field("NUMPAGES")


def parse_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_sep(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def convert(md_path, docx_path):
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = EN_FONT
    normal.font.size = Pt(10)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    normal.paragraph_format.widow_control = True

    add_footer(sec)

    for lvl, size in ((1, 19), (2, 14.5), (3, 12), (4, 10.5)):
        st = doc.styles[f"Heading {lvl}"]
        st.font.name = EN_FONT
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = ACCENT
        st.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

    i = 0
    n = len(lines)
    in_code = False
    code_buf = []
    table_buf = []

    def flush_table():
        nonlocal table_buf
        if table_buf:
            add_table(doc, table_buf)
            table_buf = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                add_code_block(doc, code_buf)
                code_buf = []
                in_code = False
            else:
                flush_table()
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and is_sep(lines[i + 1]):
            table_buf.append(parse_table_row(line))
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                table_buf.append(parse_table_row(lines[i]))
                i += 1
            continue

        if table_buf:
            flush_table()

        if not stripped:
            i += 1
            continue

        if re.match(r"^-{3,}$", stripped):
            add_hr(doc)
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            p = doc.add_paragraph(style=f"Heading {lvl}")
            p.paragraph_format.space_before = Pt(14 if lvl <= 2 else 10)
            p.paragraph_format.space_after = Pt(5)
            p.paragraph_format.keep_with_next = True
            add_inline(p, m.group(2), size={1: 19, 2: 14.5, 3: 12, 4: 10.5}[lvl], base_bold=True)
            i += 1
            continue

        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.5)
            p.paragraph_format.space_after = Pt(6)
            add_inline(p, " ".join(x for x in buf if x), size=9.5)
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x44, 0x4A, 0x52)
                r.font.italic = True
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            style = "List Bullet 2" if indent >= 2 else "List Bullet"
            p = doc.add_paragraph(style=style)
            p.paragraph_format.space_after = Pt(2)
            add_inline(p, m.group(2), size=10)
            i += 1
            continue

        m = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            style = "List Number 2" if indent >= 2 else "List Number"
            p = doc.add_paragraph(style=style)
            p.paragraph_format.space_after = Pt(2)
            add_inline(p, m.group(2), size=10)
            i += 1
            continue

        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.32
        add_inline(p, stripped, size=10)
        i += 1

    if in_code:
        add_code_block(doc, code_buf)
    flush_table()

    cp = doc.core_properties
    cp.title = "干净搜索聚合器 · 构建方案"
    cp.subject = "CleanSearch 构建方案 v1.0"
    cp.author = "YG"
    doc.save(docx_path)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
    print("OK", sys.argv[2])
