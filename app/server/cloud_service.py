"""Connection to the school's free Supabase server (Phase 12). Settings live in cloud.json in the data folder;
the password is never saved, only the refresh token."""
from __future__ import annotations

import base64
import io
import json
import secrets
import re
import uuid
from datetime import date

from ..core import paths
from ..core.cloud import Cloud, clean_url
from ..core.errors import AppError

def _small_jpeg(b64: str, side: int = 1280) -> bytes:
    """A picture from the teacher's computer, made small (free server space is limited)."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        im = im.convert("RGB")
    except Exception as e:
        raise AppError("image_unreadable", "This picture could not be read.", status=400) from e
    im.thumbnail((side, side))
    out = io.BytesIO(); im.save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


ROLES = ("admin", "teacher", "parent", "none")


class CloudMixin:
    def _cloud_path(self):
        return self._need_store().root / "cloud.json"

    def _cloud_cfg(self) -> dict:
        d = self._need_store().read_json(self._cloud_path(), {}, check=lambda x: isinstance(x, dict) or (_ for _ in ()).throw(ValueError("bad"))) or {}
        # the school can ship its own address and public key inside the app (resources/school_server.json), so teachers type nothing
        base = {}
        f = paths.resources_dir() / "school_server.json"
        if f.is_file():
            try:
                base = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                base = {}
        return {"url": str(d.get("url") or base.get("url") or ""), "key": str(d.get("key") or base.get("key") or ""), "email": str(d.get("email", "")),
                "school": str(d.get("school") or base.get("school") or "")[:60], "refresh": str(d.get("refresh", "")), "uid": str(d.get("uid", "")), "role": str(d.get("role", "")), "mode": d.get("mode") if d.get("mode") in ("online", "offline") else ""}

    def _cloud_save(self, cfg: dict) -> None:
        self._need_store().write_json(self._cloud_path(), cfg)

    def _cloud_client(self) -> Cloud:
        cfg = self._cloud_cfg()
        c = getattr(self, "_cloud_live", None)
        if c is None or (c.url, c.key) != (cfg["url"], cfg["key"]):
            c = self._cloud_live = Cloud(cfg["url"], cfg["key"], cfg["refresh"])
        return c

    def get_cloud(self) -> dict:
        cfg = self._cloud_cfg()
        admin = cfg["role"] == "admin"
        # the address and key are the administration's business: teachers only ever see the school's name
        return {"url": cfg["url"] if admin or not cfg["key"] else "", "configured": bool(cfg["url"] and cfg["key"]), "school": cfg["school"], "key_set": bool(cfg["key"]), "email": cfg["email"], "signed_in": bool(cfg["refresh"]), "role": cfg["role"], "mode": cfg["mode"]}

    def put_cloud(self, b: dict) -> dict:
        cfg = self._cloud_cfg()
        url = clean_url(str(b.get("url", cfg["url"])))
        key = str(b.get("key") or "").strip() or cfg["key"]
        if (url, key) != (cfg["url"], cfg["key"]):
            cfg.update(refresh="", role="")
            self._cloud_live = None
        cfg.update(url=url, key=key)
        if "school" in b:
            cfg["school"] = " ".join(str(b["school"]).split())[:60]
        if b.get("mode") in ("online", "offline"):
            cfg["mode"] = b["mode"]
        self._cloud_save(cfg)
        return self.get_cloud()

    def cloud_code_make(self) -> dict:
        """The school code: the server address, the public key and the school's name in one short text the administration gives to teachers."""
        cfg = self._cloud_cfg()
        if cfg["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can do this.", status=403)
        raw = json.dumps({"n": cfg["school"], "u": cfg["url"], "k": cfg["key"]}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return {"code": "DLIS-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")}

    def cloud_join(self, b: dict) -> dict:
        code = "".join(str(b.get("code", "")).split())
        try:
            body = code.split("-", 1)[1] if code.upper().startswith("DLIS-") else code
            d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))
            url, key = clean_url(str(d["u"])), str(d["k"]).strip()
            if not key:
                raise ValueError("no key")
        except (ValueError, KeyError, IndexError, TypeError, AppError) as e:
            raise AppError("cloud_bad_code", "This school code is not right. Copy it again from the administration.", status=400) from e
        return self.put_cloud({"url": url, "key": key, "school": d.get("n", "")})

    def cloud_forget_school(self) -> dict:
        cfg = self._cloud_cfg()
        cfg.update(url="", key="", school="", refresh="", role="", email="", mode="")
        self._cloud_live = None
        self._cloud_save(cfg)
        return self.get_cloud()

    def cloud_login(self, b: dict) -> dict:
        email, password = str(b.get("email", "")).strip(), str(b.get("password", ""))
        if not email or not password:
            raise AppError("cloud_bad_login", "Type the email and the password.", status=400)
        c = self._cloud_client()
        c.sign_in(email, password)
        role = c.role()
        if role == "parent":
            self._cloud_live = None
            raise AppError("cloud_parent_blocked", "This is the teachers' program. Parents use the parents' portal.", status=403)
        cfg = self._cloud_cfg()
        cfg.update(email=email, refresh=c.refresh, role=role, mode="online", uid=str((c.user or {}).get("id", "")))
        self._cloud_save(cfg)
        return self.get_cloud()

    def cloud_logout(self) -> dict:
        cfg = self._cloud_cfg()
        cfg.update(refresh="", role="", mode="offline")
        self._cloud_save(cfg)
        self._cloud_live = None
        return self.get_cloud()

    def cloud_test(self) -> dict:
        """Is the server reachable and are the school's tables there? (signed-in teachers/admins only see rows)"""
        c = self._cloud_client()
        role = c.role()
        tables = {}
        for t in ("announcements", "students", "grades", "publications", "week_plans"):
            c.select(t, "select=*&limit=1")
            tables[t] = True
        cfg = self._cloud_cfg()
        cfg["role"] = role
        cfg["refresh"] = c.refresh or cfg["refresh"]
        self._cloud_save(cfg)
        return {"ok": True, "role": role, "tables": tables}

    # ------------------------------------------------------------ announcements (only the administration writes them)
    def list_announcements(self) -> dict:
        cfg = self._cloud_cfg()
        if not (cfg["url"] and cfg["key"] and cfg["refresh"]):
            return {"connected": False, "role": "", "items": []}
        try:
            c = self._cloud_client()
            rows = c.select("announcements", "select=id,title,body,audience,starts_on,ends_on,created_at,image_path&order=starts_on.desc,created_at.desc&limit=100")
        except AppError as e:
            if e.code in ("cloud_offline", "cloud_error", "cloud_signed_out", "cloud_bad_login"):
                return {"connected": False, "role": cfg["role"], "items": [], "problem": e.code}
            raise
        today = date.today().isoformat()
        for r in rows:
            r["image_url"] = f"{cfg['url']}/storage/v1/object/public/announce/{r['image_path']}" if r.get("image_path") else ""
            r["active"] = (r.get("starts_on") or "") <= today and (not r.get("ends_on") or r["ends_on"] >= today)
        return {"connected": True, "role": cfg["role"], "items": rows}

    def _announcement_row(self, b: dict, partial: bool) -> dict:
        row = {}
        if not partial or "title" in b:
            title = " ".join(str(b.get("title", "")).split())[:120]
            if not title:
                raise AppError("bad_value", "Write a title for the announcement.", status=400)
            row["title"] = title
        if not partial or "body" in b:
            row["body"] = str(b.get("body", "")).strip()[:2000]
        if not partial or "audience" in b:
            if b.get("audience") not in ("staff", "parents", "all"):
                raise AppError("bad_value", "Choose who the announcement is for.", status=400)
            row["audience"] = b["audience"]
        for k in ("starts_on", "ends_on"):
            if partial and k not in b:
                continue
            v = str(b.get(k) or "")
            if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise AppError("bad_value", "The date is not right.", status=400)
            if v:
                row[k] = v
            elif partial and k == "ends_on":
                row[k] = None      # the end date was cleared
        if row.get("ends_on") and row.get("starts_on") and row["ends_on"] < row["starts_on"]:
            raise AppError("bad_value", "The end date is before the start date.", status=400)
        return row

    def post_announcement(self, b: dict) -> dict:
        if self._cloud_cfg()["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can post announcements.", status=403)
        row = self._announcement_row(b, False)
        img = b.get("image")
        c = self._cloud_client()
        if isinstance(img, dict) and img.get("data_b64"):
            row["image_path"] = f"{uuid.uuid4().hex}.jpg"
            c.upload("announce", row["image_path"], _small_jpeg(img["data_b64"]), "image/jpeg")
        c.insert("announcements", row)
        return self.list_announcements()

    def update_announcement(self, aid: str, b: dict) -> dict:
        """Change an announcement that is already out. A new picture replaces the old one; remove_image drops it."""
        if self._cloud_cfg()["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can change announcements.", status=403)
        if not re.fullmatch(r"[0-9a-f-]{36}", aid):
            raise AppError("bad_value", "Unknown announcement.", status=400)
        row = self._announcement_row(b, True)
        c = self._cloud_client()
        old = next(iter(c.select("announcements", f"select=image_path&id=eq.{aid}")), {}).get("image_path") or ""
        img = b.get("image")
        if isinstance(img, dict) and img.get("data_b64"):
            row["image_path"] = f"{uuid.uuid4().hex}.jpg"
            c.upload("announce", row["image_path"], _small_jpeg(img["data_b64"]), "image/jpeg")
        elif b.get("remove_image"):
            row["image_path"] = ""
        if row:
            c.update("announcements", f"id=eq.{aid}", row)
        if old and "image_path" in row and row["image_path"] != old:
            c.remove_object("announce", old)
        return self.list_announcements()

    def delete_announcement(self, aid: str) -> dict:
        if self._cloud_cfg()["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can delete announcements.", status=403)
        if not re.fullmatch(r"[0-9a-f-]{36}", aid):
            raise AppError("bad_value", "Unknown announcement.", status=400)
        c = self._cloud_client()
        for r in c.select("announcements", f"select=image_path&id=eq.{aid}"):
            if r.get("image_path"):
                c.remove_object("announce", r["image_path"])
        c.delete("announcements", f"id=eq.{aid}")
        return self.list_announcements()

    # ------------------------------------------------------------ files and links for parents (only after the teacher approves)
    KINDS = ("presentation", "quiz", "revision", "link", "other")

    def list_publications(self) -> dict:
        cfg = self._cloud_cfg()
        if not (cfg["url"] and cfg["key"] and cfg["refresh"]):
            return {"connected": False, "role": "", "items": []}
        try:
            rows = self._cloud_client().select("publications", "select=id,class_id,kind,title,url,file_path,approved,visible_from,visible_until,created_at&order=created_at.desc&limit=200")
        except AppError as e:
            if e.code in ("cloud_offline", "cloud_error", "cloud_signed_out", "cloud_bad_login"):
                return {"connected": False, "role": cfg["role"], "items": [], "problem": e.code}
            raise
        return {"connected": True, "role": cfg["role"], "items": rows}

    def _need_staff(self):
        if self._cloud_cfg()["role"] not in ("admin", "teacher"):
            raise AppError("cloud_staff_only", "Only teachers and the administration can do this.", status=403)

    @staticmethod
    def _stamp(v, end=False):
        v = str(v or "")
        if not v:
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise AppError("bad_value", "The date is not right.", status=400)
        return f"{v}T{'23:59:59' if end else '00:00:00'}+02:00"

    def add_publication(self, b: dict) -> dict:
        self._need_staff()
        class_id = str(b.get("class_id", ""))
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", class_id):
            raise AppError("bad_value", "Choose the class.", status=400)
        kind = b.get("kind")
        title = " ".join(str(b.get("title", "")).split())[:120]
        if kind not in self.KINDS or not title:
            raise AppError("bad_value", "Write a title and choose the kind.", status=400)
        row = {"class_id": class_id, "kind": kind, "title": title, "approved": False,
               "visible_from": self._stamp(b.get("visible_from")), "visible_until": self._stamp(b.get("visible_until"), True)}
        if kind == "quiz" and not row["visible_from"]:
            raise AppError("quiz_needs_date", "A quiz must have a date to show from (after it ends).", status=400)
        c = self._cloud_client()
        f = b.get("file")
        if isinstance(f, dict) and f.get("data_b64"):
            raw = base64.b64decode(f["data_b64"])
            if len(raw) > 15 * 1024 * 1024:
                raise AppError("file_too_big", "The file is bigger than 15 MB. Share a link instead.", status=400)
            name = re.sub(r"[^A-Za-z0-9._-]", "_", str(f.get("filename") or "file"))[-60:]
            row["file_path"] = f"{class_id}/{uuid.uuid4().hex[:10]}-{name}"
            c.upload("files", row["file_path"], raw, "application/octet-stream")
        else:
            link = str(b.get("url", "")).strip()
            if not re.fullmatch(r"https?://\S{3,500}", link):
                raise AppError("bad_value", "Add a file or a link that starts with https://", status=400)
            row["url"] = link
        c.insert("publications", row)
        return self.list_publications()

    def set_publication(self, pid: str, b: dict) -> dict:
        self._need_staff()
        if not re.fullmatch(r"[0-9a-f-]{36}", pid):
            raise AppError("bad_value", "Unknown item.", status=400)
        row = {}
        if "approved" in b:
            row["approved"] = bool(b["approved"])
        if "visible_from" in b:
            row["visible_from"] = self._stamp(b["visible_from"])
        if "visible_until" in b:
            row["visible_until"] = self._stamp(b["visible_until"], True)
        if row:
            self._cloud_client().update("publications", f"id=eq.{pid}", row)
        return self.list_publications()

    def delete_publication(self, pid: str) -> dict:
        self._need_staff()
        if not re.fullmatch(r"[0-9a-f-]{36}", pid):
            raise AppError("bad_value", "Unknown item.", status=400)
        c = self._cloud_client()
        for r in c.select("publications", f"select=file_path&id=eq.{pid}"):
            if r.get("file_path"):
                c.remove_object("files", r["file_path"])
        c.delete("publications", f"id=eq.{pid}")
        return self.list_publications()

    # ------------------------------------------------------------ activation codes: one per student, printed for the parent
    _CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def _codes_path(self):
        return self._need_store().root / "cloud_students.json"

    def _new_activation(self, taken: set) -> str:
        while True:
            c = "".join(secrets.choice(self._CODE_CHARS) for _ in range(8))
            if c not in taken:
                return c

    def codes_status(self) -> dict:
        d = self._need_store().read_json(self._codes_path(), {}) or {}
        return {"students": len(d), "role": self._cloud_cfg()["role"]}

    def prepare_codes(self) -> dict:
        """Give every student a code (new ones only), save the students on the school server, and make the sheet to print."""
        if self._cloud_cfg()["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can do this.", status=403)
        store = self._need_store()
        c = self._cloud_client()
        mapping = store.read_json(self._codes_path(), {}) or {}
        taken = {v["activation"] for v in mapping.values()}
        structure = store.load_structure()
        new_students, new_codes, sheet = [], [], []
        for room in structure.rooms:
            names = self.get_students(room.id)["names"]
            rows = []
            for name in names:
                key = f"{room.id}|{name}"
                if key not in mapping:
                    act = self._new_activation(taken); taken.add(act)
                    mapping[key] = {"student": "s" + secrets.token_hex(5), "activation": act}
                    new_students.append({"code": mapping[key]["student"], "class_id": room.id, "grade_id": room.grade_id, "display_name": name})
                    new_codes.append({"code": act, "student_code": mapping[key]["student"]})
                rows.append((name, mapping[key]["activation"]))
            if rows:
                sheet.append((room, rows))
        if new_students:
            c.upsert("students", new_students, "code")
            c.upsert("activation_codes", new_codes, "code")
        store.write_json(self._codes_path(), mapping)
        out = self._codes_sheet(sheet)
        return {**self._result(out), "new": len(new_students), "total": len(mapping)}

    def _codes_sheet(self, sheet):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        for i, (room, rows) in enumerate(sheet):
            if i:
                doc.add_page_break()
            doc.add_heading(room.name, level=1)
            doc.add_paragraph("Parents: open the DLIS parents' portal, create your account, and type the code of your child. / ولي الأمر: افتح بوابة الأولياء، اعمل حساب، واكتب كود ابنك.")
            tb = doc.add_table(rows=1, cols=3); tb.style = "Table Grid"
            for cell, txt in zip(tb.rows[0].cells, ("#", "Student / الطالب", "Code / الكود")):
                cell.text = txt
            for n, (name, act) in enumerate(rows, 1):
                cells = tb.add_row().cells
                cells[0].text, cells[1].text, cells[2].text = str(n), name, f"{act[:4]}-{act[4:]}"
        out = self._need_store().root / "Documents" / "Parent_Codes.docx"
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out)
        return out
