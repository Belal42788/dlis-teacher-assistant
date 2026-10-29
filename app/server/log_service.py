"""Lesson log: where each class stopped (topic and slide) and a note for next time. One entry per lesson."""
from __future__ import annotations

import uuid
from datetime import date

from ..core.errors import AppError
from ..core.models import is_safe_id


def _int(v, lo=1, hi=2000):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _check_log(d) -> None:
    if not isinstance(d, dict) or not all(isinstance(x, dict) and "room_id" in x for x in d.get("entries", [])):
        raise ValueError("lesson_log.json has the wrong shape")


class LogMixin:
    def _log_path(self):
        return self._need_store().root / "lesson_log.json"

    def _log_data(self) -> dict:
        data = self._need_store().read_json(self._log_path(), {}, check=_check_log) or {}
        data.setdefault("entries", [])
        return data

    @staticmethod
    def _log_key(e: dict):
        return (e.get("date", ""), str(e.get("period", "")), e.get("created", ""))

    def log_last(self) -> dict:
        """The newest entry of every class (what to continue from)."""
        last: dict = {}
        for e in sorted(self._log_data()["entries"], key=self._log_key):
            last[e["room_id"]] = e
        return {"last": last}

    def log_list(self, room: str = "", day: str = "") -> dict:
        items = self._log_data()["entries"]
        if room:
            items = [e for e in items if e["room_id"] == room]
        if day:
            items = [e for e in items if e["date"] == day]
        items = sorted(items, key=self._log_key, reverse=True)
        return {"entries": items[:200]}

    def log_save(self, b: dict) -> dict:
        room = str(b.get("room_id", ""))
        if room not in {r.id for r in self._need_store().load_structure().rooms}:
            raise AppError("room_not_found", status=404)
        day = str(b.get("date") or date.today().isoformat())
        try:
            date.fromisoformat(day)
        except ValueError as e:
            raise AppError("invalid_data", "bad date") from e
        period = str(b.get("period", ""))[:3]
        slide, total = _int(b.get("slide")), _int(b.get("total"))
        if slide and total and slide > total:
            raise AppError("slide_over_total", "The slide number is bigger than the number of slides.")
        fields = {"topic": " ".join(str(b.get("topic", "")).split())[:120], "slide": slide, "total": total,
                  "note": str(b.get("note", "")).strip()[:1000], "next_note": " ".join(str(b.get("next_note", "")).split())[:300]}
        if not (fields["topic"] or slide or fields["note"] or fields["next_note"]):
            raise AppError("log_empty", "Write at least the topic, the slide, or a note.")
        data = self._log_data()
        e = next((x for x in data["entries"] if x["room_id"] == room and x["date"] == day and str(x.get("period", "")) == period), None)
        if e:
            e.update(fields)
        else:
            e = {"id": uuid.uuid4().hex[:10], "room_id": room, "date": day, "period": period, "created": date.today().isoformat() + uuid.uuid4().hex[:4], **fields}
            data["entries"].append(e)
        self._need_store().write_json(self._log_path(), data)
        return {"entry": e, **self.log_last()}

    def log_delete(self, entry_id: str) -> dict:
        if not is_safe_id(entry_id):
            raise AppError("bad_id")
        data = self._log_data()
        data["entries"] = [x for x in data["entries"] if x["id"] != entry_id]
        self._need_store().write_json(self._log_path(), data)
        return self.log_last()
