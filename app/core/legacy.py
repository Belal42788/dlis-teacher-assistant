"""Bring data from the first version of the app (v1 DLIS_Data folder) into the current data folder."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .errors import AppError
from .models import AgeBand, Grade, GradeSettings, Room, Stage, Timetable
from .presets import GRADE_PRESET_BY_ID, STAGE_PRESET_BY_ID
from .store import DataStore, _migrate_calendar, _migrate_timetable
from .structure_service import normalize


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def looks_like_legacy(folder: Path) -> bool:
    return (folder / "structure.json").exists() or (folder / "schedule.json").exists() or (folder / "calendar.json").exists()


def import_legacy(src: str | Path, store: DataStore, dry_run: bool = False) -> dict:
    src = Path(src).expanduser()
    if not src.is_dir() or not looks_like_legacy(src):
        raise AppError("not_legacy_folder", "This folder does not contain DLIS data (structure.json / schedule.json / calendar.json).")
    if src.resolve() == store.root:
        raise AppError("same_folder", "This is already your current data folder.")

    report = {"stages": 0, "grades": 0, "rooms": 0, "students": 0, "duplicates_removed": 0,
              "timetable": "skipped", "calendar": "skipped", "files_copied": 0, "notes": []}

    structure = store.load_structure()
    have_stage = {s.id for s in structure.stages}
    have_grade = {g.id for g in structure.grades}
    have_room = {r.id for r in structure.rooms}
    students_by_room: dict[str, list[str]] = {}

    raw = _load(src / "structure.json") or {}

    def first_seen(items):
        seen, out = set(), []
        for it in items:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            if it["id"] in seen:
                report["duplicates_removed"] += 1
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    for it in first_seen(raw.get("stages", [])):
        if it["id"] not in have_stage:
            preset = STAGE_PRESET_BY_ID.get(it["id"], {})
            structure.stages.append(Stage(id=it["id"], name=it.get("name", it["id"]),
                                          name_ar=preset.get("name_ar", ""), order=preset.get("order", len(structure.stages))))
            have_stage.add(it["id"]); report["stages"] += 1
    for it in first_seen(raw.get("grades", [])):
        if it["id"] not in have_grade and it.get("stage_id") in have_stage:
            preset = GRADE_PRESET_BY_ID.get(it["id"], {})
            try:
                settings = GradeSettings.model_validate(it.get("settings") or {})
            except Exception:
                settings = GradeSettings()
            structure.grades.append(Grade(id=it["id"], name=it.get("name", it["id"]), name_ar=preset.get("name_ar", ""),
                                          stage_id=it["stage_id"], order=preset.get("order", len(structure.grades)),
                                          settings=settings))
            have_grade.add(it["id"]); report["grades"] += 1
    # Students were stored inside each room (often repeated): merge every copy, keep order, drop repeats.
    for it in raw.get("rooms", []):
        if isinstance(it, dict) and it.get("id"):
            bucket = students_by_room.setdefault(it["id"], [])
            for n in it.get("students", []) or []:
                n = str(n).strip()
                if n and n not in bucket:
                    bucket.append(n)
    for it in first_seen(raw.get("rooms", [])):
        if it["id"] not in have_room and it.get("grade_id") in have_grade:
            structure.rooms.append(Room(id=it["id"], grade_id=it["grade_id"], name=it.get("name", it["id"])))
            have_room.add(it["id"]); report["rooms"] += 1

    # The timetable may use classes that were never in structure.json (for example KG): create them.
    sched_raw = _load(src / "schedule.json")
    if sched_raw:
        sched = _migrate_timetable(sched_raw)
        for row in sched.get("grid", {}).values():
            for room_id in row.values():
                if room_id and room_id not in have_room:
                    gid, _, letter = room_id.rpartition("-")
                    preset = GRADE_PRESET_BY_ID.get(gid)
                    if preset and gid and letter:
                        if preset["stage_id"] not in have_stage:
                            from .presets import STAGE_PRESETS
                            structure.stages.append(Stage(**next(s for s in STAGE_PRESETS if s["id"] == preset["stage_id"])))
                            have_stage.add(preset["stage_id"]); report["stages"] += 1
                        if gid not in have_grade:
                            structure.grades.append(Grade(id=gid, name=preset["name"], name_ar=preset["name_ar"],
                                                          stage_id=preset["stage_id"], order=preset["order"],
                                                          settings=GradeSettings(lms_stage_name=preset["name"],
                                                                                 age_band=AgeBand(preset["age_band"]))))
                            have_grade.add(gid); report["grades"] += 1
                        structure.rooms.append(Room(id=room_id, grade_id=gid, name=f"{preset['name']} {letter.upper()}"))
                        have_room.add(room_id); report["rooms"] += 1
                        report["notes"].append(f"created_room:{room_id}")

    structure = normalize(structure)

    # Students from the old per-room CSV files count too.
    for room in structure.rooms:
        names = list(students_by_room.get(room.id, []))
        for n in _csv_names(src / "rooms" / room.id / "students.csv"):
            if n not in names:
                names.append(n)
        if names and not store.load_students(room.id):
            students_by_room[room.id] = names
            report["students"] += len(names)
        else:
            students_by_room.pop(room.id, None)

    if sched_raw:
        current = store.load_timetable()
        if not current.periods and not any(any(r.values()) for r in current.grid.values()):
            tt = Timetable.model_validate(_migrate_timetable(sched_raw))
            from .timetable import scrub_timetable
            if not dry_run:
                store.save_timetable(scrub_timetable(tt, structure))
            report["timetable"] = "imported"
        else:
            report["timetable"] = "kept_current"

    cal_raw = _load(src / "calendar.json")
    if cal_raw:
        current_cal = store.load_calendar()
        if not current_cal.trimesters:
            from .models import Calendar
            cal = Calendar.model_validate(_migrate_calendar(cal_raw))
            if not dry_run:
                store.save_calendar(cal)
            report["calendar"] = "imported"
        else:
            report["calendar"] = "kept_current"

    if not dry_run:
        store.save_structure(structure)
        for rid, names in students_by_room.items():
            store.save_students(rid, names)
        # Anything the teacher already produced (week folders) is copied across untouched.
        for tree in ("grades",):
            if (src / tree).is_dir():
                report["files_copied"] += _copy_tree(src / tree, store.root / tree)
        rooms_src = src / "rooms"
        if rooms_src.is_dir():
            for room_dir in rooms_src.iterdir():
                if room_dir.is_dir():
                    for sub in room_dir.iterdir():
                        if sub.is_dir() and sub.name.startswith("T"):
                            report["files_copied"] += _copy_tree(sub, store.root / "rooms" / room_dir.name / sub.name)
    return report


def _csv_names(path: Path) -> list[str]:
    import csv
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
    except OSError:
        return []
    return [r[0].strip() for r in rows[1:] if r and r[0].strip()]


def _copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in src.rglob("*"):
        if p.is_file():
            target = dst / p.relative_to(src)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
                n += 1
    return n
