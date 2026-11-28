"""Messages between the teachers and the families, through the school's server (Phase 12).
A teacher talks to the student ('student_teacher') or to the student's parents ('parent_teacher': father and mother share ONE conversation).
The server's rules decide who sees what; this file only asks for it and shapes the answer. The administration can read every conversation,
hide a message and close reports."""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone

from ..core.errors import AppError

KINDS = ("parent_teacher", "student_teacher")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_Q = lambda s: urllib.parse.quote(str(s), safe="")


def _uuid(v, what="id") -> str:
    v = str(v or "")
    if not _UUID.fullmatch(v):
        raise AppError("bad_value", f"The {what} is not right.", status=400)
    return v


def _later(a: str, b: str) -> bool:
    """Is time a after time b? (both ISO texts from the server)"""
    try:
        return datetime.fromisoformat(a.replace("Z", "+00:00")) > datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return a > b


class MessagesMixin:
    def _msg_cloud(self):
        cfg = self._cloud_cfg()
        if cfg["role"] not in ("teacher", "admin") or not cfg["refresh"]:
            raise AppError("cloud_staff_only", "Sign in to the school server with a teacher account first.", status=403)
        return self._cloud_client(), cfg

    def _msg_load(self) -> dict:
        """Every conversation this account may see, with the student's name, the last message and whether it is waiting for an answer."""
        c, cfg = self._msg_cloud()
        threads = c.select("threads", "select=id,kind,teacher_id,student_code,last_at&order=last_at.desc&limit=300")
        out = {"role": cfg["role"], "uid": cfg["uid"], "threads": [], "unread": 0}
        if not threads:
            return out
        ids = ",".join(t["id"] for t in threads)
        codes = ",".join(_Q(t["student_code"]) for t in {t["student_code"]: t for t in threads}.values())
        students = {s["code"]: s for s in c.select("students", f"select=code,display_name,class_id&code=in.({codes})")}
        last: dict = {}
        for m in c.select("messages", f"select=id,thread_id,sender_id,sender_role,sender_name,body,hidden,created_at&thread_id=in.({ids})&order=created_at.desc&limit=600"):
            last.setdefault(m["thread_id"], m)
        read = {r["thread_id"]: r["read_at"] for r in c.select("thread_reads", f"select=thread_id,read_at&thread_id=in.({ids})")}
        names = {}
        if cfg["role"] == "admin":
            for r in c.select("teacher_classes", "select=teacher_id,teacher_name&teacher_name=neq.&limit=500"):
                names.setdefault(r["teacher_id"], r["teacher_name"])
        rooms = {r.id: r.name for r in self._need_store().load_structure().rooms}
        for th in threads:
            m, s = last.get(th["id"]), students.get(th["student_code"], {})
            mine = th["teacher_id"] == cfg["uid"]
            unread = bool(mine and m and m["sender_id"] != cfg["uid"] and (th["id"] not in read or _later(m["created_at"], read[th["id"]])))
            out["unread"] += unread
            out["threads"].append({"id": th["id"], "kind": th["kind"], "student_code": th["student_code"], "student_name": s.get("display_name") or "", "class_id": s.get("class_id", ""),
                                   "class_name": rooms.get(s.get("class_id", ""), ""), "teacher_name": names.get(th["teacher_id"], ""), "mine": mine,
                                   "last_at": th["last_at"], "last_body": (m or {}).get("body", ""), "last_role": (m or {}).get("sender_role", ""), "unread": unread})
        return out

    def msg_threads(self) -> dict:
        cfg = self._cloud_cfg()
        if not (cfg["url"] and cfg["key"] and cfg["refresh"]) or cfg["role"] not in ("teacher", "admin"):
            return {"connected": False, "role": cfg["role"], "threads": [], "unread": 0}
        try:
            return {"connected": True, **self._msg_load()}
        except AppError as e:
            if e.code in ("cloud_offline", "cloud_error", "cloud_signed_out", "cloud_bad_login"):
                return {"connected": False, "role": cfg["role"], "threads": [], "unread": 0, "problem": e.code}
            raise

    def msg_unread(self) -> dict:
        return {"unread": self.msg_threads()["unread"]}

    def msg_thread(self, thread_id: str) -> dict:
        c, cfg = self._msg_cloud()
        tid = _uuid(thread_id, "conversation")
        rows = c.select("messages", f"select=id,sender_id,sender_role,sender_name,body,hidden,created_at&thread_id=eq.{tid}&order=created_at.asc&limit=500")
        for m in rows:
            m["mine"] = m["sender_id"] == cfg["uid"]
        return {"messages": rows}

    def msg_send(self, b: dict) -> dict:
        c, cfg = self._msg_cloud()
        tid, body = _uuid(b.get("thread_id"), "conversation"), str(b.get("body", "")).strip()
        if not body:
            raise AppError("bad_value", "Write the message first.", field="body", status=400)
        if len(body) > 1000:
            raise AppError("bad_value", "A message can have 1000 letters at most.", field="body", status=400)
        row = c.insert("messages", {"thread_id": tid, "body": body})
        return {"message": {**(row[0] if row else {}), "mine": True}}

    def msg_read(self, b: dict) -> dict:
        c, _cfg = self._msg_cloud()
        c.upsert("thread_reads", [{"thread_id": _uuid(b.get("thread_id"), "conversation"), "read_at": datetime.now(timezone.utc).isoformat()}], "thread_id,user_id")
        return {"ok": True}

    def msg_students(self) -> dict:
        """The teacher's classes and the students in them (from the server), to start a conversation with."""
        c, cfg = self._msg_cloud()
        rooms = {r.id: r.name for r in self._need_store().load_structure().rooms}
        if cfg["role"] in ("teacher", "admin") and cfg.get("uid"):
            try:
                self.cloud_sync_classes()              # the classes of today's timetable, not the ones of the last sign-in
            except Exception:
                pass
        mine = c.select("teacher_classes", f"select=class_id,subject&teacher_id=eq.{_Q(cfg['uid'])}") if cfg["role"] == "teacher" else c.select("teacher_classes", "select=class_id,subject&limit=500")
        ids = sorted({r["class_id"] for r in mine})
        if not ids:
            return {"classes": []}
        studs = c.select("students", f"select=code,display_name,class_id,grade_id&class_id=in.({','.join(_Q(i) for i in ids)})&order=display_name&limit=1500")
        return {"classes": [{"class_id": i, "name": rooms.get(i, i), "students": [{"code": s["code"], "name": s["display_name"] or s["code"], "student_login": not str(s["grade_id"]).startswith("kg")} for s in studs if s["class_id"] == i]} for i in ids]}

    def msg_start(self, b: dict) -> dict:
        c, cfg = self._msg_cloud()
        kind, code = str(b.get("kind", "")), str(b.get("student_code", "")).strip()
        if kind not in KINDS or not code:
            raise AppError("bad_value", "Choose the student and who the message is for.", status=400)
        have = c.select("threads", f"select=id&teacher_id=eq.{_Q(cfg['uid'])}&student_code=eq.{_Q(code)}&kind=eq.{kind}&limit=1")
        if have:
            return {"id": have[0]["id"], "existing": True}
        row = c.insert("threads", {"kind": kind, "teacher_id": cfg["uid"], "student_code": code})
        return {"id": row[0]["id"], "existing": False}

    # ------------------------------------------------------------ the administration: reports and hiding
    def _need_admin(self):
        c, cfg = self._msg_cloud()
        if cfg["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can do this.", status=403)
        return c

    def msg_reports(self) -> dict:
        c = self._need_admin()
        reps = c.select("message_reports", "select=id,message_id,reason,status,created_at&order=status.desc,created_at.desc&limit=100")
        if not reps:
            return {"reports": [], "open": 0}
        msgs = {m["id"]: m for m in c.select("messages", f"select=id,thread_id,body,sender_role,sender_name,hidden,created_at&id=in.({','.join(r['message_id'] for r in reps)})")}
        ths = {t["id"]: t for t in c.select("threads", f"select=id,kind,teacher_id,student_code&id=in.({','.join({m['thread_id'] for m in msgs.values()}) or 'x'})")} if msgs else {}
        studs = {s["code"]: s["display_name"] for s in c.select("students", f"select=code,display_name&code=in.({','.join(_Q(t['student_code']) for t in ths.values()) or 'x'})")} if ths else {}
        out = []
        for r in reps:
            m = msgs.get(r["message_id"], {})
            th = ths.get(m.get("thread_id"), {})
            out.append({**r, "body": m.get("body", ""), "sender_role": m.get("sender_role", ""), "sender_name": m.get("sender_name", ""), "hidden": bool(m.get("hidden")), "thread_id": m.get("thread_id", ""),
                        "kind": th.get("kind", ""), "student_name": studs.get(th.get("student_code"), "")})
        return {"reports": out, "open": sum(1 for r in out if r["status"] == "open")}

    def msg_hide(self, message_id: str, b: dict) -> dict:
        c = self._need_admin()
        c.update("messages", f"id=eq.{_uuid(message_id, 'message')}", {"hidden": bool(b.get("hidden", True))})
        return {"ok": True}

    def msg_report_done(self, report_id: str, b: dict) -> dict:
        c = self._need_admin()
        rid = _uuid(report_id, "report")
        if b.get("hide"):
            for r in c.select("message_reports", f"select=message_id&id=eq.{rid}"):
                c.update("messages", f"id=eq.{r['message_id']}", {"hidden": True})
        c.update("message_reports", f"id=eq.{rid}", {"status": "done"})
        return {"ok": True}
