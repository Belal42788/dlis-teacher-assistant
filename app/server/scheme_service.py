"""Scheme of work: for every week of a trimester, what will be taught, from which source and which book pages.
It is the one list the lesson plans, quizzes, revision sheets and slides start from, so nothing is taught outside the plan."""
from __future__ import annotations

from datetime import date, timedelta

from ..core.errors import AppError
from ..core.timetable import sessions_on


class SchemeMixin:
    def scheme_get(self, grade_id: str, tri: int) -> dict:
        grade = self._grade(grade_id)
        cal = self._calendar_service()
        data = self._plans()
        titles = data["trimester"].get(f"{grade.id}|{tri}", {})
        extra = data.setdefault("scheme", {}).get(f"{grade.id}|{tri}", {})
        rooms = {r.id for r in self._need_store().load_structure().rooms if r.grade_id == grade.id}
        log = [e for e in self._log_data()["entries"] if e.get("room_id") in rooms]
        weeks = []
        for w in cal.trimester_weeks(tri):
            n = str(w["number"])
            taught = sorted({e["topic"] for e in log if w["start"] <= e.get("date", "") <= w["end"] and e.get("topic")})
            weeks.append({"week": w["number"], "start": w["start"], "end": w["end"], "school_days": w["school_days"],
                          "holiday": next((h["name"] for h in w["holidays"] if h["name"]), ""),
                          "topic": titles.get(n, ""), "pages": extra.get(n, {}).get("pages", ""), "source_id": extra.get(n, {}).get("source_id", ""),
                          "unit": extra.get(n, {}).get("unit", ""), "objectives": extra.get(n, {}).get("objectives", ""),
                          "has_plan": f"{grade.id}|{tri}|{w['number']}" in data["lesson"], "taught": taught})
        return {"weeks": weeks, "sources": [{"id": s["id"], "title": s.get("name") or s["id"]} for s in self.list_sources().get("sources", [])]}

    def scheme_put(self, b: dict) -> dict:
        grade = self._grade(str(b.get("grade_id", "")))
        tri = int(b.get("trimester", 0))
        valid = {w["number"] for w in self._calendar_service().trimester_weeks(tri)}
        if not valid:
            raise AppError("week_not_found", "Set the trimester dates in the Calendar first.", status=409)
        known = {s["id"] for s in self.list_sources().get("sources", [])}
        titles, extra = {}, {}
        for r in (b.get("weeks") or [])[:60]:
            n = int(r.get("week", 0))
            if n not in valid:
                continue
            topic = " ".join(str(r.get("topic", "")).split())[:160]
            pages = " ".join(str(r.get("pages", "")).split())[:60]
            sid = str(r.get("source_id", "")) if str(r.get("source_id", "")) in known else ""
            if topic:
                titles[str(n)] = topic
            unit = " ".join(str(r.get("unit", "")).split())[:80]
            objs = "\n".join(x.strip()[:200] for x in str(r.get("objectives", "")).replace("\r", "").split("\n") if x.strip())[:800]   # one objective per line
            if pages or sid or unit or objs:
                extra[str(n)] = {"pages": pages, "source_id": sid, "unit": unit, "objectives": objs}
        data = self._plans()
        data["trimester"][f"{grade.id}|{tri}"] = titles
        data.setdefault("scheme", {})[f"{grade.id}|{tri}"] = extra
        self._need_store().write_json(self._plans_path(), data)
        return self.scheme_get(grade.id, tri)

    def tomorrow_prep(self, today: str = "") -> dict:
        """For the evening alert: the next day with lessons (tomorrow, or the first day back), how many lessons, and which grades still have no lesson plan.
        Nothing is said when tomorrow is free and today was not a school day either (no alert every evening of a weekend)."""
        d0 = date.fromisoformat(today) if today else date.today()
        cal = self._calendar_service()
        store = self._need_store()
        self._seed_timetable(store)
        tt = self._with_fixed(store.load_timetable())
        structure = store.load_structure()
        names = {g.id: g.name for g in structure.grades}
        data = self._plans()
        for i in range(1, 8):
            d = d0 + timedelta(days=i)
            sessions = [s for s in sessions_on(d, tt, cal, structure) if not s.get("extra")]
            if not sessions:
                continue
            if i > 1 and not cal.is_school_day(d0):
                break
            pos = cal.position(d)
            grades = []
            for s in sessions:
                r = next((x for x in structure.rooms if x.id == s["room_id"]), None)
                if r and r.grade_id not in grades:
                    grades.append(r.grade_id)
            missing = []
            if pos.get("state") == "in_term":
                missing = [names.get(g, g) for g in grades if f"{g}|{pos['trimester']}|{pos['week']}" not in data["lesson"]]
            return {"found": True, "date": d.isoformat(), "tomorrow": i == 1, "lessons": len(sessions), "missing": missing}
        return {"found": False}

    def scheme_objectives(self, grade_id, topic) -> str:
        """The curriculum objectives (and unit) planned for a topic of this grade, one per line."""
        topic = " ".join(str(topic or "").split()).lower()
        if not topic or not grade_id:
            return ""
        data = self._plans()
        for key, titles in data["trimester"].items():
            if not key.startswith(f"{grade_id}|"):
                continue
            for n, title in titles.items():
                e = data.get("scheme", {}).get(key, {}).get(n, {})
                if title.lower() == topic and e.get("objectives"):
                    return e["objectives"]
        return ""

    def scheme_source(self, grade_id, topic) -> tuple[str, str]:
        """The source and pages planned for a topic of this grade, so the writing helpers stay inside them."""
        topic = " ".join(str(topic or "").split()).lower()
        if not topic or not grade_id:
            return "", ""
        try:
            data = self._plans()
        except AppError:
            return "", ""
        for key, titles in data["trimester"].items():
            if not key.startswith(f"{grade_id}|"):
                continue
            for n, title in titles.items():
                e = data.get("scheme", {}).get(key, {}).get(n, {})
                if title.lower() == topic and e.get("source_id"):
                    return e["source_id"], e.get("pages", "")
        return "", ""

    def week_prep_status(self, today: str = "") -> dict:
        """For the Today page: of the classes I teach this week, how many already have their lesson plan made."""
        d_now = date.fromisoformat(today) if today else date.today()
        cal = self._calendar_service()
        pos = cal.position(d_now)
        if pos.get("state") != "in_term":
            return {"state": pos.get("state", "no_calendar"), "grades": [], "ready": 0, "total": 0}
        tri, week = pos["trimester"], pos["week"]
        w = next((x for x in cal.trimester_weeks(tri) if x["number"] == week), None)
        store = self._need_store()
        self._seed_timetable(store)
        tt = self._with_fixed(store.load_timetable())
        structure = store.load_structure()
        names = {g.id: g.name for g in structure.grades}
        grades, d = [], date.fromisoformat(w["start"]) if w else d_now
        end = date.fromisoformat(w["end"]) if w else d_now
        seen = []
        while d <= end:
            for s in sessions_on(d, tt, cal, structure):
                r = next((x for x in structure.rooms if x.id == s["room_id"]), None)
                if r and not s.get("extra") and r.grade_id not in seen:
                    seen.append(r.grade_id)
            d += timedelta(days=1)
        data = self._plans()
        titles = {g: data["trimester"].get(f"{g}|{tri}", {}) for g in seen}
        for g in seen:
            grades.append({"grade_id": g, "name": names.get(g, g), "topic": titles[g].get(str(week), ""),
                           "has_plan": f"{g}|{tri}|{week}" in data["lesson"]})
        return {"state": "in_term", "trimester": tri, "week": week, "grades": grades,
                "ready": sum(1 for g in grades if g["has_plan"]), "total": len(grades)}
