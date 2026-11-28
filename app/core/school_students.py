"""One file for the whole school: every row says which class the student is in.

Understood: an Excel or CSV file, the HTML-in-.xls export of the old school site, or pasted lines. The columns are found by their
headers (Class / Room id / الفصل / المجموعة, Name / اسم الطالب, English name); without headers each row is read as
"class, Arabic name, English spelling" in any order. Only the class, the name and the English spelling are ever read:
passwords, addresses and phone numbers in the same file are ignored and never kept."""
import csv
import io
import re
from html.parser import HTMLParser

from .errors import AppError
from .presets import GRADE_PRESET_BY_ID
from .students import _AR, _english_ok, _pick_name_from_row, clean_name

_CLASS_HEADS = {"room id", "class", "room", "الفصل", "المجموعة", "group", "classroom"}
_NAME_HEADS = {"name", "arabic", "arabic name", "الاسم", "اسم الطالب", "اسم الطالبة", "student", "student name"}
_EN_HEADS = {"english name", "english", "name_en", "name en", "الاسم بالانجليزي", "الاسم بالإنجليزي", "الاسم الانجليزي", "الاسم الإنجليزي"}


def room_key(label) -> tuple[str, str] | None:
    """(grade id, letter) of a class written the way people write it: g4-a, Grade 4 A, Grade4A, KG1 A, FS2 A, PRE-K. Else None."""
    s = " ".join(str(label or "").replace("_", " ").split()).lower()
    if not s:
        return None
    m = re.fullmatch(r"(kg[12]|g\d{1,2})-([a-h])", s)
    if m:
        return m[1], m[2]
    m = re.fullmatch(r"(?:grade|gr|g)\s*-?\s*(\d{1,2})\s*-?\s*([a-h])?", s)
    if m and f"g{m[1]}" in GRADE_PRESET_BY_ID:
        return f"g{int(m[1])}", m[2] or "a"
    m = re.fullmatch(r"(?:kg|fs|kindergarten|foundation stage)\s*-?\s*([12])\s*-?\s*([a-h])?", s)
    if m:
        return ("kg1" if m[1] == "1" else "kg2"), m[2] or "a"
    m = re.fullmatch(r"pre\s*-?\s*(?:k|kg)\s*-?\s*([a-h])?", s)        # pre-KG children sit with KG1
    if m:
        return "kg1", m[1] or "a"
    return None


class _Table(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split())); self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None


def rows_of(filename: str, raw: bytes, text: str) -> list[list[str]]:
    low = (filename or "").lower()
    if raw and low.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as e:
            raise AppError("file_unreadable", status=400) from e
        return [[("" if c is None else str(c)).strip() for c in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
    if raw:
        for enc in ("utf-8-sig", "utf-16", "cp1256"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeError:
                continue
        if raw.lstrip()[:1] == b"<" or text.lstrip()[:1] == "<":          # the old school site saves an HTML table as ".xls"
            t = _Table(); t.feed(text)
            return t.rows
        if low.endswith(".xls"):
            raise AppError("old_excel", "Old .xls files are not supported. Save as .xlsx.", status=400)
    rows = []
    for line in (text or "").splitlines():                               # each line picks its own separator
        if line.strip():
            d = "\t" if "\t" in line else ";" if ";" in line else ","
            rows.extend([c.strip() for c in r] for r in csv.reader([line], delimiter=d))
    return rows


def parse_school_rows(rows: list[list[str]]) -> list[tuple[str, str, str]]:
    """[(class label, Arabic name, English spelling or "")] in file order. Rows without a class or a name are dropped."""
    head = next((i for i, r in enumerate(rows[:6]) if any(c.strip().lower() in _NAME_HEADS for c in r) and any(c.strip().lower() in _CLASS_HEADS for c in r)), None)
    out = []
    if head is not None:
        cols = [c.strip().lower() for c in rows[head]]
        pick = lambda heads: next((i for i, c in enumerate(cols) if c in heads), None)
        ci, ni, ei = pick(_CLASS_HEADS), pick(_NAME_HEADS), pick(_EN_HEADS)
        # two class columns (Room id and Class): the one that is understood wins, row by row
        cis = [i for i, c in enumerate(cols) if c in _CLASS_HEADS]
        for r in rows[head + 1:]:
            cell = lambda i: r[i].strip() if i is not None and i < len(r) else ""
            label = next((cell(i) for i in cis if room_key(cell(i))), cell(ci))
            name, en = clean_name(cell(ni)), " ".join(cell(ei).split())
            if label and name:
                out.append((label, name, en if _english_ok(en) else ""))
        return out
    for r in rows:                                                       # no header: find the class cell, then the name and spelling
        cells = [c.strip() for c in r if c and c.strip()]
        k = next((i for i, c in enumerate(cells) if room_key(c)), None)
        if k is None:                                                    # a name with something next to it that is not a class: reported, not placed
            other = next((c for c in cells if not _AR.search(c)), "")
            if other and any(_AR.search(c) for c in cells):
                ar = next(c for c in cells if _AR.search(c))
                out.append((other, clean_name(ar), ""))
            continue
        rest = cells[:k] + cells[k + 1:]
        if not any(_AR.search(c) for c in rest):
            continue
        name, en = _pick_name_from_row(rest)
        if name:
            out.append((cells[k], name, en))
    return out


def group_by_room(items: list[tuple[str, str, str]]) -> tuple[dict, list[str]]:
    """({(grade id, letter): [(name, english)]}, labels that are not a class)"""
    groups: dict = {}
    unknown: list[str] = []
    for label, name, en in items:
        key = room_key(label)
        if key is None:
            if label not in unknown:
                unknown.append(label)
            continue
        groups.setdefault(key, []).append((name, en))
    return groups, unknown
