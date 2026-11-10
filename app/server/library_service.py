"""My files: everything the program made (Word, PowerPoint, Excel), in one list, and which of it is shared with students."""
from __future__ import annotations

import base64
import time

from ..core.errors import AppError

EXT = (".docx", ".pptx", ".xlsx", ".pdf")
# What can never go to students: it holds names, grades or the teacher's own planning.
PRIVATE = ("grading_sheet", "lesson_plan", "trimester_plan", "cover_sheet", "inspection_pack", "feedback", "report_card_comment")


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
        d.setdefault("shared", {})
        return d

    def _lib_file(self, rel: str):
        root = self._need_store().root.resolve()
        p = (root / str(rel)).resolve()
        if root not in p.parents or p.suffix.lower() not in EXT or not p.is_file():
            raise AppError("bad_value", "This file is not in your folder.", status=400)
        return p

    def library_list(self) -> dict:
        """Every file in one list. A file that is also a source for the AI carries its source card; sources with no file (web pages) come as 'orphans'."""
        root = self._need_store().root
        shared = self._lib()["shared"]
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
                                  "mtime": int(st.st_mtime), "size": st.st_size, "shared": shared.get(rel),
                                  "source": self._src_brief(src) if src else None, "source_locked": bool(src and src.get("made"))})
        items.sort(key=lambda x: -x["mtime"])
        orphans = [self._src_brief(x) for x in srcs if x["id"] not in used]
        orphans.sort(key=lambda x: x["added"], reverse=True)
        return {"items": items[:400], "orphans": orphans, "root": str(root)}

    def library_source(self, b: dict) -> dict:
        """Turn a file into a source for the AI (it is read once), or stop using it as one. Slides the app made are always sources."""
        rel = str(b.get("rel", ""))
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

    def library_share(self, b: dict) -> dict:
        """Put one file where students can see it. public=True: visible at once; False: added but hidden until approved."""
        rel = str(b.get("rel", ""))
        p = self._lib_file(rel)
        if _private(p.name):
            raise AppError("private_file", "This file has names, grades or your plans. It cannot be shared with students.", status=400)
        raw = p.read_bytes()
        kind = b.get("kind") if b.get("kind") in self.KINDS else _kind_of(p.name)
        title = " ".join(str(b.get("title") or p.stem.replace("_", " ")).split())[:120]
        before = {x["id"] for x in self.list_publications()["items"]}
        self.add_publication({"class_id": b.get("class_id"), "kind": kind, "title": title, "visible_from": b.get("visible_from"),
                              "visible_until": b.get("visible_until"), "file": {"filename": p.name, "data_b64": base64.b64encode(raw).decode()}})
        new = [x for x in self.list_publications()["items"] if x["id"] not in before]
        if not new:
            raise AppError("cloud_error", "Could not share the file. Try again.", status=502)
        pid = new[0]["id"]
        if b.get("public"):
            self.set_publication(pid, {"approved": True})
        lib = self._lib()
        lib["shared"][rel] = {"id": pid, "class_id": str(b.get("class_id")), "public": bool(b.get("public")), "at": int(time.time())}
        self._need_store().write_json(self._lib_path(), lib)
        return self.library_list()

    def library_set_public(self, b: dict) -> dict:
        rel = str(b.get("rel", ""))
        lib = self._lib()
        s = lib["shared"].get(rel)
        if not s:
            raise AppError("bad_value", "This file is not shared.", status=400)
        self.set_publication(s["id"], {"approved": bool(b.get("public"))})
        s["public"] = bool(b.get("public"))
        self._need_store().write_json(self._lib_path(), lib)
        return self.library_list()

    def library_unshare(self, b: dict) -> dict:
        rel = str(b.get("rel", ""))
        lib = self._lib()
        s = lib["shared"].pop(rel, None)
        if s:
            try:
                self.delete_publication(s["id"])
            finally:
                self._need_store().write_json(self._lib_path(), lib)
        return self.library_list()
