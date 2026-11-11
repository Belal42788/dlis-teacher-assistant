"""The teacher's own reminders ("print the quiz", "meet the coordinator"), kept in the data folder."""
from __future__ import annotations

import re
import uuid
from datetime import date

from ..core.errors import AppError
from ..core.models import is_safe_id

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _check_alarms(d) -> None:
    if not isinstance(d, dict) or not all(isinstance(x, dict) for x in d.get("items", [])):
        raise ValueError("reminders.json has the wrong shape")


class AlarmsMixin:
    def _alarms_path(self):
        return self._need_store().root / "reminders.json"

    def _alarms_data(self) -> dict:
        data = self._need_store().read_json(self._alarms_path(), {}, check=_check_alarms) or {}
        data.setdefault("items", [])
        return data

    def list_alarms(self) -> dict:
        return {"items": self._alarms_data()["items"], "today": date.today().isoformat()}

    @staticmethod
    def _clean_alarm(b: dict) -> dict:
        text = " ".join(str(b.get("text", "")).split())[:160]
        if not text:
            raise AppError("need_title", "Write what the reminder is.")
        time = str(b.get("time", ""))
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time):
            raise AppError("bad_time", "Choose the time.")
        days = [d for d in DAYS if d in (b.get("days") or [])]
        on = str(b.get("date") or "")
        if not days:  # one time only: needs a date
            try:
                date.fromisoformat(on)
            except ValueError as e:
                raise AppError("bad_date", "Choose the date, or the days of the week.") from e
        return {"text": text, "time": time, "days": days, "date": "" if days else on}

    def add_alarm(self, b: dict) -> dict:
        row = self._clean_alarm(b)
        data = self._alarms_data()
        data["items"].append({"id": uuid.uuid4().hex[:10], **row, "enabled": True})
        self._need_store().write_json(self._alarms_path(), data)
        return self.list_alarms()

    def update_alarm(self, alarm_id: str, b: dict) -> dict:
        """Switch it on or off, or (when the text/time/days are sent) change what it says and when it rings."""
        if not is_safe_id(alarm_id):
            raise AppError("bad_id")
        data = self._alarms_data()
        a = next((x for x in data["items"] if x["id"] == alarm_id), None)
        if not a:
            raise AppError("task_not_found", status=404)
        if "text" in b or "time" in b:
            a.update(self._clean_alarm({**a, **b}))
        if "enabled" in b:
            a["enabled"] = bool(b["enabled"])
        self._need_store().write_json(self._alarms_path(), data)
        return self.list_alarms()

    def delete_alarm(self, alarm_id: str) -> dict:
        data = self._alarms_data()
        data["items"] = [x for x in data["items"] if x["id"] != alarm_id]
        self._need_store().write_json(self._alarms_path(), data)
        return self.list_alarms()
