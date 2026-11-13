"""My files: everything the program made (Word, PowerPoint, Excel), in one list, and which of it is shared with students."""
from __future__ import annotations

import base64
import re
import time
import uuid

from ..core.errors import AppError

EXT = (".docx", ".pptx", ".xlsx", ".pdf")
SRC_EXT = (".docx", ".pptx", ".pdf")   # what the AI can read from a file
FOLDERS = ("Documents", "Slides", "Books", "Uploads")
MAX_UPLOAD = 40 * 1024 * 1024
# What can never go to students: it holds names, grades or the teacher's own planning.
PRIVATE = ("grading_sheet", "lesson_plan", "trimester_plan", "cover_sheet", "inspection_pack", "feedback", "report_card_comment")


def _auto_week(name: str):
    """Files the program made are named T1-W08_...: that is trimester 0, week 8."""
    m = re.match(r"T([1-3])-W(\d{1,2})_", name)
    return (int(m.group(1)) - 1, int(m.group(2))) if m else (None, None)


def _auto_place(name: str, g=None) -> dict:
    t, w = _auto_week(name)
    return {"id": "auto", "g": g, "t": t, "w": w, "note": "", "shared": None}


def _week_ok(t, w) -> bool:
    """A week is both numbers (trimester 0-2, week 1-60) or neither ('no week')."""
    return (t is None and w is None) or (isinstance(t, int) and isinstance(w, int) and not isinstance(t, bool) and 0 <= t <= 2 and 1 <= w <= 60)


def _msg_title(text: str) -> str:
    line = " ".join(str(text).split())
    return line if len(line) <= 70 else line[:69].rstrip() + "…"


