"""Word documents and tasks. A mixin for Service (needs self._need_store, self._calendar_service, self.get_timetable)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from ..core import documents as D
from ..core import paths
from ..core.errors import AppError
from ..core.models import WEEKDAYS, is_safe_id
from ..core.names import english_name

IMPORTANCE = ("high", "medium", "low")


OPENABLE = {".docx", ".xlsx", ".pptx", ".pdf", ".csv", ".zip", ".txt", ".json"}


def _check_tasks(d) -> None:
    if not isinstance(d, dict) or not all(isinstance(x, dict) for x in d.get("tasks", [])) or not isinstance(d.get("dismissed", []), list):
        raise ValueError("tasks.json has the wrong shape")


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "Class"


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def _fmt_full(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _minutes(a: str, b: str) -> int:
    try:
        (h1, m1), (h2, m2) = (int(x) for x in a.split(":")), (int(x) for x in b.split(":"))
        return (h2 * 60 + m2) - (h1 * 60 + m1)
    except ValueError:
        return 0


class DocsMixin:
    # ------------------------------------------------------------ what a document needs to know
    def _room_grade(self, room_id: str):
        store = self._need_store()
        s = store.load_structure()
        room = next((r for r in s.rooms if r.id == room_id), None)
        if not room:
            raise AppError("room_not_found", status=404)
        return room, next(g for g in s.grades if g.id == room.grade_id)

    def _grade(self, grade_id: str):
        s = self._need_store().load_structure()
        g = next((x for x in s.grades if x.id == grade_id), None)
        if not g:
            raise AppError("grade_not_found", status=404)
        return g

    @staticmethod
    def _grade_label(g) -> str:
        m = re.fullmatch(r"kg(\d)", g.id)
        if m:
            return f"KG {m.group(1)}"
        m = re.fullmatch(r"g(\d+)", g.id)
        return m.group(1) if m else g.name

    def _week_info(self, tri: int, week: int) -> dict:
        cal = self._calendar_service()
        rng = cal.week_dates(tri, week)
        if not rng:
            raise AppError("week_not_found", "That week is not in the school calendar.", status=404)
        start, end = rng
        days, notes = {}, {}
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            name = WEEKDAYS[d.weekday()]
            if name not in D.DAYS or not cal.is_working_weekday(d):
                continue
            days[name] = _fmt(d)
            hol = cal.holiday_on(d)
            if hol:
                notes[name] = f"Holiday: {english_name(hol.name)}" if hol.name else "Holiday"
            else:
                ev = [e for e in cal.events_on(d) if re.search(r"day off|off\b", e, re.I)]
                if ev:
                    notes[name] = ev[0]
        return {"start": start, "end": end, "day_dates": days, "day_notes": notes}

    def _teach_days(self, grade_id: str) -> list[str]:
        """The week days this grade has a lesson with the teacher (from the normal timetable)."""
        store = self._need_store()
        self._seed_timetable(store)
        tt = store.load_timetable()
        rooms = {r.id for r in store.load_structure().rooms if r.grade_id == grade_id}
        return [d for d in D.DAYS if rooms & set((tt.grid.get(d) or {}).values())]

    def docs_context(self, room_id: str, tri: int, week: int) -> dict:
        store = self._need_store()
        room, grade = self._room_grade(room_id)
        info = self._week_info(tri, week)
        tt = store.load_timetable()
        minutes = 0
        for p in self._with_fixed(tt).periods:
            if any(room_id == (tt.grid.get(day, {}) or {}).get(p.name) for day in tt.grid):
                minutes = _minutes(p.start, p.end)
                break
        return {"room": room.name, "grade": grade.name, "grade_label": self._grade_label(grade),
                "start": info["start"].isoformat(), "end": info["end"].isoformat(),
                "range": f"{_fmt_full(info['start'])} – {_fmt_full(info['end'])}",
                "day_dates": info["day_dates"], "day_notes": info["day_notes"], "minutes": minutes,
                "students": len(store.load_students(room_id)), "teach_days": self._teach_days(grade.id)}

    # ------------------------------------------------------------ where files go
    def doc_file(self, kind: str, grade_name: str, tri: int, week: int = 0, extra: str = "") -> Path:
        base = self._need_store().root / "Documents" / _safe(grade_name)
        t = f"T{tri + 1}"
        if kind == "trimester_plan":
            return base / f"{t}_Trimester_Plan.docx"
        w = f"{t}-W{week:02d}"
        if kind == "lesson_plan":
            return base / f"{w}_Lesson_Plan.docx"
        if kind == "quiz":
            return base / f"{w}_Quiz{extra}.docx"
        return base / f"{w}_Grading_Sheet_{_safe(extra)}.docx"

    def _result(self, path: Path) -> dict:
        root = self._need_store().root
        return {"path": str(path), "name": path.name, "folder": str(path.parent), "rel": str(path.relative_to(root))}

    # ------------------------------------------------------------ the four documents
    def make_lesson_plan(self, b: dict) -> dict:
        store = self._need_store()
        grade = self._grade(str(b.get("grade_id", "")))
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 1))
        info = self._week_info(tri, week)
        s = store.load_settings()
        sample = next((r for r in store.load_structure().rooms if r.grade_id == grade.id), None)
        ctx = self.docs_context(sample.id, tri, week) if sample else {"minutes": 0}
        out = self.doc_file("lesson_plan", grade.name, tri, week)
        D.fill_lesson_plan(D.template_path("lesson_plan"), out, {
            "term": tri + 1, "week": week, "subject": s.subject, "teacher": s.teacher_name,
            "grade_label": grade.name, "date_range": ctx.get("range", ""),
            "length": f"{ctx['minutes']} min" if ctx.get("minutes") else "",
            "day_dates": info["day_dates"], "day_notes": info["day_notes"], "teach_days": self._teach_days(grade.id),
            "content": b.get("content") or {}})
        if isinstance(b.get("content"), dict):
            self.remember_lesson(grade.id, tri, week, b["content"])
        return self._result(out)

    def make_trimester_plan(self, b: dict) -> dict:
        store = self._need_store()
        grade = self._grade(str(b.get("grade_id", "")))
        tri = int(b.get("trimester", 0))
        cal = self._calendar_service()
        weeks = cal.trimester_weeks(tri)
        if not weeks:
            raise AppError("week_not_found", "Set the trimester dates in the Calendar first.", status=409)
        lessons = [str(x).strip() for x in (b.get("lessons") or [])]
        rows = []
        for i, w in enumerate(weeks):
            hol = [h for h in w["holidays"] if h["name"]]
            note = ""
            if w["school_days"] == 0:
                note = "No classes"
            elif hol:
                note = "Holiday: " + english_name(hol[0]["name"])
            rows.append({"number": w["number"], "from": _fmt(date.fromisoformat(w["start"])), "to": _fmt(date.fromisoformat(w["end"])),
                         "lesson": lessons[i] if i < len(lessons) else "", "note": note})
        s = store.load_settings()
        out = self.doc_file("trimester_plan", grade.name, tri)
        D.fill_trimester_plan(D.template_path("trimester_plan"), out, {
            "trimester": tri + 1, "subject": s.subject, "grade_label": self._grade_label(grade),
            "academic_year": store.load_calendar().academic_year, "textbooks": b.get("textbooks", ""), "weeks": rows})
        self.remember_trimester(grade.id, tri, [w["number"] for w in weeks], lessons)
        return self._result(out)

    def make_quiz(self, b: dict) -> dict:
        grade = self._grade(str(b.get("grade_id", "")))
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 1))
        questions = D.parse_quiz(b.get("text", ""))
        if not questions:
            raise AppError("no_questions", "Paste at least one question first.")
        number = int(b.get("number", 1) or 1)
        out = self.doc_file("quiz", grade.name, tri, week, extra=f"_{number}")
        D.fill_quiz(D.template_path("quiz"), out, {
            "grade_label": self._grade_label(grade), "trimester": tri + 1, "week": week, "number": number,
            "questions": questions, "with_answers": bool(b.get("with_answers"))})
        res = self._result(out)
        res["questions"] = len(questions)
        return res

    def make_grading_sheet(self, b: dict) -> dict:
        store = self._need_store()
        room_id = str(b.get("room_id", ""))
        room, grade = self._room_grade(room_id)
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 1))
        ctx = self.docs_context(room_id, tri, week)
        from ..core.translit import to_english
        full = store.load_students_full(room_id)
        # the file follows the language of the app: Arabic names in Arabic, English spelling in English
        names = [x["name"] for x in full] if b.get("lang") == "ar" else [x["english"] or to_english(x["name"]) for x in full]
        if not names:
            raise AppError("no_students", "This class has no students yet. Add them in Classes first.", status=409)
        out = self.doc_file("grading_sheet", grade.name, tri, week, extra=room.name)
        fmt = str(b.get("format", "docx"))
        if fmt in ("xlsx", "csv"):  # for the LMS: a plain table to fill on screen, never printed
            out = out.with_suffix("." + fmt)
            D.write_grade_table(out, names, subject=store.load_settings().subject, label=room.name, term=tri + 1, week=week)
            return self._result(out)
        D.fill_grading_sheet(D.template_path("grading_sheet"), out, {
            "term": tri + 1, "week": week, "date": _fmt_full(date.fromisoformat(ctx["start"])),
            "subject": store.load_settings().subject, "grade_label": room.name, "students": names})
        return self._result(out)

    def open_file(self, path: str, folder: bool = False) -> dict:
        """Open a file (or its folder) with the computer's own program. Only inside the data folder."""
        root = self._need_store().root.resolve()
        p = Path(path).resolve()
        if root not in p.parents and p != root:
            raise AppError("bad_path", "That file is not inside your data folder.", status=403)
        if not p.exists():
            raise AppError("file_missing", "The file is not there any more.", status=404)
        if p.is_file() and p.suffix.lower() not in OPENABLE:  # only our own kind of files, never a program
            raise AppError("bad_path", "That kind of file cannot be opened from here.", status=403)
        target = p.parent if folder and p.is_file() else p
        if os.environ.get("DLIS_NO_OPEN"):
            return {"opened": str(target)}
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except OSError as e:
            raise AppError("cannot_open", f"Could not open it: {e}") from e
        return {"opened": str(target)}

    # ------------------------------------------------------------ tasks
    def _tasks_path(self) -> Path:
        return self._need_store().root / "tasks.json"

    def _tasks_data(self) -> dict:
        store = self._need_store()
        data = store.read_json(self._tasks_path(), {}, check=_check_tasks) or {}
        data.setdefault("tasks", [])
        data.setdefault("dismissed", [])
        if not data.get("tracking_start"):
            data["tracking_start"] = date.today().isoformat()
            store.write_json(self._tasks_path(), data)
        return data

    def _save_tasks(self, data: dict) -> None:
        self._need_store().write_json(self._tasks_path(), data)

    def _auto_tasks(self, data: dict, today: date) -> list[dict]:
        """Lesson plans that are missing for weeks that have already started (or start next week)."""
        store = self._need_store()
        cal = self._calendar_service()
        pos = cal.position(today)
        if pos.get("state") != "in_term":
            return []
        structure, tt = store.load_structure(), store.load_timetable()
        used_rooms = {rid for row in tt.grid.values() for rid in row.values() if rid}
        grades = {}
        for r in structure.rooms:
            if r.id in used_rooms:
                grades[r.grade_id] = next((g for g in structure.grades if g.id == r.grade_id), None)
        tri, cur_week = pos["trimester"], pos["week"]
        track = date.fromisoformat(data["tracking_start"])
        weeks = {w["number"]: w for w in cal.trimester_weeks(tri)}
        first = max(1, next((n for n, w in sorted(weeks.items()) if date.fromisoformat(w["end"]) >= track), cur_week))
        out = []
        for n in range(first, cur_week + 2):
            w = weeks.get(n)
            if not w or w["school_days"] == 0:
                continue
            wstart = date.fromisoformat(w["start"])
            for gid, g in grades.items():
                if not g:
                    continue
                tid = f"lesson_plan:{gid}:{tri}:{n}"
                if tid in data["dismissed"] or self.doc_file("lesson_plan", g.name, tri, n).exists():
                    continue
                out.append({"id": tid, "auto": True, "kind": "lesson_plan", "title_key": "task_lesson_plan",
                            "grade": g.name, "grade_id": gid, "trimester": tri, "week": n,
                            "deadline": wstart.isoformat(), "importance": "medium", "done": False})
        return out

    def list_tasks(self, today: Optional[date] = None) -> dict:
        today = today or date.today()
        data = self._tasks_data()
        auto = self._auto_tasks(data, today)
        manual = data["tasks"]
        overdue = sum(1 for t in manual + auto if not t.get("done") and t.get("deadline") and t["deadline"] < today.isoformat())
        open_n = sum(1 for t in manual + auto if not t.get("done"))
        return {"tasks": manual, "auto": auto, "open": open_n, "overdue": overdue, "today": today.isoformat()}

    def add_task(self, b: dict) -> dict:
        title = " ".join(str(b.get("title", "")).split())
        if not title:
            raise AppError("need_title", "Write what the task is.")
        imp = b.get("importance") if b.get("importance") in IMPORTANCE else "medium"
        deadline = str(b.get("deadline") or "")
        if deadline:
            try:
                date.fromisoformat(deadline)
            except ValueError as e:
                raise AppError("invalid_data", "bad deadline") from e
        data = self._tasks_data()
        data["tasks"].append({"id": uuid.uuid4().hex[:10], "title": title, "importance": imp, "deadline": deadline,
                              "done": False, "created": date.today().isoformat()})
        self._save_tasks(data)
        return self.list_tasks()

    def update_task(self, task_id: str, b: dict) -> dict:
        if not is_safe_id(task_id):
            raise AppError("bad_id")
        data = self._tasks_data()
        t = next((x for x in data["tasks"] if x["id"] == task_id), None)
        if not t:
            raise AppError("task_not_found", status=404)
        if "done" in b:
            t["done"] = bool(b["done"])
        if "title" in b and str(b["title"]).strip():
            t["title"] = " ".join(str(b["title"]).split())
        if b.get("importance") in IMPORTANCE:
            t["importance"] = b["importance"]
        if "deadline" in b:
            t["deadline"] = str(b["deadline"] or "")
        self._save_tasks(data)
        return self.list_tasks()

    def delete_task(self, task_id: str) -> dict:
        data = self._tasks_data()
        data["tasks"] = [x for x in data["tasks"] if x["id"] != task_id]
        self._save_tasks(data)
        return self.list_tasks()

    def dismiss_task(self, task_id: str) -> dict:
        data = self._tasks_data()
        if task_id not in data["dismissed"]:
            data["dismissed"].append(task_id)
        self._save_tasks(data)
        return self.list_tasks()
