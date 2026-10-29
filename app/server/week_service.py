"""What the teacher planned for a class on a given day (topic, slides), and the sheet for a substitute teacher."""
from __future__ import annotations

from datetime import date, datetime

from ..core import documents as D
from ..core.errors import AppError


def _t12(hhmm: str) -> str:
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return hhmm or ""


class WeekMixin:
    def _plan_for(self, grade_id: str, d: date) -> dict:
        """Topic / objectives / activities / slide count for the class's grade in the week that contains `d` ({} when unknown)."""
        try:
            pos = self._calendar_service().position(d)
            if pos.get("state") != "in_term":
                return {}
            tri, week = int(pos["trimester"]), int(pos["week"])
            data = self._plans()
            key = f"{grade_id}|{tri}|{week}"
            lp = data["lesson"].get(key) or {}
            topic = lp.get("topic") or (data["trimester"].get(f"{grade_id}|{tri}", {}) or {}).get(str(week), "")
            sl = (data.get("slides") or {}).get(key) or {}
            out = {"topic": topic, "objectives": lp.get("objectives", ""), "activities": lp.get("activities", ""),
                   "slides": sl.get("count") or None, "tri": tri, "week": week}
            return {k: v for k, v in out.items() if v not in ("", None)}
        except (AppError, KeyError, ValueError, TypeError):
            return {}

    def make_cover_sheet(self, b: dict) -> dict:
        store = self._need_store()
        try:
            d = date.fromisoformat(str(b.get("date") or date.today().isoformat()))
        except ValueError as e:
            raise AppError("invalid_data", "bad date") from e
        today = self.today(d.isoformat())
        if not today["sessions"]:
            raise AppError("no_sessions", "There are no lessons on this day.", status=409)
        s = store.load_settings()
        last = self.log_last()["last"]
        structure = store.load_structure()
        lessons = []
        for x in today["sessions"]:
            room = next((r for r in structure.rooms if r.id == x["room_id"]), None)
            plan = x.get("plan") or {}
            lg = last.get(x["room_id"]) or {}
            lessons.append({"period": x["period"], "start": _t12(x.get("start", "")), "end": _t12(x.get("end", "")),
                            "room": room.name if room else x["room_id"], "students": len(store.load_students(x["room_id"])) if room else 0,
                            "topic": plan.get("topic", ""), "objectives": plan.get("objectives", ""), "activities": plan.get("activities", ""),
                            "slides": plan.get("slides"), "last_topic": lg.get("topic", ""), "last_slide": lg.get("slide"), "last_total": lg.get("total"),
                            "remember": lg.get("next_note", "")})
        out = store.root / "Documents" / "Cover_Sheets" / f"{d.isoformat()}_Cover_Sheet.docx"
        D.fill_cover(D.template_path("revision"), out, {"date": d.strftime("%A, %d %B %Y"), "teacher": s.teacher_name, "subject": s.subject, "lessons": lessons})
        res = self._result(out)
        res["lessons"] = len(lessons)
        return res
