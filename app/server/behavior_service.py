"""Behaviour notes: a quick note about a student (something good, or something to follow up). Stays on this computer."""
from __future__ import annotations

import uuid
from datetime import date

from ..core.errors import AppError
from ..core.models import is_safe_id

KINDS = ("good", "concern")


def _check(d) -> None:
    if not isinstance(d, dict) or not all(isinstance(x, dict) and "room_id" in x and "student" in x for x in d.get("notes", [])):
        raise ValueError("behavior.json has the wrong shape")


class BehaviorMixin:
    def _behavior_path(self):
        return self._need_store().root / "behavior.json"

    def _behavior_data(self) -> dict:
        data = self._need_store().read_json(self._behavior_path(), {}, check=_check) or {}
        data.setdefault("notes", [])
        return data

    def _class_names(self, room: str) -> list[str]:
        store = self._need_store()
        if room not in {r.id for r in store.load_structure().rooms}:
            raise AppError("room_not_found", status=404)
        return [x["name"] for x in store.load_students_full(room)]

    def behavior_list(self, room: str) -> dict:
        names = self._class_names(room)
        notes = sorted((n for n in self._behavior_data()["notes"] if n["room_id"] == room), key=lambda n: (n["date"], n["id"]), reverse=True)
        counts = {n: {"good": 0, "concern": 0, "open": 0} for n in names}
        for n in notes:
            c = counts.get(n["student"])
            if c is not None:
                c[n["kind"]] += 1
                c["open"] += 1 if n["kind"] == "concern" and not n.get("done") else 0
        return {"notes": notes[:500], "students": names, "counts": counts}

    def behavior_save(self, b: dict) -> dict:
        room, student = str(b.get("room_id", "")), str(b.get("student", "")).strip()
        if student not in self._class_names(room):
            raise AppError("student_not_found", "That student is not in this class.", status=404)
        kind = str(b.get("kind", "good"))
        if kind not in KINDS:
            raise AppError("invalid_data", "bad kind")
        note = " ".join(str(b.get("note", "")).split())[:500]
        if not note:
            raise AppError("note_empty", "Write the note first.")
        day = str(b.get("date") or date.today().isoformat())
        try:
            date.fromisoformat(day)
        except ValueError as e:
            raise AppError("invalid_data", "bad date") from e
        data = self._behavior_data()
        e = next((x for x in data["notes"] if x["id"] == b.get("id")), None) if b.get("id") else None
        if b.get("id") and not e:
            raise AppError("note_not_found", status=404)
        fields = {"room_id": room, "student": student, "kind": kind, "note": note, "date": day, "done": bool(b.get("done")) and kind == "concern"}
        if e:
            e.update(fields)
        else:
            e = {"id": uuid.uuid4().hex[:10], **fields}
            data["notes"].append(e)
        self._need_store().write_json(self._behavior_path(), data)
        return {"note": e}

    def behavior_done(self, note_id: str, done: bool) -> dict:
        if not is_safe_id(note_id):
            raise AppError("bad_id")
        data = self._behavior_data()
        e = next((x for x in data["notes"] if x["id"] == note_id), None)
        if not e:
            raise AppError("note_not_found", status=404)
        e["done"] = bool(done) and e["kind"] == "concern"
        self._need_store().write_json(self._behavior_path(), data)
        return {"note": e}

    def behavior_delete(self, note_id: str) -> dict:
        if not is_safe_id(note_id):
            raise AppError("bad_id")
        data = self._behavior_data()
        data["notes"] = [x for x in data["notes"] if x["id"] != note_id]
        self._need_store().write_json(self._behavior_path(), data)
        return {"ok": True}
