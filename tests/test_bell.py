import unittest

from helpers import tmp   # sets the import path and blocks the real internet
from app.core import paths
from app.core.errors import AppError
from app.core.store import DataStore
from app.server.bell_service import clean_bell
from app.server.service import Service


def _svc():
    svc = Service(); svc.store = DataStore(tmp())
    svc.build_structure({"g4": ["A"]})
    return svc


def _six():
    """Six lessons of 45 minutes from 8:00, a break after the 3rd, prayer after the 5th, 20 minutes of late duty."""
    return {"periods": [{"start": "08:00", "end": "08:45"}, {"start": "08:45", "end": "09:30"}, {"start": "09:30", "end": "10:15"},
                        {"start": "10:45", "end": "11:30"}, {"start": "11:30", "end": "12:15"}, {"start": "12:25", "end": "13:10"}],
            "break": {"after": "3", "start": "10:15", "end": "10:45"}, "prayer": {"after": "5", "start": "12:15", "end": "12:25"},
            "late": {"start": "13:10", "end": "13:30"}}


class TestBell(unittest.TestCase):
    def test_the_school_times_are_used_until_changed_and_can_be_brought_back(self):
        svc = _svc()
        self.assertEqual(len(svc.get_timetable()["periods"]), 8)
        self.assertFalse(svc.get_bell()["custom"])
        svc.put_bell({"bell": _six()})
        b = svc.get_bell()
        self.assertTrue(b["custom"])
        tt = svc.get_timetable()
        self.assertEqual([p["name"] for p in tt["periods"]], ["1", "2", "3", "4", "5", "6"])
        self.assertEqual((tt["bell"]["break"]["after"], tt["bell"]["late"]["end"]), ("3", "13:30"))
        self.assertEqual(svc.today()["periods"][5]["end"], "13:10")
        svc.reset_bell()
        self.assertEqual(len(svc.get_timetable()["periods"]), 8)
        # putting back exactly the school's times keeps nothing on disk
        d = paths.bell_schedule()
        svc.put_bell({"bell": {k: v for k, v in d.items() if k != "_note"}})
        self.assertFalse(svc.get_bell()["custom"])

    def test_wrong_times_are_refused_and_a_damaged_file_never_stops_the_program(self):
        svc = _svc()
        bad = _six(); bad["periods"][1]["end"] = "08:30"
        with self.assertRaises(AppError) as e:
            svc.put_bell({"bell": bad})
        self.assertEqual(e.exception.code, "bell_bad_time")
        over = _six(); over["break"] = {"after": "3", "start": "10:00", "end": "10:45"}
        with self.assertRaises(AppError) as e:
            clean_bell(over)
        self.assertEqual(e.exception.code, "bell_overlap")
        for periods in ([], [{"start": "08:00", "end": "08:40"}] * 13):
            with self.assertRaises(AppError) as e:
                clean_bell({"periods": periods})
            self.assertEqual(e.exception.code, "bell_count")
        far = _six(); far["prayer"]["after"] = "9"
        with self.assertRaises(AppError):
            clean_bell(far)
        svc._bell_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(len(svc.get_timetable()["periods"]), 8)

    def test_no_break_means_no_break_duty_and_lessons_that_went_away_are_hidden_not_lost(self):
        svc = _svc()
        room = svc.get_structure()["rooms"][0]["id"] if hasattr(svc, "get_structure") else "g4-a"
        tt = svc.get_timetable()
        grid = {"Sunday": {"7": room, "2": room}}
        svc.put_timetable({"grid": grid, "duties": {"Sunday": ["break", "late"]}})
        six = _six(); del six["break"]
        svc.put_bell({"bell": six})
        out = svc.get_timetable()
        self.assertEqual(out["duties"]["Sunday"], ["late"])
        self.assertNotIn("7", out["grid"]["Sunday"])
        self.assertIn("2", out["grid"]["Sunday"])
        self.assertNotIn("break", [d["kind"] for d in svc.today("2026-10-25")["duties"]])
        self.assertTrue(tt["periods"])


if __name__ == "__main__":
    unittest.main()
