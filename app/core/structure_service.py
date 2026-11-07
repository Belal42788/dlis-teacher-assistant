"""Stages, grades and rooms: build from presets, validate, keep everything consistent."""
from __future__ import annotations

import re

from .errors import AppError
from .models import AgeBand, Grade, GradeSettings, Room, Stage, Structure, is_safe_id
from .presets import GRADE_PRESET_BY_ID, GRADE_PRESETS, ROOM_LETTERS, STAGE_PRESETS


def build_from_selection(selection: dict[str, list[str]], existing: Structure | None = None) -> Structure:
    """selection = {"g4": ["A", "B"], "kg2": ["A"]}.

    Existing grades and rooms are kept (with their students and settings); only missing ones are added.
    """
    s = existing.model_copy(deep=True) if existing else Structure()
    have_stage = {x.id for x in s.stages}
    have_grade = {x.id for x in s.grades}
    have_room = {x.id for x in s.rooms}
    for gid, letters in selection.items():
        preset = GRADE_PRESET_BY_ID.get(gid)
        if not preset:
            raise AppError("unknown_grade", f"Unknown grade preset: {gid}")
        if preset["stage_id"] not in have_stage:
            sp = next(x for x in STAGE_PRESETS if x["id"] == preset["stage_id"])
            s.stages.append(Stage(**sp))
            have_stage.add(sp["id"])
        if gid not in have_grade:
            s.grades.append(Grade(
                id=gid, name=preset["name"], name_ar=preset["name_ar"], stage_id=preset["stage_id"],
                order=preset["order"],
                settings=GradeSettings(lms_stage_name=preset["name"], age_band=AgeBand(preset["age_band"]))))
            have_grade.add(gid)
        for letter in letters:
            letter = str(letter).strip().upper()[:1]
            if not letter or letter not in ROOM_LETTERS:
                continue
            rid = f"{gid}-{letter.lower()}"
            if rid not in have_room:
                s.rooms.append(Room(id=rid, grade_id=gid, name=f"{preset['name']} {letter}"))
                have_room.add(rid)
    return normalize(s)


def normalize(s: Structure) -> Structure:
    """Check ids and links; sort for display. Raises AppError with a clear code when something is wrong."""
    for kind, items in (("stage", s.stages), ("grade", s.grades), ("room", s.rooms)):
        seen = set()
        for it in items:
            if not is_safe_id(it.id):
                raise AppError("bad_id", f"Invalid {kind} id: {it.id!r}")
            if it.id in seen:
                raise AppError("duplicate_id", f"Duplicate {kind} id: {it.id}")
            seen.add(it.id)
    stage_ids = {x.id for x in s.stages}
    grade_ids = {x.id for x in s.grades}
    for g in s.grades:
        if g.stage_id not in stage_ids:
            raise AppError("missing_stage", f"Grade {g.name} points to a stage that does not exist")
    for r in s.rooms:
        if r.grade_id not in grade_ids:
            raise AppError("missing_grade", f"Class {r.name} points to a grade that does not exist")
    return sort_structure(s)


def _natural(text: str) -> list:
    """'Grade 10 B' sorts after 'Grade 9 A' (numbers compared as numbers, not letters)."""
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", text or "")]


def sort_structure(s: Structure) -> Structure:
    """Youngest first: KG1, KG2, Grade 1 ... Grade 12, and A, B, C inside each grade."""
    stage_rank = {p["id"]: p["order"] for p in STAGE_PRESETS}
    s.stages.sort(key=lambda x: (stage_rank.get(x.id, 100 + x.order), _natural(x.name)))
    grade_rank = {g["id"]: g["order"] for g in GRADE_PRESETS}
    srank = {x.id: i for i, x in enumerate(s.stages)}
    s.grades.sort(key=lambda g: (srank.get(g.stage_id, 99), grade_rank.get(g.id, 100 + g.order), _natural(g.name)))
    grank = {g.id: i for i, g in enumerate(s.grades)}
    s.rooms.sort(key=lambda r: (grank.get(r.grade_id, 999), _natural(r.name)))
    return s


def preset_payload() -> dict:
    return {"stages": STAGE_PRESETS, "grades": GRADE_PRESETS, "room_letters": list(ROOM_LETTERS)}
