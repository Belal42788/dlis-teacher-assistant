"""Turn whatever the teacher pastes or uploads (Excel, CSV, a list) into clean student names."""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable

from .errors import AppError

_HEADER_WORDS = {"name", "names", "student", "student name", "students", "full name",
                 "الاسم", "اسم الطالب", "الطالب", "الطلاب", "اسم", "اسم الطالبة",
                 "english", "english name", "arabic", "arabic name", "class", "room id", "active", "الفصل", "الاسم بالإنجليزي"}
_AR = re.compile(r"[\u0600-\u06FF]")
_LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")
_NUMBERISH = re.compile(r"^[\s\d\.\-\)\(#:،,]+$")
_LEADING_NUM = re.compile(r"^\s*\d+\s*[\.\)\-:،]\s*")


def clean_name(raw: str) -> str:
    name = _LEADING_NUM.sub("", str(raw or "")).strip()
    return re.sub(r"\s+", " ", name)


def _english_ok(c: str) -> bool:
    """An English spelling of a full name: letters only and at least two words (so "Female" or "Grade9 A" are never taken for one)."""
    return bool(_LATIN_NAME.match(c)) and len(c.split()) >= 2


def _split_mixed(cell: str):
    """One cell holding both ("ملك اشرف Malak Ashraf" or the other way round): the Arabic words and the Latin words, each at least two."""
    words = cell.replace("|", " ").replace("/", " ").replace(" - ", " ").split()
    ar = [w for w in words if _AR.search(w)]
    en = [w for w in words if not _AR.search(w) and re.match(r"^[A-Za-z.'\-]+$", w)]
    if len(ar) >= 2 and len(en) >= 2 and len(ar) + len(en) == len(words):
        return " ".join(ar), " ".join(en)
    return None


def _pick_name_from_row(cells: list[str]) -> tuple[str, str]:
    """(name, English spelling or ""). The name is the first cell with Arabic letters, else the first cell that is not just a number.
    The English spelling is the cell next to the Arabic one (or the same cell, when both are written together)."""
    cells = [c.strip() for c in cells if c is not None and str(c).strip()]
    for i, c in enumerate(cells):
        if _AR.search(c):
            mixed = _split_mixed(c)
            if mixed:
                return clean_name(mixed[0]), clean_name(mixed[1])
            for j in (i + 1, i - 1):
                if 0 <= j < len(cells) and _english_ok(cells[j]):
                    return clean_name(c), clean_name(cells[j])
            return clean_name(c), ""
    for c in cells:
        if not _NUMBERISH.match(c):
            return clean_name(c), ""
    return "", ""


def parse_rows(rows: Iterable[list[str]]) -> dict:
    names: list[str] = []
    english: list[str] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    skipped = 0
    first = True
    for row in rows:
        cells = [str(c) if c is not None else "" for c in row]
        name, en = _pick_name_from_row(cells)
        if first:
            first = False
            if name.lower() in _HEADER_WORDS or any(c.strip().lower() in _HEADER_WORDS for c in cells):
                continue
        if not name:
            skipped += 1 if any(str(c).strip() for c in row) else 0
            continue
        key = name.casefold()
        if key in seen:
            duplicates.append(name)
            continue
        seen[key] = 1
        names.append(name)
        english.append(en)
    return {"names": names, "english": english, "duplicates": duplicates, "skipped": skipped}


_GENDER = {"ذكر", "أنثى", "انثى", "male", "female", "m", "f"}
_ID_LINE = re.compile(r"^\s*\d{2,}\s*$")


def _school_system_blocks(lines: list[str]) -> list[str]:
    """The school system exports one student per block: ID, name, gender, ****, stage, grade, class, address, phone.
    Returns the names, or [] if the text does not look like that."""
    clean = [ln.strip() for ln in lines]
    names = []
    i = 0
    while i < len(clean) - 2:
        if _ID_LINE.match(clean[i]) and clean[i + 1] and not _NUMBERISH.match(clean[i + 1]) and clean[i + 2].casefold() in _GENDER:
            names.append(clean[i + 1])
            i += 3
        else:
            i += 1
    return names


def parse_text(text: str) -> dict:
    lines = [ln for ln in str(text or "").replace("\r", "").split("\n")]
    blocks = _school_system_blocks([ln for ln in lines if ln.strip()])
    if blocks:
        return parse_rows([[n] for n in blocks])
    rows = []
    for ln in lines:
        if not ln.strip():
            continue
        rows.append(re.split(r"\t|;", ln) if ("\t" in ln or ";" in ln) else re.split(r",", ln) if (_AR.search(ln) and re.search(r",\s*[A-Za-z]", ln)) else [ln])
    return parse_rows(rows)


def parse_file(filename: str, data: bytes) -> dict:
    low = (filename or "").lower()
    if low.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
        except ImportError as e:  # pragma: no cover
            raise AppError("excel_unavailable", "Excel support is not installed") from e
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:
            raise AppError("file_unreadable", f"Could not read the Excel file: {e}") from e
        ws = wb.worksheets[0]
        rows = [["" if c is None else str(c) for c in r] for r in ws.iter_rows(values_only=True)]
        return parse_rows(rows)
    if low.endswith(".xls"):
        raise AppError("old_excel", "Old .xls files are not supported. Save as .xlsx or paste the names.")
    text = None
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AppError("file_unreadable", "Could not read the file")
    if low.endswith(".csv"):
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
        except csv.Error:
            pass
        return parse_rows(list(csv.reader(io.StringIO(text), dialect)))
    return parse_text(text)