def _pub_ids(shared) -> list:
    """The server items behind one shared placement: one per class of the grade (older versions kept a single id)."""
    if not shared:
        return []
    ids = list((shared.get("ids") or {}).values())
    return ids or ([shared["id"]] if shared.get("id") else [])


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
        d.setdefault("messages", {})   # short messages for the students: {id: {text, added}}
        d.setdefault("links", {})   # web links (a video, a playlist, a site): {id: {title, url, added}}
        legacy = d.pop("shared", None) or {}   # older versions kept one share per file
        for rel, sh in legacy.items():
            d["files"].setdefault(rel, [{"id": uuid.uuid4().hex[:8], "t": None, "w": None, "note": "", "shared": sh}])
        if legacy:
            self._need_store().write_json(self._lib_path(), d)
        return d

    def _save_lib(self, lib: dict) -> None:
        self._need_store().write_json(self._lib_path(), lib)

    # ---- grades: a file sits in a grade (and a week). Files the program made are in a folder named after the grade.
    def _grade_map(self) -> dict:
        try:
            grades = self._need_store().load_structure().grades
        except Exception:
            return {}
        return {re.sub(r'[\\/:*?"<>|]+', "-", g.name).strip().lower(): g.id for g in grades}

    def _auto_grade(self, rel: str, gm=None):
        parts = rel.split("/")
        if len(parts) >= 3 and parts[0] in ("Documents", "Slides", "Uploads"):
            return (self._grade_map() if gm is None else gm).get(parts[1].strip().lower())
        return None

    def _valid_grade(self, g):
        if g in (None, "", "none"):
            return None
        if g == "*":   # a book for every grade
            return "*"
        if any(x.id == g for x in self._need_store().load_structure().grades):
            return str(g)
        raise AppError("bad_value", "Choose the grade.", status=400)

    def _rooms_for(self, g) -> list:
        rooms = self._need_store().load_structure().rooms
        return [r.id for r in rooms if g == "*" or r.grade_id == g]

    @staticmethod
    def _shown(p: dict) -> dict:
        s = p.get("shared")
        if s and "ids" not in s:   # an older share: one class
            p = {**p, "shared": {**s, "ids": {s.get("class_id", ""): s.get("id", "")}}}
        return p

    def _places(self, lib: dict, rel: str, gm=None) -> list:
        rows = lib["files"].get(rel)
        if not rows:
            return [_auto_place(rel.rsplit("/", 1)[-1], self._auto_grade(rel, gm))]
        return [self._shown(p if "g" in p else {**p, "g": self._auto_grade(rel, gm)}) for p in rows]

    def _place(self, lib: dict, rel: str, pid: str) -> dict:
        """One placement of a file (a file can sit in several weeks). The automatic one is saved the first time it is changed."""
        rows = lib["files"].get(rel)
        if rows is None:
            rows = lib["files"][rel] = [_auto_place(rel.rsplit("/", 1)[-1], self._auto_grade(rel))]
            rows[0]["id"] = uuid.uuid4().hex[:8]
            if pid == "auto":
                pid = rows[0]["id"]
        if not pid or pid == "auto":   # "auto": the automatic one, which is the first once it has been saved
            p = rows[0]
        else:
            p = next((x for x in rows if x["id"] == pid), None)
            if not p:
                raise AppError("bad_value", "This file is not in that week.", status=400)
        if "g" not in p:
            p["g"] = self._auto_grade(rel)
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
        if rel.startswith("msg:"):
            m = lib["messages"].get(rel[4:])
            if not m:
                raise AppError("bad_value", "This message is not in your list.", status=400)
            return {"name": _msg_title(m["text"]), "path": None, "url": None, "link_id": "", "msg_id": rel[4:], "text": m["text"]}
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
        gm = self._grade_map()
        srcs = self._srcs()
        by_id = {x["id"]: x for x in srcs}
        by_rel = {x["file_rel"]: x for x in srcs if x.get("file_rel")}
        by_link = {x["link_id"]: x for x in srcs if x.get("link_id")}
        items, used = [], set()
        for sub in FOLDERS:
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
                                  "mtime": int(st.st_mtime), "size": st.st_size, "places": self._places(lib, rel, gm),
                                  "source": self._src_brief(src) if src else None, "source_locked": bool(src and src.get("made"))})
        for lid, link in lib["links"].items():
            src = by_link.get(lid)
            if src:
                used.add(src["id"])
            items.append({"rel": f"link:{lid}", "name": link["title"], "url": link["url"], "folder": "", "kind": "link", "private": False, "mtime": link.get("added", 0), "size": 0,
                          "places": self._places(lib, f"link:{lid}", gm), "source": self._src_brief(src) if src else None, "source_locked": False})
        for mid, m in lib["messages"].items():
            items.append({"rel": f"msg:{mid}", "name": _msg_title(m["text"]), "text": m["text"], "folder": "", "kind": "message", "private": False, "mtime": m.get("added", 0), "size": 0,
                          "places": self._places(lib, f"msg:{mid}", gm), "source": None, "source_locked": False})
        items.sort(key=lambda x: -x["mtime"])
        orphans = [self._src_brief(x) for x in srcs if x["id"] not in used]
        orphans.sort(key=lambda x: x["added"], reverse=True)
        return {"items": items[:600], "orphans": orphans, "root": str(root)}

    # ---- the AI can use every file of this list: a file is read the first time it is chosen (no switch to turn on)
    def library_sources(self) -> list:
        """Files and links of My files that are not yet sources, listed as 'virtual' sources: choosing one reads it."""
        lib = self._lib()
        root = self._need_store().root
        srcs = self._srcs()
        have_rel = {x["file_rel"] for x in srcs if x.get("file_rel")}
        have_id = {x["id"] for x in srcs}
        have_link = {x["link_id"] for x in srcs if x.get("link_id")}
        out = []
        for sub in FOLDERS:
            base = root / sub
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if not (p.is_file() and p.suffix.lower() in SRC_EXT and not p.name.startswith("~")) or _private(p.name):
                    continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel in have_rel or self._made_id(p) in have_id:
                    continue
                out.append({"id": "file:" + rel, "name": p.stem, "added": time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime)), "pages": 0, "pending": 0, "chars": 0,
                            "topic": "", "has_digest": False, "read_model": "", "made": False, "rel": rel, "virtual": True})
        for lid, link in lib["links"].items():
            if lid in have_link or re.search(r"youtube\.com|youtu\.be", link["url"], re.I):   # a video needs its text pasted, so it is added by hand
                continue
            out.append({"id": f"link:{lid}", "name": link["title"], "added": time.strftime("%Y-%m-%d", time.localtime(link.get("added", 0))), "pages": 0, "pending": 0, "chars": 0,
                        "topic": "", "has_digest": False, "read_model": "", "made": False, "rel": f"link:{lid}", "virtual": True})
        out.sort(key=lambda x: x["added"], reverse=True)
        return out[:300]

    def _materialize_source(self, sid: str) -> dict:
        """'file:<rel>' or 'link:<id>' (a file or link of My files) becomes a real source the first time it is used."""
        rel = sid[5:] if sid.startswith("file:") else sid
        lib = self._lib()
        it = self._item(lib, rel)
        srcs = self._srcs()
        if it["link_id"]:
            cur = next((x for x in srcs if x.get("link_id") == it["link_id"]), None)
        else:
            if _private(it["name"]) or it["path"].suffix.lower() not in SRC_EXT:
                raise AppError("bad_value", "The AI cannot read this file.", status=400)
            cur = next((x for x in srcs if x.get("file_rel") == rel or x["id"] == self._made_id(it["path"])), None)
        if not cur:
            if it["link_id"]:
                made = self.import_url({"url": it["url"]})
                cur = self._src(made["id"])
                cur["link_id"] = it["link_id"]
                self._src_save(cur)
            else:
                cur = self._src(self._import_bytes(it["name"], it["path"].read_bytes(), file_rel=rel)["id"])
        if not any(x.get("text") for x in cur["pages"]):
            raise AppError("source_needs_reading", "This file is made of pictures. Open My files and press «Read the pictures» on it first.", status=409)
        return cur

    def library_source(self, b: dict) -> dict:
        """Turn a file or a link into a source for the AI (it is read once), or stop using it as one. Slides the app made are always sources."""
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        srcs = self._srcs()
        if it["link_id"]:
            cur = next((x for x in srcs if x.get("link_id") == it["link_id"]), None)
        elif it["path"] is None:
            raise AppError("bad_value", "A message is not a source.", status=400)
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
        rel = f"link:{lid}"
        self._add_first_place(lib, rel, b)
        self._save_lib(lib)
        return {**self.library_list(), "added": rel}

    def _add_first_place(self, lib: dict, rel: str, b: dict) -> None:
        """A new link, message or upload can be put in its grade and week at once."""
        if not any(k in b for k in ("g", "t", "w")):
            return
        t, w = b.get("t"), b.get("w")
        if not _week_ok(t, w):
            raise AppError("bad_value", "Choose the week.", status=400)
        lib["files"][rel] = [{"id": uuid.uuid4().hex[:8], "g": self._valid_grade(b.get("g")), "t": t, "w": w, "note": "", "shared": None}]

    def library_upload(self, b: dict) -> dict:
        """A file the teacher brings in (a book, a worksheet, a deck made elsewhere) is kept in the Uploads folder and put in its grade and week."""
        name = re.sub(r'[\\/:*?"<>|]+', "_", str(b.get("filename") or "")).strip(" .")[:120]
        if not name.lower().endswith(EXT):
            raise AppError("bad_value", "Choose a Word, PowerPoint, Excel or PDF file.", status=400)
        try:
            raw = base64.b64decode(b.get("data_b64") or "")
        except ValueError as e:
            raise AppError("file_unreadable") from e
        if not raw:
            raise AppError("file_unreadable", "The file is empty.", status=400)
        if len(raw) > MAX_UPLOAD:
            raise AppError("file_too_big", "The file is bigger than 40 MB.", status=400)
        g = self._valid_grade(b.get("g"))
        lib = self._lib()
        root = self._need_store().root
        gname = next((x.name for x in self._need_store().load_structure().grades if x.id == g), "") if g and g != "*" else ""
        folder = root / "Uploads" / (re.sub(r'[\\/:*?"<>|]+', "-", gname).strip() or "") if gname else root / "Uploads"
        folder.mkdir(parents=True, exist_ok=True)
        stem, dot, ext = name.rpartition(".")
        p, n = folder / name, 2
        while p.exists():
            p = folder / f"{stem} ({n}){dot}{ext}"
            n += 1
        p.write_bytes(raw)
        rel = str(p.relative_to(root)).replace("\\", "/")
        self._add_first_place(lib, rel, {"g": g, "t": b.get("t"), "w": b.get("w")})
        self._save_lib(lib)
        if p.suffix.lower() in SRC_EXT and not _private(p.name):   # the AI can use it at once; picture-only pages are read afterwards
            try:
                self._import_bytes(p.name, raw, file_rel=rel)
            except AppError:
                pass
        return {**self.library_list(), "added": rel}

    def library_link_delete(self, b: dict) -> dict:
        lib = self._lib()
        rel = self._rel(b)
        it = self._item(lib, rel)
        try:
            for place in lib["files"].get(rel, []):
                for pid in _pub_ids(place.get("shared")):
                    self.delete_publication(pid)
        finally:
            lib["files"].pop(rel, None)
            lib["links"].pop(it["link_id"], None)
            self._save_lib(lib)
        for src in self._srcs():
            if src.get("link_id") == it["link_id"]:
                self.delete_source(src["id"])
        return self.library_list()

    # ---- messages: a few words for the students, in their grade and week (a reminder, the homework, what to bring)
    @staticmethod
    def _msg_text(b: dict) -> str:
        text = "\n".join(" ".join(line.split()) for line in str(b.get("text") or "").strip().splitlines())[:600].strip()
        if not text:
            raise AppError("bad_value", "Write the message.", status=400)
        return text

    def library_message_add(self, b: dict) -> dict:
        text = self._msg_text(b)
        lib = self._lib()
        mid = uuid.uuid4().hex[:8]
        lib["messages"][mid] = {"text": text, "added": int(time.time())}
        rel = f"msg:{mid}"
        self._add_first_place(lib, rel, {"g": b.get("g"), "t": b.get("t"), "w": b.get("w")})
        self._save_lib(lib)
        return {**self.library_list(), "added": rel}

    def library_message_set(self, b: dict) -> dict:
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        if not it.get("msg_id"):
            raise AppError("bad_value", "This is not a message.", status=400)
        text = self._msg_text(b)
        lib["messages"][it["msg_id"]]["text"] = text
        self._save_lib(lib)
        for place in lib["files"].get(rel, []):   # the students see the new words
            for pid in _pub_ids(place.get("shared")):
                self.set_publication(pid, {"body": text, "title": _msg_title(text)})
        return self.library_list()

    def library_message_delete(self, b: dict) -> dict:
        lib = self._lib()
        rel = self._rel(b)
        it = self._item(lib, rel)
        if not it.get("msg_id"):
            raise AppError("bad_value", "This is not a message.", status=400)
        try:
            for place in lib["files"].get(rel, []):
                for pid in _pub_ids(place.get("shared")):
                    self.delete_publication(pid)
        finally:
            lib["files"].pop(rel, None)
            lib["messages"].pop(it["msg_id"], None)
            self._save_lib(lib)
        return self.library_list()

    # ---- showing to the students
    def _week_fields(self, p: dict) -> dict:
        return {"note": p.get("note", ""), "trimester": p.get("t"), "week": p.get("w")}

    def _sync_shared(self, place: dict, fields: dict) -> None:
        for pid in _pub_ids(place.get("shared")):
            self.set_publication(pid, fields)

    def _drop_shared(self, lib: dict, place: dict) -> None:
        """Take a placement away from the students (all the classes of its grade)."""
        s = place.get("shared")
        if not s:
            return
        try:
            for pid in _pub_ids(s):
                self.delete_publication(pid)
        finally:
            place["shared"] = None
            self._save_lib(lib)

    def _publish(self, lib: dict, rel: str, it: dict, place: dict, class_ids: list, b: dict) -> None:
        """Make one server item per class for this placement of the file, link or message."""
        if it["path"] is not None and _private(it["name"]):
            raise AppError("private_file", "This file has names, grades or your plans. It cannot be shared with students.", status=400)
        if it.get("msg_id"):
            kind, title, what = "message", it["name"], {"body": it["text"]}
        elif it["url"]:
            kind, title, what = "link", it["name"], {"url": it["url"]}
        else:
            f = it["path"]
            kind = b.get("kind") if b.get("kind") in self.KINDS else _kind_of(f.name)
            title = " ".join(str(b.get("title") or f.stem.replace("_", " ")).split())[:120]
            what = {"file": {"filename": f.name, "data_b64": base64.b64encode(f.read_bytes()).decode()}}
        before = {x["id"] for x in self.list_publications()["items"]}
        who = {"class_id": class_ids[0]} if len(class_ids) == 1 else {"class_ids": class_ids}
        self.add_publication({**who, "kind": kind, "title": title, "visible_from": b.get("visible_from"), "visible_until": b.get("visible_until"),
                              "approved": bool(b.get("public")), **self._week_fields(place), **what})
        new = [x for x in self.list_publications()["items"] if x["id"] not in before]
        ids = {x["class_id"]: x["id"] for x in new if x.get("class_id") in class_ids}
        if len(ids) != len(class_ids):
            for x in new:   # do not leave half of it on the server
                try:
                    self.delete_publication(x["id"])
                except AppError:
                    pass
            raise AppError("cloud_error", "Could not share the file. Try again.", status=502)
        place["shared"] = {"id": ids[class_ids[0]], "class_id": class_ids[0], "ids": ids, "public": bool(b.get("public")), "at": int(time.time())}
        self._save_lib(lib)

    def library_share(self, b: dict) -> dict:
        """Put one placement of a file (the file, for that week, with its note) where students of ONE class can see it. public=True: visible at once; False: hidden until approved."""
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        place = self._place(lib, rel, str(b.get("pid") or ""))
        if place.get("shared"):
            raise AppError("bad_value", "This is already shared.", status=400)
        self._publish(lib, rel, it, place, [str(b.get("class_id"))], b)
        return self.library_list()

    def library_visible(self, b: dict) -> dict:
        """The «for students» switch: on = every class of the placement's grade can see it now; off = taken away from them."""
        rel = self._rel(b)
        lib = self._lib()
        it = self._item(lib, rel)
        place = self._place(lib, rel, str(b.get("pid") or ""))
        cur = place.get("shared")
        if not b.get("on"):
            self._drop_shared(lib, place)
            return self.library_list()
        if cur and cur.get("public"):
            return self.library_list()
        if cur:   # shared by an older version and still waiting for approval
            for pid in _pub_ids(cur):
                self.set_publication(pid, {"approved": True})
            cur["public"] = True
            self._save_lib(lib)
            return self.library_list()
        rooms = self._rooms_for(place.get("g"))
        if not rooms:
            raise AppError("no_grade", "Choose the grade of this file first, then show it to the students.", status=400)
        self._publish(lib, rel, it, place, rooms, {**b, "public": True, "kind": b.get("kind") or None})
        return self.library_list()

    def library_set_public(self, b: dict) -> dict:
        rel = self._rel(b)
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        s = place.get("shared")
        if not s:
            raise AppError("bad_value", "This file is not shared.", status=400)
        for pid in _pub_ids(s):
            self.set_publication(pid, {"approved": bool(b.get("public"))})
        s["public"] = bool(b.get("public"))
        self._save_lib(lib)
        return self.library_list()

    def library_unshare(self, b: dict) -> dict:
        rel = self._rel(b)
        lib = self._lib()
        place = self._place(lib, rel, str(b.get("pid") or ""))
        self._drop_shared(lib, place)
        return self.library_list()

    # ---- where a file sits: grade, week, note
    def library_place(self, b: dict) -> dict:
        """Change a placement: its grade, which week it belongs to (t and w both, or both empty for 'no week') and/or its note for the students."""
        rel = self._rel(b)
        lib = self._lib()
        self._item(lib, rel)
        place = self._place(lib, rel, str(b.get("pid") or ""))
        unshared = False
        if "g" in b:
            g = self._valid_grade(b.get("g"))
            if g != place.get("g"):
                if place.get("shared"):   # other classes now: the students lose it until it is shown again
                    self._drop_shared(lib, place)
                    unshared = True
                place["g"] = g
        if "w" in b or "t" in b:
            t, w = b.get("t"), b.get("w")
            if not _week_ok(t, w):
                raise AppError("bad_value", "Choose the week.", status=400)
            place["t"], place["w"] = t, w
        if "note" in b:
            place["note"] = " ".join(str(b.get("note") or "").split())[:300]
        self._save_lib(lib)
        if place.get("shared"):   # the students see the same week and note
            self._sync_shared(place, self._week_fields(place))
        return {**self.library_list(), "unshared": unshared}

    def library_place_add(self, b: dict) -> dict:
        """Use the same file in one more week or grade (half of the slides in week 1, the other half in week 2), with its own note.
        A file that has no week yet is simply put there."""
        rel = self._rel(b)
        lib = self._lib()
        self._item(lib, rel)
        first = self._place(lib, rel, "")   # keeps the automatic one
        t, w = b.get("t"), b.get("w")
        if not _week_ok(t, w):
            raise AppError("bad_value", "Choose the week.", status=400)
        g = self._valid_grade(b["g"]) if "g" in b else first.get("g")
        rows = lib["files"][rel]
        if len(rows) == 1 and first.get("t") is None and not first.get("shared") and t is not None:
            first["g"], first["t"], first["w"] = g, t, w   # it had no week: it moves there
        else:
            if any(x.get("g") == g and x["t"] == t and x["w"] == w for x in rows):
                raise AppError("bad_value", "The file is already in that week.", status=400)
            rows.append({"id": uuid.uuid4().hex[:8], "g": g, "t": t, "w": w, "note": "", "shared": None})
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
            for pid in _pub_ids(place.get("shared")):
                self.delete_publication(pid)
        finally:
            rows.remove(place)
            if not rows:
                rows.append({"id": uuid.uuid4().hex[:8], "g": None, "t": None, "w": None, "note": "", "shared": None})
            self._save_lib(lib)
        return self.library_list()
