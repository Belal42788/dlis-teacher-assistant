"""My files: everything the program made (Word, PowerPoint, Excel), in one list, and which of it is shared with students."""
from __future__ import annotations

import base64
import re
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
        root = self._need_store().root
        shared = self._lib()["shared"]
        items = []
        for sub in ("Documents", "Slides"):
            base = root / sub
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in EXT and not p.name.startswith("~"):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    st = p.stat()
                    items.append({"rel": rel, "name": p.name, "folder": p.parent.name, "kind": _kind_of(p.name), "private": _private(p.name),
                                  "mtime": int(st.st_mtime), "size": st.st_size, "shared": shared.get(rel)})
        items.sort(key=lambda x: -x["mtime"])
        return {"items": items[:400], "root": str(root)}

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
