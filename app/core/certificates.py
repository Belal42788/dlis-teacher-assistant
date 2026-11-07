"""Certificates and thank-you cards as a Word file, with the school logo. Pure local work: names are only written into the file."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import paths
from .documents import _clean, _save

# Wording is neutral for boys and girls in Arabic (no "his/her"), so one text fits every student.
OCCASIONS = {
    "excellence": {"en": ("Certificate of Excellence", "in recognition of outstanding achievement in {subject}"),
                   "ar": ("شهادة تفوّق", "تقديرًا للتفوّق الدراسي في مادة {subject}")},
    "improvement": {"en": ("Most Improved Student", "in recognition of great progress and hard work in {subject}"),
                    "ar": ("شهادة تحسّن ملحوظ", "تقديرًا للتقدّم الملحوظ والجهد المبذول في مادة {subject}")},
    "behavior": {"en": ("Certificate of Good Behaviour", "in recognition of excellent behaviour and respect towards others"),
                 "ar": ("شهادة سلوك مثالي", "تقديرًا للسلوك المثالي والاحترام تجاه الآخرين")},
    "participation": {"en": ("Certificate of Participation", "in recognition of active participation in class"),
                      "ar": ("شهادة مشاركة", "تقديرًا للمشاركة الفعّالة داخل الفصل")},
    "attendance": {"en": ("Perfect Attendance", "in recognition of excellent attendance and punctuality"),
                   "ar": ("شهادة مواظبة", "تقديرًا للمواظبة والانضباط في الحضور")},
    "thanks": {"en": ("Thank You", "with sincere thanks for your effort and kindness"),
               "ar": ("شكر وتقدير", "مع خالص الشكر والتقدير على الجهد والتعاون")},
    "custom": {"en": ("", ""), "ar": ("", "")},
}
PRESENT = {"en": "This certificate is proudly presented to", "ar": "تُمنح هذه الشهادة إلى"}
CARD_TO = {"en": "To", "ar": "إلى"}
DATE_LABEL = {"en": "Date", "ar": "التاريخ"}
TEACHER_LABEL = {"en": "Teacher", "ar": "المعلّم"}
BLUE, DARK, GOLD = RGBColor(0x2F, 0x82, 0xA8), RGBColor(0x2A, 0x2A, 0x72), "C9A227"
ARABIC = re.compile(r"[؀-ۿ]")


def wording(occasion: str, lang: str, subject: str, title: str = "", text: str = "") -> tuple[str, str]:
    lang = "ar" if lang == "ar" else "en"
    t, body = OCCASIONS.get(occasion, OCCASIONS["custom"])[lang]
    t = _clean(title) or t
    body = _clean(text) or body.format(subject=_clean(subject) or ("المادة" if lang == "ar" else "this subject"))
    return t, body


def _font(run, size, bold=False, color=None, ar=False):
    run.font.size = Pt(size); run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts"); rpr.insert(0, fonts)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(a), "Arial" if ar else "Georgia")
    if ar:
        rpr.append(OxmlElement("w:rtl"))
        if bold:
            rpr.append(OxmlElement("w:bCs"))
        sz = OxmlElement("w:szCs"); sz.set(qn("w:val"), str(int(size * 2))); rpr.append(sz)


def _line(container, text, size, bold=False, color=None, after=6, before=0, lang="en", underline=False):
    p = container.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(after); p.paragraph_format.space_before = Pt(before)
    ar = bool(ARABIC.search(text)) or lang == "ar"
    if ar:
        p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    r = p.add_run(text)
    _font(r, size, bold, color, ar)
    if underline:
        pr = p._p.get_or_add_pPr(); b = OxmlElement("w:pBdr"); bt = OxmlElement("w:bottom")
        for k, v in (("val", "single"), ("sz", "8"), ("space", "2"), ("color", GOLD)):
            bt.set(qn(f"w:{k}"), v)
        b.append(bt); pr.append(b)
    return p


def _logo(container, logo, height):
    if logo and Path(logo).is_file():
        p = container.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        p.add_run().add_picture(str(logo), height=Pt(height))


def _page_border(section, color=GOLD):
    pg = OxmlElement("w:pgBorders"); pg.set(qn("w:offsetFrom"), "page")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        for k, v in (("val", "double"), ("sz", "18"), ("space", "24"), ("color", color)):
            e.set(qn(f"w:{k}"), v)
        pg.append(e)
    section._sectPr.append(pg)


def _no_borders(table):
    tbl = table._tbl; pr = tbl.tblPr; b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}"); e.set(qn("w:val"), "nil"); b.append(e)
    pr.append(b)


def _cell_border(cell, color, size="6", dashed=False):
    pr = cell._tc.get_or_add_tcPr(); b = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        for k, v in (("val", "dashed" if dashed else "single"), ("sz", size), ("space", "0"), ("color", color)):
            e.set(qn(f"w:{k}"), v)
        b.append(e)
    pr.append(b)


def _signature_row(doc, lang, when, teacher):
    t = doc.add_table(rows=1, cols=2); _no_borders(t); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, (label, value) in zip(t.rows[0].cells, ((DATE_LABEL[lang], when), (TEACHER_LABEL[lang], teacher))):
        c.paragraphs[0]._p.getparent().remove(c.paragraphs[0]._p)
        _line(c, "", 6, after=14)
        _line(c, f"{label}: {value}" if value else label, 13, color=DARK, lang=lang)
        pr = c.paragraphs[-1]._p.get_or_add_pPr(); b = OxmlElement("w:pBdr"); tp = OxmlElement("w:top")
        for k, v in (("val", "single"), ("sz", "6"), ("space", "4"), ("color", "8A94A6")):
            tp.set(qn(f"w:{k}"), v)
        b.append(tp); pr.append(b)


def write_certificates(out: Path, names: list[str], *, occasion: str = "excellence", lang: str = "en", kind: str = "certificate",
                       subject: str = "", title: str = "", text: str = "", school: str = "", teacher: str = "", when: str = "",
                       logo: Path | None = None) -> Path:
    """kind 'certificate': one landscape A4 page per student.  kind 'card': four small thank-you cards per page to cut out."""
    names = [_clean(n) for n in names if _clean(n)]
    if not names:
        from .errors import AppError
        raise AppError("no_names", "Add at least one name.", status=409)
    lang = "ar" if lang == "ar" else "en"
    head, body = wording(occasion, lang, subject, title, text)
    school, teacher, when = _clean(school), _clean(teacher), _clean(when)
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE; sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    st = doc.styles["Normal"]; st.font.size = Pt(12)
    if kind == "card":
        sec.left_margin = sec.right_margin = Cm(1.2); sec.top_margin = sec.bottom_margin = Cm(1.0)
        for i in range(0, len(names), 4):
            if i:
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            chunk = names[i:i + 4]
            tbl = doc.add_table(rows=2, cols=2); tbl.alignment = WD_TABLE_ALIGNMENT.CENTER; _no_borders(tbl)
            for k in range(4):
                cell = tbl.cell(k // 2, k % 2)
                cell.width = Cm(13.6)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                cell.paragraphs[0]._p.getparent().remove(cell.paragraphs[0]._p)
                _cell_border(cell, GOLD, "12", dashed=False)
                if k >= len(chunk):
                    _line(cell, "", 12, after=130)
                    continue
                _logo(cell, logo, 42)
                _line(cell, head, 24, True, DARK, after=8, before=4, lang=lang)
                _line(cell, f"{CARD_TO[lang]}:", 12, color=BLUE, after=0, lang=lang)
                _line(cell, chunk[k], 20, True, BLUE, after=8, lang=lang, underline=True)
                _line(cell, body, 13, color=DARK, after=14, lang=lang)
                _line(cell, " · ".join(x for x in (teacher, when) if x), 11, color=RGBColor(0x56, 0x60, 0x83), after=4, lang=lang)
            for r in tbl.rows:
                r.height = Cm(9.2)
    else:
        sec.left_margin = sec.right_margin = Cm(2.2); sec.top_margin = sec.bottom_margin = Cm(1.6)
        _page_border(sec)
        for i, name in enumerate(names):
            first = _line(doc, "", 10, after=14)
            first.paragraph_format.page_break_before = bool(i)   # a new page per student, with no empty page between
            _logo(doc, logo, 78)
            if school:
                _line(doc, school, 15, False, BLUE, after=22, lang=lang)
            _line(doc, head, 40, True, DARK, after=26, lang=lang)
            _line(doc, PRESENT[lang], 16, color=RGBColor(0x44, 0x4A, 0x6E), after=16, lang=lang)
            _line(doc, name, 38, True, BLUE, after=20, lang=lang, underline=True)
            _line(doc, body, 19, color=DARK, after=70, lang=lang)
            _signature_row(doc, lang, when, teacher)
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out
