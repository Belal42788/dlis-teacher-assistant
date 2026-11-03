"""The ONE place that knows what week it is. Every screen and document asks this module."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .models import WEEKDAYS, Calendar, Holiday


def _d(value: str) -> Optional[date]:
    return date.fromisoformat(value) if value else None


class AcademicCalendar:
    def __init__(self, calendar: Calendar, working_days: list[str]):
        self.cal = calendar
        self.working = {WEEKDAYS.index(d) for d in working_days if d in WEEKDAYS}
        if not self.working:
            self.working = {6, 0, 1, 2, 3}
        self.week_start_wd = self._find_week_start()

    # ------------------------------------------------------------ weekdays
    def _find_week_start(self) -> int:
        """The first working day after the longest run of days off (Fri+Sat -> Sunday)."""
        if len(self.working) == 7:
            return 0
        best, best_gap = None, -1
        for c in sorted(self.working):
            gap, k = 0, (c - 1) % 7
            while k not in self.working:
                gap += 1
                k = (k - 1) % 7
            if gap > best_gap:
                best, best_gap = c, gap
        return best if best is not None else 6

    def is_working_weekday(self, d: date) -> bool:
        return d.weekday() in self.working

    def week_start_of(self, d: date) -> date:
        return d - timedelta(days=(d.weekday() - self.week_start_wd) % 7)

    def _first_working_on_or_after(self, d: date) -> date:
        for _ in range(7):
            if self.is_working_weekday(d):
                return d
            d += timedelta(days=1)
        return d

    # ------------------------------------------------------------ holidays / events
    def holiday_on(self, d: date) -> Optional[Holiday]:
        for h in self.cal.holidays:
            start = _d(h.start)
            end = _d(h.end) or start
            if start and end and start <= d <= end:
                return h
        return None

    def events_on(self, d: date) -> list[str]:
        return [e.name for e in self.cal.events if e.date == d.isoformat()]

    def trimester_index_on(self, d: date) -> Optional[int]:
        for i, t in enumerate(self.cal.trimesters):
            s, e = _d(t.start), _d(t.end)
            if s and e and s <= d <= e:
                return i
        return None

    def is_school_day(self, d: date) -> bool:
        return (self.is_working_weekday(d) and self.holiday_on(d) is None
                and self.trimester_index_on(d) is not None)

    # ------------------------------------------------------------ weeks
    def week1_start(self, tri_idx: int) -> Optional[date]:
        t = self.cal.trimesters[tri_idx]
        if t.week1_start:
            return _d(t.week1_start)
        s = _d(t.start)
        if not s:
            return None
        return self.week_start_of(self._first_working_on_or_after(s))

    def trimester_weeks(self, tri_idx: int) -> list[dict]:
        t = self.cal.trimesters[tri_idx]
        start, end = self.week1_start(tri_idx), _d(t.end)
        if not start or not end:
            return []
        weeks, n = [], 1
        while start <= end and n < 60:
            days = [start + timedelta(days=i) for i in range(7)]
            work = [x for x in days if self.is_working_weekday(x)]
            if work:
                weeks.append({
                    "number": n,
                    "start": work[0].isoformat(),
                    "end": work[-1].isoformat(),
                    "school_days": sum(1 for x in work if self.is_school_day(x)),
                    "holidays": [{"date": x.isoformat(), "name": self.holiday_on(x).name}
                                 for x in work if self.holiday_on(x)],
                })
            start += timedelta(days=7)
            n += 1
        return weeks

    def week_dates(self, tri_idx: int, week_number: int) -> Optional[tuple[date, date]]:
        for w in self.trimester_weeks(tri_idx):
            if w["number"] == week_number:
                return date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
        return None

    def position(self, today: date) -> dict:
        """Where are we in the school year? Used by Today and by every plan we create."""
        tris = [(i, _d(t.start), _d(t.end)) for i, t in enumerate(self.cal.trimesters)]
        tris = [(i, s, e) for i, s, e in tris if s and e]
        if not tris:
            return {"state": "no_calendar"}
        idx = self.trimester_index_on(today)
        if idx is not None:
            w1 = self.week1_start(idx)
            number = max(1, ((self.week_start_of(today) - w1).days // 7) + 1) if w1 else 1
            rng = self.week_dates(idx, number)
            return {"state": "in_term", "trimester": idx, "trimester_name": self.cal.trimesters[idx].name,
                    "week": number,
                    "week_start": rng[0].isoformat() if rng else "", "week_end": rng[1].isoformat() if rng else ""}
        upcoming = [(s, i) for i, s, e in tris if s > today]
        if upcoming:
            s, i = min(upcoming)
            return {"state": "before_term" if s == min(x[1] for x in tris) else "between_terms",
                    "next_trimester": i, "next_name": self.cal.trimesters[i].name, "next_start": s.isoformat()}
        return {"state": "after_year"}

    def next_school_day(self, d: date, limit: int = 400) -> Optional[date]:
        for _ in range(limit):
            d += timedelta(days=1)
            if self.is_school_day(d):
                return d
        return None
