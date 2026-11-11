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
        d.setdefault("links", {})   # web links (a video, a playlist, a site): {id: {title, url, added}}
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

    def _place(self, lib: dict, rel: str, pid: str) -> dict:
        """One placement of a file (a file can sit in several weeks). The automatic one is saved the first time it is changed."""
        rows = lib["files"].get(rel)
        if rows is None:
            rows = lib["files"][rel] = [_auto_place(rel.rsplit("/", 1)[-1])]
            rows[0]["id"] = uuid.uuid4().hex[:8]
            if pid == "auto":
                pid = rows[0]["id"]
        if not pid or pid == "auto":   # "auto": the automatic one, which is the first once it has been saved
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

    @staticmethod
    def _rel(b: dict) -> str:
        return str(b.get("rel", "")).replace("\\", "/")

    def _item(self, lib: dict, rel: str) -> dict:
        """The thing a placement points at: a file in the folder, or a saved web link."""
        if rel.startswith("link:"):
            link = lib["links"].get(rel[5:])
            if not link:
                raise AppError("bad_value", "This link is not in your list.", status=400)
            return {"name": link["title"], "path": None, "url": link["url"], "link_id": rel[5:]}
        p = self._lib_file(rel)
        return {"name": p.name, "path": p, "url": None, "link_id": ""}

    def _adopt_old_url_sources(self, lib: dict) -> None:
        """Web pages added as sources before links were part of My files become links, so they can be put in a week and shared."""
        changed = False
        for src in self._srcs():
            if src.get("url") and not src.get("file_rel") and not src.get("link_id") and not src.get("made"):
                lid = uuid.uuid4().hex[:8]
                lib["links"][lid] = {"title": src.get("name") or src["url"], "url": src["url"], "added": int(time.time())}
                src["link_id"] = lid
                self._src_save(src)
                changed = True
        if changed:
            self._save_lib(lib)

    def library_list(self) -> dict:
        """Every file in one list. A file that is also a source for the AI carries its source card; sources with no file (web pages) come as 'orphans'."""
        root = self._need_store().root
        lib = self._lib()
        self._sync_made_decks()
        self._adopt_old_url_sources(lib)
        srcs = self._srcs()
        by_id = {x["id"]: x for x in srcs}
        by_rel = {x["file_rel"]: x for x in srcs if x.get("file_rel")}
        by_link = {x["link_id"]: x for x in srcs if x.get("link_id")}
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
        for lid, link in lib["links"].items():
            src = by_link.get(lid)
            if src:
                used.add(src["id"])
            items.append({"rel": f"link:{lid}", "name": link["title"], "url": link["url"], "folder": "", "kind": "link", "private": False, "mtime": link.get("added", 0), "size": 0,
                          "places": self._places(lib, f"link:{lid}"), "source": self._src_brief(src) if src else None, "source_locked": False})
        items.sort(key=lambda x: -x["mtime"])
        orphans = [self._src_brief(x) for x in srcs if x["id"] not in used]
        orphans.sort(key=lambda x: x["added"], reverse=True)
        return {"items": items[:400], "orphans": orphans, "root": str(root)}

    def library_source(self, b: dict) -> dict:
        """Turn a file or a link into a source for the AI (it is read once), or stop using it as one. Slides the app made are always sources."""
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        srcs = self._srcs()
        if it["link_id"]:
            cur = next((x for x in srcs if x.get("link_id") == it["link_id"]), None)
        else:
            cur = next((x for x in srcs if x.get("file_rel") == rel or x["id"] == self._made_id(it["path"])), None)
        if b.get("on"):
            if not cur and it["link_id"]:   # a web page, or a video with its transcript pasted
                made = self.import_url({"url": it["url"], "transcript": b.get("transcript", "")})
                src = self._src(made["id"])
                src["link_id"] = it["link_id"]
                self._src_save(src)
            elif not cur:
                self._import_bytes(it["name"], it["path"].read_bytes(), file_rel=rel)
        elif cur:
            if cur.get("made"):
                raise AppError("bad_value", "Slides made by the app are always sources.", status=400)
            self.delete_source(cur["id"])
        return self.library_list()

    def library_link_add(self, b: dict) -> dict:
        """A web link (video, playlist, site) joins the list like a file: it can be put in a week, ticked for students, and used as a source."""
        url = str(b.get("url") or "").strip()
        if "://" not in url:
            url = "https://" + url
        if not re.fullmatch(r"https?://[^\s/]+\.[^\s/]+\S{0,500}", url):
            raise AppError("bad_value", "Write a web address that starts with https://", status=400)
        title = " ".join(str(b.get("title") or "").split())[:120] or re.sub(r"^https?://(www\.)?", "", url)[:80]
        lib = self._lib()
        lid = uuid.uuid4().hex[:8]
        lib["links"][lid] = {"title": title, "url": url, "added": int(time.time())}
        self._save_lib(lib)
        return {**self.library_list(), "added": f"link:{lid}"}

    def library_link_delete(self, b: dict) -> dict:
        lib = self._lib()
        rel = self._rel(b)
        it = self._item(lib, rel)
        try:
            for place in lib["files"].get(rel, []):
                if place.get("shared"):
                    self.delete_publication(place["shared"]["id"])
        finally:
            lib["files"].pop(rel, None)
            lib["links"].pop(it["link_id"], None)
            self._save_lib(lib)
        for src in self._srcs():
            if src.get("link_id") == it["link_id"]:
                self.delete_source(src["id"])
        return self.library_list()

    def _week_fields(self, p: dict) -> dict:
        return {"note": p.get("note", ""), "trimester": p.get("t"), "week": p.get("w")}

    def library_share(self, b: dict) -> dict:
        """Put one placement of a file (the file, for that week, with its note) where students can see it. public=True: visible at once; False: hidden until approved."""
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        if it["path"] is not None and _private(it["name"]):
            raise AppError("private_file", "This file has names, grades or your plans. It cannot be shared with students.", status=400)
        place = self._place(lib, rel, str(b.get("pid") or ""))
        if place.get("shared"):
            raise AppError("bad_value", "This is already shared.", status=400)
        if it["url"]:
            kind, title, what = "link", it["name"], {"url": it["url"]}
        else:
            f = it["path"]
            kind = b.get("kind") if b.get("kind") in self.KINDS else _kind_of(f.name)
            title = " ".join(str(b.get("title") or f.stem.replace("_", " ")).split())[:120]
            what = {"file": {"filename": f.name, "data_b64": base64.b64encode(f.read_bytes()).decode()}}
        before = {x["id"] for x in self.list_publications()["items"]}
        self.add_publication({"class_id": b.get("class_id"), "kind": kind, "title": title, "visible_from": b.get("visible_from"),
                              "visible_until": b.get("visible_until"), **self._week_fields(place), **what})
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
        rel = self._rel(b)
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
        rel = self._rel(b)
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
        rel = self._rel(b)
        lib = self._lib()
        self._item(lib, rel)
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
        rel = self._rel(b)
        lib = self._lib()
        self._item(lib, rel)
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
        rel = self._rel(b)
        lib = self._lib()
        self._item(lib, rel)
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
