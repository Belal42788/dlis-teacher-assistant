"""Seating chart: a grid of seats for each class, with a student in each seat. Stays on this computer."""
from __future__ import annotations

from ..core.errors import AppError

MAX_SIDE = 12


def _check(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("rooms", {}), dict):
        raise ValueError("seating.json has the wrong shape")


class SeatingMixin:
    def _seating_path(self):
        return self._need_store().root / "seating.json"

    def _seating_data(self) -> dict:
        data = self._need_store().read_json(self._seating_path(), {}, check=_check) or {}
        data.setdefault("rooms", {})
        return data

    def seating_get(self, room: str) -> dict:
        names = self._class_names(room)
        chart = self._seating_data()["rooms"].get(room) or {}
        rows, cols = int(chart.get("rows") or 5), int(chart.get("cols") or 6)
        seats = {k: v for k, v in (chart.get("seats") or {}).items() if v in names}   # a student who left the class loses the seat
        return {"rows": rows, "cols": cols, "seats": seats, "students": names, "saved": bool(chart)}

    def seating_save(self, b: dict) -> dict:
        room = str(b.get("room_id", ""))
        names = set(self._class_names(room))
        try:
            rows, cols = int(b.get("rows")), int(b.get("cols"))
        except (TypeError, ValueError) as e:
            raise AppError("invalid_data", "rows and columns must be numbers") from e
        if not (1 <= rows <= MAX_SIDE and 1 <= cols <= MAX_SIDE):
            raise AppError("invalid_data", f"rows and columns must be between 1 and {MAX_SIDE}")
        seats, used = {}, set()
        for key, name in (b.get("seats") or {}).items():
            try:
                r, c = (int(x) for x in str(key).split("-"))
            except ValueError as e:
                raise AppError("invalid_data", "bad seat") from e
            if not (0 <= r < rows and 0 <= c < cols):
                continue   # the grid was made smaller: that seat is gone
            if name not in names:
                raise AppError("student_not_found", "That student is not in this class.", status=404)
            if name in used:
                raise AppError("invalid_data", "A student can sit in one seat only.")
            used.add(name)
            seats[f"{r}-{c}"] = name
        data = self._seating_data()
        data["rooms"][room] = {"rows": rows, "cols": cols, "seats": seats}
        self._need_store().write_json(self._seating_path(), data)
        return self.seating_get(room)
