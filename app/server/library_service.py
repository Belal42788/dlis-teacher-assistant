"""My files: everything the program made (Word, PowerPoint, Excel), in one list, and which of it is shared with students."""
from __future__ import annotations

import base64
import re
import time
import uuid

from ..core.errors import AppError

EXT = (".docx", ".pptx", ".xlsx", ".pdf")
# What can never go to students: it holds names, grades or the teacher's own planning.
PRIVATE = ("grading_sheet", "lesson_plan", "trimester_plan", "cover_sheet", "inspection_pack", "feedback", "report_card_comment")


def _auto_week(name: str):
    """Files the program made are named T1-W08_...: that is trimester 0, week 8."""
    m = re.match(r"T([1-3])-W(\d{1,2})_", name)
    return (int(m.group(1)) - 1, int(m.group(2))) if m else (None, None)


def _auto_place(name: str) -> dict:
    t, w = _auto_week(name)
    return {"id": "auto", "t": t, "w": w, "note": "", "shared": None}


def _kind_of(name: str) -> str:
    n = name.lower()
    if n.endswith(".pptx"):
        return "presentation"
    if "quiz" in n:
        return "quiz"
    if "revision" in n:
        return "revision"
    return "other"


def _private(name: str) -> bool:
    n = name.lower().replace(" ", "_")
    return any(p in n for p in PRIVATE)


