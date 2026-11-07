"""Curriculum progress (how many lessons were really logged), the inspection pack, and the weekly status the administration sees."""
from __future__ import annotations

import csv
import re
import zipfile
from datetime import date, timedelta

from ..core.errors import AppError
from ..core.timetable import sessions_on


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_") or "teacher"


class CoverageMixin:
    def coverage(self, today: str = "") -> dict:
        """For every class: lessons held so far this term (from the timetable) against lessons logged, and the topic planned for this week."""
        store = self._need_store()
        d_now = date.fromisoformat(today) if today else date.today()
        cal = self._calendar_service()
        pos = cal.position(d_now)
        if pos.get("state") != "in_term":
            return {"state": pos.get("state", "no_calendar"), "rows": []}
        tri = pos["trimester"]
        weeks = cal.trimester_weeks(tri)
        start = date.fromisoformat(weeks[0]["start"]) if weeks else d_now
        self._seed_timetable(store)
        tt = self._with_fixed(store.load_timetable())
        structure = store.load_structure()
        held: dict[str, int] = {}
        d = start
        while d <= d_now:
            for s in sessions_on(d, tt, cal, structure):
                if not s.get("extra"):
                    held[s["room_id"]] = held.get(s["room_id"], 0) + 1
            d += timedelta(days=1)
        entries = [e for e in self._log_data()["entries"] if start.isoformat() <= e["date"] <= d_now.isoformat()]
        rows = []
        for room in structure.rooms:
            n_held = held.get(room.id, 0)
            if not n_held:
                continue
            mine = sorted((e for e in entries if e["room_id"] == room.id), key=self._log_key)
            n_logged = len({(e["date"], str(e.get("period", ""))) for e in mine})
            pct = min(100, round(100 * n_logged / n_held))
            topics = self.slide_topics(room.grade_id, tri)["weeks"]
            planned = next((w["topic"] for w in topics if w["week"] == pos["week"]), "")
            last = mine[-1] if mine else None
            rows.append({"room_id": room.id, "held": n_held, "logged": n_logged, "percent": pct,
                         "status": "ok" if pct >= 80 else "warn" if pct >= 50 else "bad",
                         "last_date": last["date"] if last else "", "last_topic": last["topic"] if last else "", "planned_now": planned})
        rows.sort(key=lambda r: r["percent"])
        return {"state": "in_term", "trimester": tri, "week": pos["week"], "rows": rows}

    def inspection_pack(self) -> dict:
        """One folder-in-a-zip with the term's papers, so a visit from a supervisor takes minutes, not days."""
        store = self._need_store()
        s = store.load_settings()
        cov = self.coverage()
        tri = cov.get("trimester", 0) + 1 if cov.get("state") == "in_term" else 0
        root = store.root
        out = root / "Documents" / f"Inspection_Pack_{_safe(s.teacher_name)}.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        rooms = {r.id: r.name for r in store.load_structure().rooms}
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            n = 0
            docs = root / "Documents"
            for f in sorted(docs.rglob("*.docx")) if docs.is_dir() else []:
                if tri and not re.search(rf"T{tri}[-_]", f.name):
                    continue
                z.write(f, "Documents/" + f.relative_to(docs).as_posix()); n += 1
            import io
            buf = io.StringIO(); w = csv.writer(buf)
            w.writerow(["Date", "Class", "Period", "Topic", "Slide reached", "Total slides", "Note"])
            for e in sorted(self._log_data()["entries"], key=self._log_key):
                w.writerow([e["date"], rooms.get(e["room_id"], e["room_id"]), e.get("period", ""), e["topic"], e.get("slide") or "", e.get("total") or "", e.get("note", "")])
            z.writestr("Lesson_Log.csv", "﻿" + buf.getvalue())
            buf = io.StringIO(); w = csv.writer(buf); w.writerow(["Class", "Lessons held", "Lessons logged", "Percent", "Last topic"])
            for r in cov.get("rows", []):
                w.writerow([rooms.get(r["room_id"], r["room_id"]), r["held"], r["logged"], r["percent"], r["last_topic"]])
            z.writestr("Curriculum_Progress.csv", "﻿" + buf.getvalue())
            z.writestr("README.txt", f"{s.school_name}\nTeacher: {s.teacher_name}\nSubject: {s.subject}\nMade on {date.today().isoformat()}\n"
                                      f"Word files: {n}. Lesson_Log.csv = every lesson logged. Curriculum_Progress.csv = lessons logged against lessons held.\n")
        tmp.replace(out)
        return self._result(out)

    # ------------------------------------------------------------ what the administration sees (counts only, never the files)
    def push_status(self) -> dict:
        cfg = self._cloud_cfg()
        if cfg["role"] not in ("teacher", "admin"):
            raise AppError("cloud_staff_only", "Sign in with a teacher account first.", status=403)
        cov = self.coverage()
        if cov.get("state") != "in_term":
            return {"sent": False, "reason": cov.get("state", "")}
        wk = self.get_weekly(cov["trimester"], cov["week"])
        s = self._need_store().load_settings()
        avg = round(sum(r["percent"] for r in cov["rows"]) / len(cov["rows"])) if cov["rows"] else 0
        row = {"teacher_name": s.teacher_name, "subject": s.subject, "trimester": cov["trimester"], "week": cov["week"],
               "done": wk["done"], "total": wk["total"], "progress_percent": avg,
               "items": [{"name": r["name"], "states": r["states"]} for r in wk["rows"]], "updated_at": date.today().isoformat()}
        if cfg.get("uid"):
            row["teacher_id"] = cfg["uid"]
        self._cloud_client().upsert("teacher_status", [row], "teacher_id,trimester,week")
        return {"sent": True, "done": row["done"], "total": row["total"]}

    def staff_status(self) -> dict:
        cfg = self._cloud_cfg()
        if cfg["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can see this.", status=403)
        pos = self._calendar_service().position(date.today())
        q = "select=teacher_name,subject,trimester,week,done,total,progress_percent,items,updated_at&order=teacher_name"
        if pos.get("state") == "in_term":
            q += f"&trimester=eq.{pos['trimester']}&week=eq.{pos['week']}"
        return {"week": pos.get("week"), "trimester": pos.get("trimester"), "rows": self._cloud_client().select("teacher_status", q)}
