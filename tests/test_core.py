import json
import tempfile
import unittest
from datetime import date

from helpers import tmp, ZIP_DATA   # sets the import path and blocks the real internet
from app.core.academic import AcademicCalendar
from app.core.errors import AppError
from app.core.legacy import import_legacy
from app.core.models import Calendar, Holiday, Settings, Structure, Timetable, Trimester, Period
from app.core.store import DataStore
from app.core.structure_service import build_from_selection, normalize
from app.core.students import parse_file, parse_text
from app.core.timetable import room_session_days, scrub_timetable, sessions_on


class TestWeekOrder(unittest.TestCase):
    def test_working_days_are_sunday_first(self):
        from app.core.models import Settings
        s = Settings(working_days=["Thursday", "Monday", "Sunday", "Tuesday", "Wednesday"])
        self.assertEqual(s.working_days, ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"])


class StoreTests(unittest.TestCase):
    def test_roundtrip_and_backup_prune(self):
        s = DataStore(tmp())
        for i in range(9):
            s.save_settings(Settings(teacher_name=f"T{i}"))
        self.assertEqual(s.load_settings().teacher_name, "T8")
        backups = list((s.backup_root()).glob("config.json.*.bak"))
        self.assertEqual(len(backups), 5)

    def test_backups_of_similar_names_do_not_prune_each_other(self):
        s = DataStore(tmp())
        for i in range(8):
            s.write_json(s.root / "quiz.json", {"i": i})
            s.write_json(s.root / "quiz_answer_key.json", {"i": i})
        self.assertEqual(len(list(s.backup_root().glob("quiz.json.*.bak"))), 5)
        self.assertEqual(len(list(s.backup_root().glob("quiz_answer_key.json.*.bak"))), 5)

    def test_corrupt_file_recovers_from_backup(self):
        s = DataStore(tmp())
        s.save_settings(Settings(teacher_name="Good"))
        s.save_settings(Settings(teacher_name="Newer"))
        s.config_path().write_text("{ broken", encoding="utf-8")
        self.assertIn(s.load_settings().teacher_name, ("Good", "Newer"))

    def test_invalid_json_never_replaces_file(self):
        s = DataStore(tmp())
        s.write_json(s.config_path(), {"a": 1})
        with self.assertRaises(TypeError):
            s.write_json(s.config_path(), {"a": object()})
        self.assertEqual(s.read_json(s.config_path()), {"a": 1})

    def test_students_csv_arabic_roundtrip(self):
        s = DataStore(tmp())
        s.save_students("g4-a", ["أحمد علي", "Sara  ", ""])
        self.assertEqual(s.load_students("g4-a"), ["أحمد علي", "Sara"])

    def test_unsafe_room_id_rejected(self):
        s = DataStore(tmp())
        with self.assertRaises(AppError):
            s.students_path("../../etc")

    def test_conflict_detection_ignores_backups(self):
        s = DataStore(tmp())
        (s.root / "calendar (conflict).json").write_text("{}")
        (s.root / "_backup").mkdir()
        (s.root / "_backup" / "copy of x.json").write_text("{}")
        self.assertEqual(s.detect_conflicts(), ["calendar (conflict).json"])


class StructureTests(unittest.TestCase):
    def test_build_and_keep_existing(self):
        s = build_from_selection({"g4": ["A", "B"], "kg1": ["A"]})
        self.assertEqual({r.id for r in s.rooms}, {"g4-a", "g4-b", "kg1-a"})
        self.assertEqual({st.id for st in s.stages}, {"primary", "kg"})
        next(g for g in s.grades if g.id == "g4").settings.textbook = "Book"
        again = build_from_selection({"g4": ["A", "B", "C"]}, s)
        self.assertEqual(len(again.rooms), 4)
        self.assertEqual(next(g for g in again.grades if g.id == "g4").settings.textbook, "Book")

    def test_orphan_room_is_rejected(self):
        s = build_from_selection({"g1": ["A"]})
        s.rooms[0].grade_id = "nope"
        with self.assertRaises(AppError):
            normalize(s)

    def test_scrub_timetable(self):
        s = build_from_selection({"g1": ["A"]})
        tt = Timetable(periods=[Period(name="1")], grid={"Sunday": {"1": "g9-z", "2": "g1-a"}})
        scrub_timetable(tt, s)
        self.assertEqual(tt.grid["Sunday"], {"1": ""})


class AcademicTests(unittest.TestCase):
    def cal(self, **kw):
        c = Calendar(trimesters=[Trimester(name="T1", start="2026-09-01", end="2026-11-30"),
                                 Trimester(name="T2", start="2026-12-01", end="2027-02-28")],
                     holidays=[Holiday(start="2026-10-06", name="Armed Forces Day"),
                               Holiday(start="2026-12-24", end="2026-12-26", name="Break")], **kw)
        return AcademicCalendar(c, ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"])

    def test_week_starts_on_sunday(self):
        a = self.cal()
        self.assertEqual(a.week_start_wd, 6)
        w = a.trimester_weeks(0)
        # 1 Sep 2026 is a Tuesday -> week 1 starts Sunday 30 Aug (shows school days only from Tue)
        self.assertEqual(w[0]["start"], "2026-08-30")
        self.assertEqual(w[0]["school_days"], 3)
        self.assertEqual(w[1]["start"], "2026-09-06")

    def test_position_in_term_and_gaps(self):
        a = self.cal()
        p = a.position(date(2026, 10, 24))  # Saturday of week 8
        self.assertEqual((p["state"], p["trimester"], p["week"]), ("in_term", 0, 8))
        self.assertEqual(a.position(date(2026, 8, 1))["state"], "before_term")
        self.assertEqual(a.position(date(2027, 6, 1))["state"], "after_year")
        self.assertEqual(AcademicCalendar(Calendar(), ["Sunday"]).position(date.today())["state"], "no_calendar")

    def test_holiday_range_and_school_day(self):
        a = self.cal()
        self.assertFalse(a.is_school_day(date(2026, 10, 6)))
        self.assertFalse(a.is_school_day(date(2026, 12, 25)))
        self.assertTrue(a.is_school_day(date(2026, 10, 7)))
        self.assertFalse(a.is_school_day(date(2026, 10, 9)))  # Friday
        self.assertEqual(a.next_school_day(date(2026, 10, 5)), date(2026, 10, 7))

    def test_week1_override_from_legacy_value(self):
        a = self.cal()
        a.cal.trimesters[0].week1_start = "2026-09-06"
        self.assertEqual(a.trimester_weeks(0)[0]["start"], "2026-09-06")
        p = a.position(date(2026, 9, 3))  # before the overridden week 1 -> clamped to week 1
        self.assertEqual(p["week"], 1)

    def test_other_weekends(self):
        a = AcademicCalendar(Calendar(), ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        self.assertEqual(a.week_start_wd, 0)
        a = AcademicCalendar(Calendar(), ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday"])
        self.assertEqual(a.week_start_wd, 5)


class TimetableTests(unittest.TestCase):
    def setUp(self):
        self.struct = build_from_selection({"g4": ["A"], "g5": ["A"]})
        self.tt = Timetable(periods=[Period(name="1", start="08:00", end="08:40"), Period(name="2")],
                            grid={"Sunday": {"1": "g4-a", "2": ""}, "Monday": {"1": "", "2": "g5-a"}})
        self.cal = AcademicCalendar(Calendar(trimesters=[Trimester(name="T1", start="2026-09-01", end="2026-11-30")],
                                             holidays=[Holiday(start="2026-10-12", name="x")]),
                                    ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"])

    def test_sessions(self):
        got = sessions_on(date(2026, 10, 11), self.tt, self.cal, self.struct)  # Sunday
        self.assertEqual([(s["period"], s["room_id"]) for s in got], [("1", "g4-a")])
        self.assertEqual(got[0]["start"], "08:00")

    def test_holiday_and_cancel_and_extra(self):
        self.assertEqual(sessions_on(date(2026, 10, 12), self.tt, self.cal, self.struct), [])
        self.tt.overrides["2026-10-11"] = {"cancel": ["1"], "extra": [{"period": "2", "room_id": "g5-a"}]}
        got = sessions_on(date(2026, 10, 11), self.tt, self.cal, self.struct)
        self.assertEqual([(s["period"], s["extra"]) for s in got], [("2", True)])

    def test_session_days(self):
        self.assertEqual(room_session_days("g5-a", self.tt, ["Sunday", "Monday"]), ["Monday"])


class StudentParsingTests(unittest.TestCase):
    def test_paste_with_numbers_header_duplicates(self):
        r = parse_text("الاسم\n1. أحمد محمد\n2) سارة علي\n\n3 - أحمد محمد\n  Omar   Ali ")
        self.assertEqual(r["names"], ["أحمد محمد", "سارة علي", "Omar Ali"])
        self.assertEqual(r["duplicates"], ["أحمد محمد"])

    def test_excel_style_columns(self):
        r = parse_text("1\tSara Ali\t2020\n2\tOmar Hany\t2021")
        self.assertEqual(r["names"], ["Sara Ali", "Omar Hany"])

    def test_csv_and_xlsx(self):
        r = parse_file("a.csv", "Name,Class\nSara,4A\nOmar,4A\n".encode("utf-8"))
        self.assertEqual(r["names"], ["Sara", "Omar"])
        import io
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(["#", "Student Name"]); ws.append([1, "Laila"]); ws.append([2, "Karim"])
        buf = io.BytesIO(); wb.save(buf)
        r = parse_file("x.xlsx", buf.getvalue())
        self.assertEqual(r["names"], ["Laila", "Karim"])


@unittest.skipUnless(ZIP_DATA.exists(), "legacy sample not available")
class LegacyImportTests(unittest.TestCase):
    def test_import_real_old_folder(self):
        s = DataStore(tmp())
        report = import_legacy(ZIP_DATA, s)
        st = s.load_structure()
        self.assertEqual(len(st.stages), 4)  # kg gets created from the timetable
        self.assertEqual(len(st.grades), 13)
        self.assertEqual(len(st.rooms), 13)
        self.assertGreater(report["duplicates_removed"], 100)
        self.assertEqual(len(s.load_students("g9-a")), 30)
        self.assertEqual(report["timetable"], "imported")
        tt = s.load_timetable()
        self.assertEqual(tt.grid["Sunday"]["6"], "g5-a")
        self.assertEqual(len(tt.periods), 8)
        cal = s.load_calendar()
        self.assertEqual(cal.holidays[0].start, "2026-10-06")
        self.assertEqual(cal.trimesters[0].week1_start, "2026-09-06")
        # importing twice changes nothing
        again = import_legacy(ZIP_DATA, s)
        self.assertEqual((again["rooms"], again["students"]), (0, 0))
        self.assertEqual(len(s.load_structure().rooms), 13)

    def test_refuses_random_folder(self):
        with self.assertRaises(AppError):
            import_legacy(tmp(), DataStore(tmp()))



class TestSortAndPaste(unittest.TestCase):
    def test_grades_sorted_youngest_first_numerically(self):
        from app.core.models import Grade, Room, Stage
        from app.core.structure_service import sort_structure
        s = Structure(stages=[Stage(id="high_school", name="High", order=3), Stage(id="kg", name="KG", order=0), Stage(id="preparatory", name="Prep", order=2)],
                      grades=[Grade(id=f"g{n}", name=f"Grade {n}", stage_id="high_school" if n > 8 else "preparatory", order=0) for n in (11, 9, 10, 8)] + [Grade(id="kg2", name="KG2", stage_id="kg", order=1)],
                      rooms=[Room(id="g10-a", grade_id="g10", name="Grade 10 A"), Room(id="g9-b", grade_id="g9", name="Grade 9 B"), Room(id="g9-a", grade_id="g9", name="Grade 9 A")])
        sort_structure(s)
        self.assertEqual([g.id for g in s.grades], ["kg2", "g8", "g9", "g10", "g11"])
        self.assertEqual([x.id for x in s.stages], ["kg", "preparatory", "high_school"])
        self.assertEqual([r.id for r in s.rooms], ["g9-a", "g9-b", "g10-a"])

    def test_school_system_export_paste(self):
        from app.core.students import parse_text
        txt = "1214\nيامن عادل\nذكر\n********\nرياض اطفال\nKG1\nKG1 A\n3 ش فهمي\n01224006224\n\n1322\nمبارك بن مبارك\nذكر\n********\nرياض اطفال\nKG1\nKG1 A\n"
        self.assertEqual(parse_text(txt)["names"], ["يامن عادل", "مبارك بن مبارك"])

    def test_school_calendar_file_is_valid(self):
        from app.core import paths
        from app.core.models import Calendar
        from app.core.academic import AcademicCalendar
        from datetime import date
        cal = Calendar.model_validate(json.loads((paths.resources_dir() / "school_calendar.json").read_text(encoding="utf-8")))
        a = AcademicCalendar(cal, ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"])
        self.assertEqual(a.position(date(2026, 10, 25))["week"], 8)
        self.assertFalse(a.is_school_day(date(2026, 10, 6)))
        self.assertTrue(a.is_school_day(date(2026, 10, 25)))
        self.assertEqual(a.position(date(2026, 12, 1))["trimester"], 1)


class TestRoster(unittest.TestCase):
    def test_known_class_gets_its_students_once(self):
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.build_structure({"kg1": ["A"], "g4": ["A"]})
            self.assertEqual(len(svc.get_students("kg1-a")["names"]), 14)
            self.assertEqual(svc.get_students("g4-a")["names"], [])
            svc.put_students("kg1-a", ["Only one"])
            svc.get_structure()
            self.assertEqual(svc.get_students("kg1-a")["names"], ["ونلي ون"])


class TestWeekendHolidays(unittest.TestCase):
    def test_friday_saturday_holidays_are_dropped(self):
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            out = svc.put_calendar({"holidays": [{"start": "2026-10-09", "end": "", "name": "Friday"}, {"start": "2026-10-10", "end": "2026-10-10", "name": "Sat"},
                                                 {"start": "2026-10-06", "end": "", "name": "Oct 6"}, {"start": "2026-12-27", "end": "2026-12-31", "name": "Winter"}]})
            self.assertEqual([h["name"] for h in out["holidays"]], ["Oct 6", "Winter"])

    def test_official_year_gets_all_holidays_and_loses_event_rows(self):
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            off = svc.school_calendar()
            ev = off["events"][0]
            out = svc.put_calendar({"academic_year": off["academic_year"], "holidays": [{"start": ev["date"], "end": "", "name": ev["name"]},
                                                                                       {"start": "2026-11-25", "end": "", "name": "My own day"}]})
            names = [h["name"] for h in out["holidays"]]
            self.assertNotIn(ev["name"], names)           # an event is not a holiday
            self.assertIn("My own day", names)            # what the teacher added stays
            for h in off["holidays"]:                      # every orange cell of the school calendar is there
                self.assertTrue(any(x["start"] <= h["start"] and (x["end"] or x["start"]) >= (h["end"] or h["start"]) for x in out["holidays"]), h)


class TestCoverage(unittest.TestCase):
    def test_progress_pack_and_status(self):
        import zipfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.put_settings({"teacher_name": "بلال عبدالناصر عبدالفتاح", "subject": "ICT"})
            svc.build_structure({"kg1": ["A"]})
            off = svc.school_calendar(); svc.put_calendar({"academic_year": off["academic_year"], "trimesters": off["trimesters"], "holidays": off["holidays"]})
            svc.get_timetable()
            cov = svc.coverage("2026-10-28")
            self.assertEqual(cov["state"], "in_term")
            row = next(r for r in cov["rows"] if r["room_id"] == "kg1-a")
            self.assertGreater(row["held"], 3); self.assertEqual((row["logged"], row["status"]), (0, "bad"))
            svc.log_save({"room_id": "kg1-a", "date": "2026-10-27", "period": "4", "topic": "Mouse"})
            row = next(r for r in svc.coverage("2026-10-28")["rows"] if r["room_id"] == "kg1-a")
            self.assertEqual((row["logged"], row["last_topic"]), (1, "Mouse"))
            out = svc.inspection_pack()
            with zipfile.ZipFile(out["path"]) as z:
                names = z.namelist()
            self.assertIn("Lesson_Log.csv", names); self.assertIn("Curriculum_Progress.csv", names); self.assertIn("README.txt", names)
            with self.assertRaises(AppError):
                svc.push_status()                                      # not signed in to the school server
            with self.assertRaises(AppError):
                svc.staff_status()


class TestReadyTimetable(unittest.TestCase):
    def test_known_teacher_gets_timetable_once(self):
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.put_settings({"teacher_name": "بلال عبدالناصر عبدالفتاح"})
            tt = svc.get_timetable()
            self.assertEqual(tt["grid"]["Sunday"]["6"], "g5-a")
            self.assertEqual(tt["grid"]["Tuesday"]["4"], "kg1-a")
            self.assertEqual(tt["duties"]["Wednesday"], ["break", "late"])
            self.assertEqual(tt["periods"][0]["start"], "08:15")
            tt["grid"]["Sunday"]["6"] = ""
            svc.put_timetable(tt)
            self.assertEqual(svc.get_timetable()["grid"]["Sunday"]["6"], "")  # his edit is kept
            other = Service(); other.store = DataStore(tempfile.mkdtemp())
            other.put_settings({"teacher_name": "Someone Else"})
            self.assertEqual(other.get_timetable()["grid"], {})


class TestUnnamedHolidays(unittest.TestCase):
    def test_unnamed_days_get_names_and_merge(self):
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            days = [{"start": f"2026-12-{x}", "end": "", "name": ""} for x in (27, 28, 29, 30, 31)] + [{"start": "2026-10-09", "end": "", "name": ""}]
            out = svc.put_calendar({"holidays": days})["holidays"]
            self.assertEqual(len(out), 1)
            self.assertEqual((out[0]["start"], out[0]["end"]), ("2026-12-27", "2026-12-31"))
            self.assertIn("Winter Break", out[0]["name"])
            rows = svc.put_calendar({"holidays": [{"start": "2026-11-15", "end": "2026-11-18", "name": ""}, {"start": "2026-12-03", "end": "", "name": ""}]})["holidays"]
            self.assertEqual(rows, [])  # school events are not holidays: those days stay normal school days


if __name__ == "__main__":
    unittest.main()
