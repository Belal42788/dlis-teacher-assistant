"""Turn whatever the teacher pastes or uploads (Excel, CSV, a list) into clean student names."""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable

from .errors import AppError

_HEADER_WORDS = {"name", "names", "student", "student name", "students", "full name",
                 "الاسم", "اسم الطالب", "الطالب", "الطلاب", "اسم", "اسم الطالبة"}
_NUMBERISH = re.compile(r"^[\s\d\.\-\)\(#:،,]+$")
_LEADING_NUM = re.compile(r"^\s*\d+\s*[\.\)\-:،]\s*")


def clean_name(raw: str) -> str:
    name = _LEADING_NUM.sub("", str(raw or "")).strip()
    return re.sub(r"\s+", " ", name)


def _pick_name_from_row(cells: list[str]) -> str:
    cells = [c.strip() for c in cells if c is not None and str(c).strip()]
    # first cell that is not just a number (row numbers / ids) and contains letters
    for c in cells:
        if not _NUMBERISH.match(c):
            return clean_name(c)
    return ""


def parse_rows(rows: Iterable[list[str]]) -> dict:
    names: list[str] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    skipped = 0
    first = True
    for row in rows:
        name = _pick_name_from_row([str(c) if c is not None else "" for c in row])
        if first:
            first = False
            if name.lower() in _HEADER_WORDS:
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
    return {"names": names, "duplicates": duplicates, "skipped": skipped}


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
        rows.append(re.split(r"\t|;", ln) if ("\t" in ln or ";" in ln) else [ln])
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
