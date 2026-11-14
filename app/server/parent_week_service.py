"""The week plan parents see: homework, extra material (links) and quiz alerts, written by the teacher and approved before it is published.
It never contains the lesson plan. What was taught this week is shown to the teacher from the lesson log, so the teacher can mention it."""
from __future__ import annotations

import re
from datetime import date

from ..core.errors import AppError


def _lines(v, n=12, w=200):
    return [" ".join(str(x).split())[:w] for x in (v if isinstance(v, list) else str(v or "").split("\n")) if str(x).strip()][:n]


def _links(v):
    out = []
    for ln in _lines(v, 12, 400):
        title, _, url = ln.rpartition("|")
        url = url.strip()
        if re.fullmatch(r"https?://\S{3,300}", url):
            out.append({"title": (title.strip() or url)[:120], "url": url})
    return out


def _alerts(v):
    out = []
    for ln in _lines(v, 12, 200):
        title, _, day = ln.rpartition("|")
        day = day.strip()
        if title and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            out.append({"title": title.strip()[:120], "text": f"{title.strip()[:120]} · {day}", "date": day})
        elif ln:
            out.append({"title": ln[:120], "text": ln[:120], "date": ""})
    return out


class ParentWeekMixin:
    def _pw_path(self):
        return self._need_store().root / "parent_week.json"

    def _pw(self) -> dict:
        d = self._need_store().read_json(self._pw_path(), {}, check=lambda x: isinstance(x, dict) or (_ for _ in ()).throw(ValueError("bad"))) or {}
        return d

    def get_parent_week(self, room_id: str, tri: int, week: int) -> dict:
        self._room(room_id)
        cur = self._pw().get(f"{room_id}|{tri}|{week}", {})
        try:
            rng = self._calendar_service().week_dates(tri, week)
        except (IndexError, KeyError):
            rng = None
        topics = []
        if rng:
            topics = [e["topic"] for e in sorted(self._log_data()["entries"], key=self._log_key)
                      if e["room_id"] == room_id and rng[0].isoformat() <= e["date"] <= rng[1].isoformat() and e.get("topic")]
        return {"room_id": room_id, "trimester": tri, "week": week, "topics": list(dict.fromkeys(topics)),
                "homework": cur.get("homework", []), "material": cur.get("material", []), "quiz_alerts": cur.get("quiz_alerts", []), "approved": bool(cur.get("approved"))}

    def save_parent_week(self, b: dict, publish: bool | None = None) -> dict:
        room, tri, week = str(b.get("room_id", "")), int(b.get("trimester", 0)), int(b.get("week", 1))
        self._room(room)
        data = self._pw()
        old = data.get(f"{room}|{tri}|{week}", {})
        item = {"homework": _lines(b.get("homework")), "material": _links(b["material"]) if "material" in b else old.get("material", []), "quiz_alerts": _alerts(b.get("quiz_alerts")),
                "approved": data.get(f"{room}|{tri}|{week}", {}).get("approved", False)}
        if publish is not None:
            if self._cloud_cfg()["role"] not in ("teacher", "admin"):
                raise AppError("cloud_staff_only", "Sign in with a teacher account first.", status=403)
            item["approved"] = publish
            self._cloud_client().upsert("week_plans", [{"class_id": room, "trimester": tri, "week": week, "subject": self._need_store().load_settings().subject or "", "homework": item["homework"], "material": item["material"],
                                                       "quiz_alerts": item["quiz_alerts"], "approved": publish, "updated_at": date.today().isoformat()}], "class_id,trimester,week,subject")
        data[f"{room}|{tri}|{week}"] = item
        self._need_store().write_json(self._pw_path(), data)
        return self.get_parent_week(room, tri, week)
