"""Checks on a file the teacher brings in, before anything reads it. A file is believed only when its first bytes match what its
name says (a .docx that is really an .exe is turned away), and a zip-based file (Word, PowerPoint, Excel) must not be a "zip bomb": a
tiny file that unpacks into gigabytes and freezes the computer when it is read."""
from __future__ import annotations

import io
import zipfile

from .errors import AppError

_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"          # the old .doc / .ppt / .xls container
_ZIP_EXT = (".docx", ".pptx", ".xlsx", ".xlsm")
MAX_ENTRIES = 10_000
MAX_UNPACKED = 600 * 1024 * 1024
MAX_PIXELS = 100_000_000                              # a 10000 x 10000 picture


def _bad(msg: str = "This file does not look like what its name says.") -> AppError:
    return AppError("file_suspicious", msg, status=400)


def _check_zip(raw: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
    except zipfile.BadZipFile as e:
        raise AppError("file_unreadable", "This file could not be read.", status=400) from e
    if len(infos) > MAX_ENTRIES:
        raise _bad("This file has too many parts.")
    total = sum(i.file_size for i in infos)
    if total > MAX_UNPACKED or (total > 50 * 1024 * 1024 and total > 100 * max(len(raw), 1)):
        raise _bad("This file would unpack into something far too big.")
    for i in infos:
        n = i.filename.replace("\\", "/")
        if n.startswith("/") or ".." in n.split("/"):
            raise _bad("This file has a part with an unsafe name.")


def check_document(name: str, raw: bytes) -> None:
    """Raise AppError when `raw` is not really the kind of file `name` claims (Word, PowerPoint, Excel, PDF, text, CSV)."""
    low = (name or "").lower()
    head = raw[:8]
    if low.endswith(_ZIP_EXT):
        if not head.startswith(_ZIP):
            raise _bad()
        _check_zip(raw)
    elif low.endswith(".pdf"):
        if b"%PDF-" not in raw[:1024]:
            raise _bad()
    elif low.endswith((".doc", ".ppt", ".xls")):
        if not head.startswith(_OLE):
            raise _bad()
    elif low.endswith((".txt", ".md", ".csv", ".tsv")):
        if b"\x00" in raw[:4096]:                    # text has no zero bytes: this is a program or a picture
            raise _bad()


def check_picture(raw: bytes) -> None:
    """Raise AppError when `raw` is not a picture of a sensible size (a small file can claim to be a huge picture and fill the memory)."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
    except Exception as e:
        raise AppError("image_unreadable", "This picture could not be read.", status=400) from e
    if w * h > MAX_PIXELS:
        raise AppError("image_too_big", "This picture is too large.", status=400)
