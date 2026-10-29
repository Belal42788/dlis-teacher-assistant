"""Weekly checklist: for every grade, a fixed list of weekly jobs marked done / not done / not yet."""
from __future__ import annotations

from ..core.errors import AppError
from .docs_service import _safe

# Five jobs; three of them have two boxes ("did I make it?" and "did I send / upload it?").
GROUPS = [("attendance", ["attendance"]), ("presentation", ["presentation_made", "presentation_lms"]),
          ("lesson_plan", ["lesson_plan_made", "lesson_plan_sent"]), ("quiz", ["quiz_made", "quiz_sent"]), ("weekly_plan", ["weekly_plan"])]
TASKS = [k for _, cols in GROUPS for k in cols]
_OLD = {"presentation": "presentation_made", "lms": "presentation_lms", "lesson_plan": "lesson_plan_sent", "quiz": "quiz_sent"}  # first version
STATES = ("wait", "done", "no")


def _check(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("status", {}), dict):
        raise ValueError("weekly.json has the wrong shape")


class WeeklyMixin:
    def _weekly_path(self):
        return self._need_store().root / "weekly.json"

    def _weekly_data(self) -> dict:
        data = self._need_store().read_json(self._weekly_path(), {}, check=_check) or {}
        data.setdefault("status", {})
        for weeks in data["status"].values():       # marks from the first version keep their meaning
            for marks in weeks.values():
                for old, new in _OLD.items():
                    if old in marks and new not in marks:
                        marks[new] = marks.pop(old)
                    else:
                        marks.pop(old, None)
        return data

    def _made_files(self, grade, tri: int, week: int) -> dict:
        """Which of "my own" files exist already (so those boxes can tick themselves)."""
        store = self._need_store()
        base = store.root / "Documents" / _safe(grade.name)
        w = f"T{tri + 1}-W{week:02d}"
        slides = (self._plans().get("slides") or {}).get(f"{grade.id}|{tri}|{week}")
        return {"lesson_plan_made": (base / f"{w}_Lesson_Plan.docx").is_file(), "quiz_made": any(base.glob(f"{w}_Quiz*.docx")) if base.is_dir() else False,
                "presentation_made": bool(slides)}

    def get_weekly(self, tri: int, week: int) -> dict:
        store = self._need_store()
        struct = store.load_structure()
        grades = [g for g in struct.grades if any(r.grade_id == g.id for r in struct.rooms)]
        mine = self._weekly_data()["status"].get(f"{tri}|{week}", {})
        rows = []
        for g in grades:
            states = {t: (mine.get(g.id, {}) or {}).get(t, "wait") for t in TASKS}
            auto = {}
            for k, exists in self._made_files(g, tri, week).items():
                if exists and states[k] == "wait":
                    states[k] = "done"; auto[k] = True
            rows.append({"grade_id": g.id, "name": g.name, "states": states, "auto": auto})
        done = sum(1 for r in rows for v in r["states"].values() if v == "done")
        return {"tasks": TASKS, "groups": [{"id": gid, "cols": cols} for gid, cols in GROUPS], "rows": rows, "done": done, "total": len(rows) * len(TASKS)}

    def set_weekly(self, b: dict) -> dict:
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 1))
        task, state, gid = str(b.get("task", "")), str(b.get("state", "")), str(b.get("grade_id", ""))
        if task not in TASKS or state not in STATES:
            raise AppError("bad_value", "Unknown task or state.", status=400)
        grade = self._grade(gid)
        data = self._weekly_data()
        data["status"].setdefault(f"{tri}|{week}", {}).setdefault(grade.id, {})[task] = state
        self._need_store().write_json(self._weekly_path(), data)
        return self.get_weekly(tri, week)
