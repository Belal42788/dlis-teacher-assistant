"""Data models. Everything the app saves goes through these."""
from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 2

SCHOOL_WEEK = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]  # how people here read a week
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]  # python weekday() order
DEFAULT_WORKING_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def is_safe_id(value: str) -> bool:
    return bool(_ID_RE.match(value or ""))


def check_iso_date(value: str) -> str:
    if value in ("", None):
        return ""
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"not a date (YYYY-MM-DD): {value!r}")
    return value


class _Base(BaseModel):
    # Unknown fields are ignored so files written by newer versions still open.
    model_config = ConfigDict(extra="ignore")


class AgeBand(str, Enum):
    KG = "KG"
    LOWER_PRIMARY = "LOWER_PRIMARY"
    UPPER_PRIMARY = "UPPER_PRIMARY"
    PREPARATORY = "PREPARATORY"
    SECONDARY = "SECONDARY"


# ---------------------------------------------------------------- settings

class Settings(_Base):
    schema_version: int = SCHEMA_VERSION
    setup_done: bool = False
    teacher_name: str = ""
    school_name: str = "Dar Luqman Al-Hakim International School"
    subject: str = ""
    # Rarely a teacher has more than one subject; extra names are just offered in pick-lists.
    extra_subjects: list[str] = Field(default_factory=list)
    working_days: list[str] = Field(default_factory=lambda: list(DEFAULT_WORKING_DAYS))
    ai: dict = Field(default_factory=dict)  # filled in a later phase

    @field_validator("working_days")
    @classmethod
    def _days(cls, v: list[str]) -> list[str]:
        clean = [d for d in SCHOOL_WEEK if d in v]
        if not clean:
            raise ValueError("at least one working day is required")
        return clean


# ---------------------------------------------------------------- structure

class GradeSettings(_Base):
    lms_stage_name: str = ""
    age_band: AgeBand = AgeBand.UPPER_PRIMARY
    period_minutes: int = Field(default=40, ge=5, le=240)
    textbook: str = ""
    grading_maximums: dict[str, int] = Field(
        default_factory=lambda: {"Behavior": 10, "Attendance": 10, "Classwork": 15, "Homework": 15, "Quiz Score": 20}
    )


class Stage(_Base):
    id: str
    name: str
    name_ar: str = ""
    order: int = 0


class Grade(_Base):
    id: str
    name: str
    name_ar: str = ""
    stage_id: str
    order: int = 0
    settings: GradeSettings = Field(default_factory=GradeSettings)


class Room(_Base):
    id: str
    grade_id: str
    name: str  # e.g. "Grade 4 A"
    subject: str = ""  # empty = the teacher's main subject


class Structure(_Base):
    schema_version: int = SCHEMA_VERSION
    stages: list[Stage] = Field(default_factory=list)
    grades: list[Grade] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)


# ---------------------------------------------------------------- timetable

class Period(_Base):
    name: str
    start: str = ""  # HH:MM or empty
    end: str = ""

    @field_validator("start", "end")
    @classmethod
    def _time(cls, v: str) -> str:
        if v and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("time must look like 08:30")
        return v


class Timetable(_Base):
    schema_version: int = SCHEMA_VERSION
    periods: list[Period] = Field(default_factory=list)
    # grid[day][period_name] = room_id  ("" = free)
    grid: dict[str, dict[str, str]] = Field(default_factory=dict)
    # overrides["2026-10-12"] = {"cancel": ["3"], "extra": [{"period": "3", "room_id": "g4-a"}]}
    overrides: dict[str, dict] = Field(default_factory=dict)
    # duties["Monday"] = ["break"]  ("break" = break-time duty after period 4, "late" = end-of-day duty)
    duties: dict[str, list[str]] = Field(default_factory=dict)
    seeded: str = ""  # id of the ready-made school timetable that was applied once


# ---------------------------------------------------------------- calendar

class Trimester(_Base):
    name: str
    start: str = ""
    end: str = ""
    week1_start: str = ""  # optional: if the first teaching week doesn't start on the normal week day

    _v = field_validator("start", "end", "week1_start")(check_iso_date)


class Holiday(_Base):
    start: str
    end: str = ""  # empty = same day
    name: str = ""

    _v = field_validator("start", "end")(check_iso_date)


class Event(_Base):
    date: str
    name: str

    _v = field_validator("date")(check_iso_date)


class Calendar(_Base):
    schema_version: int = SCHEMA_VERSION
    academic_year: str = ""
    trimesters: list[Trimester] = Field(default_factory=list)
    holidays: list[Holiday] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)


def default_period_names(n: int) -> list[Period]:
    return [Period(name=str(i + 1)) for i in range(n)]

