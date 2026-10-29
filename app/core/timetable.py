"""Today's sessions, built from the fixed weekly grid plus one-off changes."""
from __future__ import annotations

from datetime import date

from .academic import AcademicCalendar
from .models import WEEKDAYS, Structure, Timetable


def sessions_on(d: date, tt: Timetable, cal: AcademicCalendar, structure: Structure) -> list[dict]:
    if not cal.is_school_day(d):
        return []
    day = WEEKDAYS[d.weekday()]
    override = tt.overrides.get(d.isoformat(), {}) or {}
    cancelled = {str(x) for x in override.get("cancel", [])}
    rooms = {r.id: r for r in structure.rooms}
    out = []
    for p in tt.periods:
        room_id = (tt.grid.get(day, {}) or {}).get(p.name, "")
        if room_id and p.name not in cancelled and room_id in rooms:
            out.append(_session(p, room_id, rooms, extra=False))
    for extra in override.get("extra", []):
        p = next((x for x in tt.periods if x.name == str(extra.get("period"))), None)
        room_id = extra.get("room_id", "")
        if p and room_id in rooms:
            out.append({**_session(p, room_id, rooms, extra=True), "kind": extra.get("kind", ""), "note": extra.get("note", "")})
    order = {p.name: i for i, p in enumerate(tt.periods)}
    out.sort(key=lambda s: order.get(s["period"], 99))
    return out


def cancelled_on(d: date, tt: Timetable, structure: Structure) -> list[dict]:
    """Normal lessons the teacher cancelled for this one day (shown greyed, with an undo button)."""
    override = tt.overrides.get(d.isoformat(), {}) or {}
    cancelled = {str(x) for x in override.get("cancel", [])}
    rooms = {r.id: r for r in structure.rooms}
    day = WEEKDAYS[d.weekday()]
    return [_session(p, (tt.grid.get(day, {}) or {})[p.name], rooms, extra=False) for p in tt.periods
            if p.name in cancelled and (tt.grid.get(day, {}) or {}).get(p.name) in rooms]


def _session(p, room_id, rooms, extra: bool) -> dict:
    r = rooms[room_id]
    return {"period": p.name, "start": p.start, "end": p.end, "room_id": room_id,
            "grade_id": r.grade_id, "extra": extra}


def room_session_days(room_id: str, tt: Timetable, working_days: list[str]) -> list[str]:
    return [d for d in working_days if room_id in (tt.grid.get(d, {}) or {}).values()]


def grade_session_days(grade_id: str, tt: Timetable, structure: Structure, working_days: list[str]) -> list[str]:
    ids = {r.id for r in structure.rooms if r.grade_id == grade_id}
    return [d for d in working_days if ids & set((tt.grid.get(d, {}) or {}).values())]


def scrub_timetable(tt: Timetable, structure: Structure) -> Timetable:
    """Remove references to rooms that no longer exist and cells for periods that no longer exist."""
    valid = {r.id for r in structure.rooms}
    names = {p.name for p in tt.periods}
    grid = {}
    for day, row in tt.grid.items():
        grid[day] = {k: (v if v in valid else "") for k, v in row.items() if k in names}
    tt.grid = grid
    return tt
