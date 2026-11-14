"""The school day's shape: lesson times, breakfast, break, prayer break and the late duty.
The school's own times come with the program (resources/bell_schedule.json). A teacher can change them for this computer
(lesson length, number of lessons, break, prayer, end of day); the change is kept in the data folder and can be undone."""
from __future__ import annotations

import re

from ..core import paths
from ..core.errors import AppError

KINDS = ("breakfast", "break", "prayer", "late")
MAX_LESSONS = 12
_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _mins(v, what: str) -> int:
    v = str(v or "")
    if not _HM.match(v):
        raise AppError("bell_bad_time", f"{what}: time must look like 08:30.", status=400)
    return int(v[:2]) * 60 + int(v[3:])


def clean_bell(raw: dict) -> dict:
    """A bell schedule in the shape the program uses, or an AppError saying what is wrong."""
    if not isinstance(raw, dict):
        raise AppError("bell_bad_time", "The schedule is missing.", status=400)
    periods = raw.get("periods")
    if not isinstance(periods, list) or not 1 <= len(periods) <= MAX_LESSONS:
        raise AppError("bell_count", f"Use between 1 and {MAX_LESSONS} lessons.", status=400)
    out: dict = {"periods": [{"name": str(i + 1), "start": str(p.get("start", "")), "end": str(p.get("end", ""))} for i, p in enumerate(periods)]}
    spans = []   # (start, end, label)
    for p in out["periods"]:
        a, b = _mins(p["start"], p["name"]), _mins(p["end"], p["name"])
        if b <= a:
            raise AppError("bell_bad_time", f"Lesson {p['name']} must end after it starts.", status=400)
        spans.append((a, b, p["name"]))
    names = [p["name"] for p in out["periods"]]
    for kind in KINDS:
        s = raw.get(kind)
        if not s:
            continue
        a, b = _mins(s.get("start"), kind), _mins(s.get("end"), kind)
        if b <= a:
            raise AppError("bell_bad_time", f"{kind} must end after it starts.", status=400)
        item = {"start": str(s["start"]), "end": str(s["end"])}
        if kind == "breakfast":
            item = {"before": names[0], **item}
        elif kind in ("break", "prayer"):
            after = str(s.get("after", ""))
            if after not in names:
                raise AppError("bell_count", f"{kind} must come after one of the lessons.", status=400)
            item = {"after": after, **item}
        out[kind] = item
        spans.append((a, b, kind))
    spans.sort()
    for first, second in zip(spans, spans[1:]):
        if second[0] < first[1]:
            raise AppError("bell_overlap", "Two parts of the day overlap.", status=400)
    return out


class BellMixin:
    def _bell_path(self):
        return self._need_store().root / "bell_schedule.json"

    def _bell_custom(self):
        try:
            f = self._bell_path()
        except AppError:
            return None
        if not f.is_file():
            return None
        data = self._need_store().read_json(f, None)
        try:
            return clean_bell(data)
        except AppError:
            return None   # a damaged file never stops the program: the school's times are used

    def _bell(self) -> dict:
        return self._bell_custom() or paths.bell_schedule()

    def get_bell(self) -> dict:
        custom = self._bell_custom()
        return {"bell": custom or paths.bell_schedule(), "default": paths.bell_schedule(), "custom": bool(custom)}

    def put_bell(self, b: dict) -> dict:
        clean = clean_bell((b or {}).get("bell"))
        if clean == {k: v for k, v in paths.bell_schedule().items() if k in ("periods", *KINDS)}:
            return self.reset_bell()   # same as the school's: nothing to keep
        self._need_store().write_json(self._bell_path(), clean)
        return self.get_bell()

    def reset_bell(self) -> dict:
        f = self._bell_path()
        if f.is_file():
            f.unlink()
        return self.get_bell()