class LibraryMixin:
    def _lib_path(self):
        return self._need_store().root / "library.json"

    def _lib(self) -> dict:
        d = self._need_store().read_json(self._lib_path(), {}, check=lambda x: isinstance(x, dict) or (_ for _ in ()).throw(ValueError("bad"))) or {}
        d.setdefault("files", {})
        legacy = d.pop("shared", None) or {}   # older versions kept one share per file
        for rel, sh in legacy.items():
            d["files"].setdefault(rel, [{"id": uuid.uuid4().hex[:8], "t": None, "w": None, "note": "", "shared": sh}])
        if legacy:
            self._need_store().write_json(self._lib_path(), d)
        return d

    def _save_lib(self, lib: dict) -> None:
        self._need_store().write_json(self._lib_path(), lib)

    def _places(self, lib: dict, rel: str) -> list:
        return lib["files"].get(rel) or [_auto_place(rel.rsplit("/", 1)[-1])]

    def _place(self, lib: dict, rel: str, pid: str, make: bool = True) -> dict:
        """One placement of a file (a file can sit in several weeks). The automatic one is saved the first time it is changed."""
        rows = lib["files"].get(rel)
        if rows is None:
            rows = lib["files"][rel] = [_auto_place(rel.rsplit("/", 1)[-1])]
            rows[0]["id"] = uuid.uuid4().hex[:8]
            if pid == "auto":
                pid = rows[0]["id"]
        if not pid:
            return rows[0]
        p = next((x for x in rows if x["id"] == pid), None)
        if not p:
            raise AppError("bad_value", "This file is not in that week.", status=400)
        return p

    def _lib_file(self, rel: str):
        root = self._need_store().root.resolve()
        p = (root / str(rel)).resolve()
        if root not in p.parents or p.suffix.lower() not in EXT or not p.is_file():
            raise AppError("bad_value", "This file is not in your folder.", status=400)
        return p

    def library_list(self) -> dict:
        """Every file in one list. A file that is also a source for the AI carries its source card; sources with no file (web pages) come as 'orphans'."""
        root = self._need_store().root
        lib = self._lib()
        self._sync_made_decks()
        srcs = self._srcs()
        by_id = {x["id"]: x for x in srcs}
        by_rel = {x["file_rel"]: x for x in srcs if x.get("file_rel")}
        items, used = [], set()
        for sub in ("Documents", "Slides", "Books"):
            base = root / sub
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in EXT and not p.name.startswith("~"):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    st = p.stat()
                    src = by_rel.get(rel) or by_id.get(self._made_id(p))
                    if src:
                        used.add(src["id"])
                    items.append({"rel": rel, "name": p.name, "folder": p.parent.name, "kind": "book" if sub == "Books" else _kind_of(p.name), "private": _private(p.name),
                                  "mtime": int(st.st_mtime), "size": st.st_size, "places": self._places(lib, rel),
                                  "source": self._src_brief(src) if src else None, "source_locked": bool(src and src.get("made"))})
        items.sort(key=lambda x: -x["mtime"])
        orphans = [self._src_brief(x) for x in srcs if x["id"] not in used]
        orphans.sort(key=lambda x: x["added"], reverse=True)
        return {"items": items[:400], "orphans": orphans, "root": str(root)}

    def library_source(self, b: dict) -> dict:
        """Turn a file into a source for the AI (it is read once), or stop using it as one. Slides the app made are always sources."""
        rel = str(b.get("rel", "")).replace("\\", "/")
        p = self._lib_file(rel)
        cur = next((x for x in self._srcs() if x.get("file_rel") == rel or x["id"] == self._made_id(p)), None)
        if b.get("on"):
            if not cur:
                self._import_bytes(p.name, p.read_bytes(), file_rel=rel)
        elif cur:
            if cur.get("made"):
                raise AppError("bad_value", "Slides made by the app are always sources.", status=400)
            self.delete_source(cur["id"])
        return self.library_list()

    def _week_fields(self, p: dict) -> dict:
        return {"note": p.get("note", ""), "trimester": p.get("t"), "week": p.get("w")}

    def library_share(self, b: dict) -> dict:
        """Put one placement of a file (the file, for that week, with its note) where students can see it. public=True: visible at once; False: hidden until approved."""
        rel = str(b.get("rel", "")).replace("\\", "/")
        f = self._lib_file(rel)
        if _private(f.name):
            raise AppError("private_file", "This file has names, grades or your plans. It cannot be shared with students.", status=400)
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        if place.get("shared"):
            raise AppError("bad_value", "This is already shared.", status=400)
        raw = f.read_bytes()
        kind = b.get("kind") if b.get("kind") in self.KINDS else _kind_of(f.name)
        title = " ".join(str(b.get("title") or f.stem.replace("_", " ")).split())[:120]
        before = {x["id"] for x in self.list_publications()["items"]}
        self.add_publication({"class_id": b.get("class_id"), "kind": kind, "title": title, "visible_from": b.get("visible_from"),
                              "visible_until": b.get("visible_until"), **self._week_fields(place),
                              "file": {"filename": f.name, "data_b64": base64.b64encode(raw).decode()}})
        new = [x for x in self.list_publications()["items"] if x["id"] not in before]
        if not new:
            raise AppError("cloud_error", "Could not share the file. Try again.", status=502)
        cid = new[0]["id"]
        if b.get("public"):
            self.set_publication(cid, {"approved": True})
        place["shared"] = {"id": cid, "class_id": str(b.get("class_id")), "public": bool(b.get("public")), "at": int(time.time())}
        self._save_lib(lib)
        return self.library_list()

    def library_set_public(self, b: dict) -> dict:
        rel = str(b.get("rel", "")).replace("\\", "/")
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        s = place.get("shared")
        if not s:
            raise AppError("bad_value", "This file is not shared.", status=400)
        self.set_publication(s["id"], {"approved": bool(b.get("public"))})
        s["public"] = bool(b.get("public"))
        self._save_lib(lib)
        return self.library_list()

    def library_unshare(self, b: dict) -> dict:
        rel = str(b.get("rel", "")).replace("\\", "/")
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        s = place.pop("shared", None)
        if s:
            try:
                self.delete_publication(s["id"])
            finally:
                place["shared"] = None
                self._save_lib(lib)
        return self.library_list()

    def library_place(self, b: dict) -> dict:
        """Change a placement: which week it belongs to (t and w both, or both empty for 'no week') and/or its note for the students."""
        rel = str(b.get("rel", "")).replace("\\", "/")
        self._lib_file(rel)
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        if "w" in b or "t" in b:
            t, w = b.get("t"), b.get("w")
            if (t is None) != (w is None) or (t is not None and not (isinstance(t, int) and isinstance(w, int) and 0 <= t <= 2 and 1 <= w <= 60)):
                raise AppError("bad_value", "Choose the week.", status=400)
            place["t"], place["w"] = t, w
        if "note" in b:
            place["note"] = " ".join(str(b.get("note") or "").split())[:300]
        self._save_lib(lib)
        if place.get("shared"):   # the students see the same week and note
            self.set_publication(place["shared"]["id"], self._week_fields(place))
        return self.library_list()

    def library_place_add(self, b: dict) -> dict:
        """Use the same file in one more week (half of the slides in week 1, the other half in week 2), with its own note."""
        rel = str(b.get("rel", "")).replace("\\", "/")
        self._lib_file(rel)
        lib = self._lib()
        self._place(lib, rel, "")   # keeps the automatic one
        t, w = b.get("t"), b.get("w")
        if (t is None) != (w is None) or (t is not None and not (isinstance(t, int) and isinstance(w, int) and 0 <= t <= 2 and 1 <= w <= 60)):
            raise AppError("bad_value", "Choose the week.", status=400)
        if any(x["t"] == t and x["w"] == w for x in lib["files"][rel]):
            raise AppError("bad_value", "The file is already in that week.", status=400)
        lib["files"][rel].append({"id": uuid.uuid4().hex[:8], "t": t, "w": w, "note": "", "shared": None})
        self._save_lib(lib)
        return self.library_list()

    def library_place_delete(self, b: dict) -> dict:
        """Take the file out of one week (and away from the students for that week). A file always keeps one place, even if it is 'no week'."""
        rel = str(b.get("rel", "")).replace("\\", "/")
        self._lib_file(rel)
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        rows = lib["files"][rel]
        try:
            if place.get("shared"):
                self.delete_publication(place["shared"]["id"])
        finally:
            rows.remove(place)
            if not rows:
                rows.append({"id": uuid.uuid4().hex[:8], "t": None, "w": None, "note": "", "shared": None})
            self._save_lib(lib)
        return self.library_list()
