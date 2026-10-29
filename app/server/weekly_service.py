"""Weekly checklist: for every grade, a fixed list of weekly jobs marked done / not done / not yet."""
from __future__ import annotations

from ..core.errors import AppError

TASKS = ["attendance", "presentation", "lms", "lesson_plan", "quiz", "weekly_plan"]
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
        return data

    def get_weekly(self, tri: int, week: int) -> dict:
        store = self._need_store()
        struct = store.load_structure()
        grades = [g for g in struct.grades if any(r.grade_id == g.id for r in struct.rooms)]
        mine = self._weekly_data()["status"].get(f"{tri}|{week}", {})
        rows = [{"grade_id": g.id, "name": g.name, "states": {t: (mine.get(g.id, {}) or {}).get(t, "wait") for t in TASKS}} for g in grades]
        done = sum(1 for r in rows for v in r["states"].values() if v == "done")
        return {"tasks": TASKS, "rows": rows, "done": done, "total": len(rows) * len(TASKS)}

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
