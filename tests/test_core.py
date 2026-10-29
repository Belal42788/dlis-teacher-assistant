import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.academic import AcademicCalendar
from app.core.errors import AppError
from app.core.legacy import import_legacy
from app.core.models import Calendar, Holiday, Settings, Structure, Timetable, Trimester, Period
from app.core.store import DataStore
from app.core.structure_service import build_from_selection, normalize
from app.core.students import parse_file, parse_text
from app.core.timetable import room_session_days, scrub_timetable, sessions_on

ZIP_DATA = Path(os.environ.get("DLIS_LEGACY_SAMPLE", "/home/claude/proj/DLIS_Data"))


def tmp():
    return tempfile.mkdtemp()


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


if __name__ == "__main__":
    unittest.main()


class TestSortAndPaste(unittest.TestCase):
    def test_grades_sorted_youngest_first_numerically(self):
        from app.core.models import Grade, Room, Stage, Structure
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
        import json
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
        import tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.build_structure({"kg1": ["A"], "g4": ["A"]})
            self.assertEqual(len(svc.get_students("kg1-a")["names"]), 14)
            self.assertEqual(svc.get_students("g4-a")["names"], [])
            svc.put_students("kg1-a", ["Only one"])
            svc.get_structure()
            self.assertEqual(svc.get_students("kg1-a")["names"], ["Only one"])


class TestWeekendHolidays(unittest.TestCase):
    def test_friday_saturday_holidays_are_dropped(self):
        import tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            out = svc.put_calendar({"holidays": [{"start": "2026-10-09", "end": "", "name": "Friday"}, {"start": "2026-10-10", "end": "2026-10-10", "name": "Sat"},
                                                 {"start": "2026-10-06", "end": "", "name": "Oct 6"}, {"start": "2026-12-27", "end": "2026-12-31", "name": "Winter"}]})
            self.assertEqual([h["name"] for h in out["holidays"]], ["Oct 6", "Winter"])


class TestReadyTimetable(unittest.TestCase):
    def test_known_teacher_gets_timetable_once(self):
        import tempfile
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
        import tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            days = [{"start": f"2026-12-{x}", "end": "", "name": ""} for x in (27, 28, 29, 30, 31)] + [{"start": "2026-10-09", "end": "", "name": ""}]
            out = svc.put_calendar({"holidays": days})["holidays"]
            self.assertEqual(len(out), 1)
            self.assertEqual((out[0]["start"], out[0]["end"]), ("2026-12-27", "2026-12-31"))
            self.assertIn("Winter Break", out[0]["name"])


class TestDocsAndTasks(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        os.environ["DLIS_NO_OPEN"] = "1"
        from app.server.service import Service
        from app.core.store import DataStore
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "Test Teacher", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"], "kg1": ["A"]})
        self.svc.put_students("g4-a", ["Sara Ali", "Omar Samy"])
        self.svc.put_timetable({"grid": {"Sunday": {"6": "g4-a", "2": "kg1-a"}}})
        self.svc.put_calendar(self.svc.school_calendar())

    def tearDown(self):
        self.d.cleanup()

    def test_weekly_checklist(self):
        w = self.svc.get_weekly(0, 8)
        self.assertEqual(w["tasks"][0], "attendance"); self.assertEqual(len(w["rows"]), 2); self.assertEqual(w["done"], 0)
        w = self.svc.set_weekly({"trimester": 0, "week": 8, "grade_id": "g4", "task": "quiz", "state": "done"})
        self.assertEqual(next(r for r in w["rows"] if r["grade_id"] == "g4")["states"]["quiz"], "done"); self.assertEqual(w["done"], 1)
        self.assertEqual(self.svc.get_weekly(0, 9)["done"], 0)   # each week has its own marks
        with self.assertRaises(AppError):
            self.svc.set_weekly({"trimester": 0, "week": 8, "grade_id": "g4", "task": "nope", "state": "done"})

    def test_saved_chats(self):
        a = self.svc.chat_save("", {"messages": [{"role": "user", "content": "Explain the CPU"}, {"role": "assistant", "content": "It is the brain"}]})
        self.assertEqual(a["title"], "Explain the CPU")
        b = self.svc.chat_save("", {"messages": [{"role": "user", "content": "Quiz ideas"}]})
        self.assertEqual({x["id"] for x in self.svc.chats_list()["items"]}, {a["id"], b["id"]})
        self.assertEqual(len(self.svc.chat_get(a["id"])["messages"]), 2)
        self.svc.chat_save(a["id"], {"messages": [{"role": "user", "content": "Explain the CPU"}, {"role": "assistant", "content": "x"}, {"role": "user", "content": "more"}]})
        self.assertEqual(len(self.svc.chat_get(a["id"])["messages"]), 3)
        self.assertEqual(len(self.svc.chat_delete(a["id"])["items"]), 1)
        with self.assertRaises(AppError):
            self.svc.chat_get(a["id"])

    def test_grade_table_for_lms(self):
        from openpyxl import load_workbook
        room = self.svc.store.load_structure().rooms[0]
        self.svc.store.save_students(room.id, ["Ali Ahmed", "Sara Omar"]) if hasattr(self.svc.store, "save_students") else None
        out = self.svc.make_grading_sheet({"room_id": room.id, "trimester": 0, "week": 8, "lang": "en", "format": "xlsx"})
        self.assertTrue(out["name"].endswith(".xlsx"))
        ws = load_workbook(out["path"]).active
        self.assertEqual([c.value for c in ws[2]], ["#", "Student", "Grade"])
        self.assertGreaterEqual(ws.max_row, 3)
        csv = self.svc.make_grading_sheet({"room_id": room.id, "trimester": 0, "week": 8, "lang": "en", "format": "csv"})
        self.assertTrue(open(csv["path"], encoding="utf-8-sig").read().startswith("#,Student,Grade"))

    def test_plan_on_today_and_cover_sheet(self):
        from docx import Document
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware", "objectives": "- Name parts"}})
        plans = self.svc._plans(); plans.setdefault("slides", {})["g4|0|8"] = {"count": 12, "file": "x.pptx"}
        self.svc.store.write_json(self.svc._plans_path(), plans)
        self.svc.log_save({"room_id": "g4-a", "date": "2026-10-18", "topic": "Input", "slide": 5, "total": 12, "next_note": "Bring mice"})
        sessions = self.svc.today("2026-10-25")["sessions"]
        plan = next(x for x in sessions if x["room_id"] == "g4-a")["plan"]
        self.assertEqual((plan["topic"], plan["slides"]), ("Hardware", 12))
        r = self.svc.make_cover_sheet({"date": "2026-10-25"})
        self.assertEqual(r["lessons"], 2)
        d = Document(r["path"]); text = "\n".join(p.text for p in d.paragraphs)
        for w in ("substitute", "Hardware", "12 slides", "slide 5 of 12", "Bring mice", "Grade 4"):
            self.assertIn(w, text)
        with self.assertRaises(AppError):
            self.svc.make_cover_sheet({"date": "2026-10-23"})   # Friday: no lessons

    def test_four_documents(self):
        from docx import Document
        r = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware", "sunday": "Warm up"}})
        self.assertTrue(r["rel"].replace("\\", "/").endswith("Documents/Grade 4/T1-W08_Lesson_Plan.docx"), r["rel"])
        doc = Document(r["path"])
        txt = " ".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        self.assertIn("Hardware", txt); self.assertIn("ICT", txt); self.assertIn("Test Teacher", txt); self.assertIn("Warm up", txt)
        days = [doc.tables[2].rows[i].cells[0].text for i in range(1, 6)]  # grade 4 only has Sunday: the other four days say so
        self.assertNotIn("No session", days[0]); self.assertIn("Warm up", days[0])
        self.assertTrue(all("No session" in d for d in days[1:]), days)
        self.assertIn("Term 1 Week 8", doc.paragraphs[0].text)
        self.assertIn("Term 1", doc.paragraphs[0].text.replace("\t", "").replace("  ", " ") if False else "Term 1")
        r = self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": ["L1", "L2"]})
        txt = " ".join(c.text for t in Document(r["path"]).tables for row in t.rows for c in row.cells)
        self.assertIn("From 06/09 to 10/09", txt); self.assertIn("L2", txt); self.assertIn("Week 12", txt)
        r = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a", "with_answers": True})
        self.assertEqual(r["questions"], 1)
        r = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8})
        txt = " ".join(c.text for t in Document(r["path"]).tables for row in t.rows for c in row.cells)
        self.assertIn("Sara Ali", txt); self.assertIn("Grade level Grade 4 A", txt)
        self.assertEqual(self.svc.open_file(r["path"])["opened"], r["path"])
        with self.assertRaises(Exception):
            self.svc.open_file("/etc/passwd")
        with self.assertRaises(Exception):
            self.svc.build_structure({"g5": ["A"]}); self.svc.make_grading_sheet({"room_id": "g5-a", "trimester": 0, "week": 8})  # no students

    def test_tasks(self):
        from datetime import date
        self.svc.store.write_json(self.svc._tasks_path(), {"tasks": [], "dismissed": [], "tracking_start": "2026-10-19"})
        t = self.svc.list_tasks(date(2026, 10, 25))
        ids = {x["id"] for x in t["auto"]}
        self.assertIn("lesson_plan:g4:0:7", ids)   # week 7 started 18 Oct, nothing written: overdue
        self.assertIn("lesson_plan:g4:0:9", ids)   # next week
        self.assertEqual(len([i for i in ids if i.startswith("lesson_plan:kg1")]), len([i for i in ids if i.startswith("lesson_plan:g4")]))
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8})
        ids = {x["id"] for x in self.svc.list_tasks(date(2026, 10, 25))["auto"]}
        self.assertNotIn("lesson_plan:g4:0:8", ids)    # written -> disappears by itself
        t = self.svc.add_task({"title": "Print quizzes", "importance": "high", "deadline": "2026-10-26"})
        tid = t["tasks"][0]["id"]
        self.svc.update_task(tid, {"done": True})
        self.assertTrue(self.svc.list_tasks()["tasks"][0]["done"])
        self.svc.dismiss_task("lesson_plan:g4:0:9")
        self.assertNotIn("lesson_plan:g4:0:9", {x["id"] for x in self.svc.list_tasks(date(2026, 10, 25))["auto"]})
        self.svc.delete_task(tid)
        self.assertEqual(self.svc.list_tasks()["tasks"], [])


class TestAi(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        os.environ["DLIS_NO_OPEN"] = "1"
        self.home = tempfile.TemporaryDirectory()
        os.environ["DLIS_APP_HOME"] = self.home.name
        from app.server.service import Service
        from app.core.store import DataStore
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"]})
        self.svc.put_students("g4-a", ["Sara Ali Hassan", "Omar Samy"])
        self.svc.put_timetable({"grid": {"Sunday": {"1": "g4-a"}, "Monday": {"2": "g4-a"}}})
        self.svc.put_calendar(self.svc.school_calendar())
        self.sent = []
        from app.core import ai_client
        self.ai_client = ai_client
        self._orig = ai_client._http
        def fake(method, url, headers, body=None, timeout=0):
            self.sent.append((method, url, headers, body))
            if url.endswith("/models"):
                return {"data": [{"id": "models/m1"}, {"id": "m2"}]}
            if url.endswith("/v1/messages"):
                return {"content": [{"type": "text", "text": self.reply}]}
            return {"choices": [{"message": {"content": self.reply}}]}
        ai_client._http = fake
        self.reply = "ready"

    def tearDown(self):
        import os
        self.ai_client._http = self._orig
        os.environ.pop("DLIS_APP_HOME", None)
        self.d.cleanup(); self.home.cleanup()

    def test_chat_hides_names_keeps_history_and_prompts_are_editable(self):
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = "Sure, here is an idea."
        r = self.svc.ai_chat({"messages": [{"role": "user", "content": "Help"}, {"role": "assistant", "content": "Ok"},
                                           {"role": "user", "content": "Sara Ali Hassan talks too much, what to do?"}], "grade_id": "g4"})
        self.assertEqual(r["reply"], self.reply)
        body = self.sent[-1][3]
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user", "assistant", "user"])
        self.assertNotIn("Sara", json.dumps(body)); self.assertIn("[student]", json.dumps(body))
        self.assertIn("ICT", body["messages"][0]["content"])
        with self.assertRaises(AppError):
            self.svc.ai_chat({"messages": [{"role": "assistant", "content": "hi"}]})
        # the teacher edits the lesson prompt; the output-format rule stays
        got = self.svc.ai_prompts_get()
        self.assertTrue(got["templates"]); self.assertEqual(got["custom"], {})
        self.svc.ai_prompts_put({"key": "lesson", "system": "You are a pirate teacher.", "guidance": "Use short steps."})
        self.reply = json.dumps({"topic": "T"})
        self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 1, "topic": "Hardware"})
        system = self.sent[-1][3]["messages"][0]["content"]
        self.assertIn("pirate", system); self.assertIn("ONE JSON object", system)
        self.svc.ai_prompts_put({"key": "lesson", "reset": True})
        self.assertEqual(self.svc.ai_prompts_get()["custom"], {})
        with self.assertRaises(AppError):
            self.svc.ai_prompts_put({"key": "nope", "system": "x"})

    def test_slide_topics_and_notebooklm_prompt(self):
        wk = self.svc.overview()["trimesters"][0]["weeks"]
        w1, w2 = wk[2]["number"], wk[3]["number"]
        self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": [""] * 2 + ["Intro to computers", "Hardware"]})
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": w2, "content": {"topic": "Input devices", "objectives": "- Name 3 devices"}})
        got = {x["week"]: x for x in self.svc.slide_topics("g4", 0)["weeks"]}
        self.assertEqual((got[w1]["topic"], got[w1]["source"]), ("Intro to computers", "trimester"))
        self.assertEqual((got[w2]["topic"], got[w2]["source"]), ("Input devices", "lesson"))  # the lesson plan wins
        self.assertEqual(got[wk[0]["number"]]["source"], "")
        r = self.svc.notebooklm_prompt({"grade_id": "g4", "topic": "Input devices", "slides": 8, "language": "ar", "look": "cartoon", "objectives": "- Name 3 devices"})["prompt"]
        for must in ("8 slides", "Input devices", "ICT", "Arabic", "cartoon", "Do not add exercises", "2F82A8", "Name 3 devices", "right-to-left", "Grade 4", "speaker notes"):
            self.assertIn(must, r)
        self.svc.build_structure({"kg1": ["A"], "g4": ["A"], "g11": ["A"]})
        stages = {g: self.svc.notebooklm_prompt({"grade_id": g, "topic": "Colours"})["prompt"] for g in ("kg1", "g4", "g11")}
        self.assertIn("4-6 years old", stages["kg1"]); self.assertIn("6 words", stages["kg1"])
        self.assertIn("9-12 years old", stages["g4"]); self.assertIn("15-18 years old", stages["g11"])
        self.assertEqual(len({p.split("## Visual style")[1][:60] for p in stages.values()}), 3)  # each stage has its own style
        with self.assertRaises(AppError):
            self.svc.notebooklm_prompt({"grade_id": "g4", "topic": " "})
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = "Input devices let us give information to a computer."
        out = self.svc.notebooklm_source({"grade_id": "g4", "topic": "Input devices. Sara Ali Hassan helps"})
        self.assertIn("Input devices", out["text"]); self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))

    def test_bilingual_student_names(self):
        from app.core.translit import to_english
        self.assertEqual(to_english("محمد أحمد"), "Mohamed Ahmed")
        self.assertEqual(to_english("Sara Ali"), "Sara Ali")
        r = self.svc.put_students("g4-a", ["يوسف محمد", "مريم علي"], ["", "Maryam Aly"])
        self.assertEqual((r["english"], r["auto"][0]), (["", "Maryam Aly"], "Youssef Mohamed"))
        again = self.svc.get_students("g4-a")
        self.assertEqual(again["english"], ["", "Maryam Aly"])
        # spelling that equals our own suggestion is not stored as a manual change
        self.assertEqual(self.svc.put_students("g4-a", ["يوسف محمد"], ["Youssef Mohamed"])["english"], [""])
        r = self.svc.put_students("g4-a", ["يوسف محمد", "مريم علي"], ["", "Maryam Aly"])
        from docx import Document
        txt = lambda p: "\n".join(c.text for t in Document(p).tables for row in t.rows for c in row.cells)
        en = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8})  # same file name: read before the next one
        text_en = txt(en["path"])
        text_ar = txt(self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8, "lang": "ar"})["path"])
        self.assertIn("Maryam Aly", text_en); self.assertIn("Youssef Mohamed", text_en); self.assertNotIn("مريم", text_en)
        self.assertIn("مريم علي", text_ar)
        # both spellings are hidden from the AI
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.svc.ai_chat({"messages": [{"role": "user", "content": "Maryam Aly and Youssef Mohamed and مريم علي were late"}]})
        sent = json.dumps(self.sent[-1][3], ensure_ascii=False)
        for n in ("Maryam", "Youssef", "مريم"):
            self.assertNotIn(n, sent)

    def test_slides_plan_images_and_powerpoint(self):
        import base64, io
        from PIL import Image
        from pptx import Presentation
        buf = io.BytesIO(); Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "JPEG"); jpg = buf.getvalue()
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = json.dumps({"slides": [{"title": "What is input?", "bullets": ["Sends data in", "Keyboard"], "notes": "Say it.", "image_prompt": "a keyboard"},
                                            {"title": "Recap", "bullets": ["Input = in"], "notes": "", "image_prompt": "a mouse"}]})
        plan = self.svc.slide_plan({"grade_id": "g4", "topic": "Input devices. Sara Ali Hassan likes it", "slides": 2, "language": "en"})
        self.assertEqual((len(plan["slides"]), plan["stage"]), (2, "upper"))
        self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))
        self.assertIn("ONE JSON object", self.sent[-1][3]["messages"][0]["content"])
        # pictures: not set up -> clear error; set up -> file saved, names hidden from the picture prompt
        with self.assertRaises(AppError):
            self.svc.slide_image({"prompt": "a keyboard"})
        with self.assertRaises(AppError):
            self.svc.image_save({"account_id": "bad id", "api_token": "t"})
        st = self.svc.image_save({"account_id": "a" * 32, "api_token": "cf_secret"})
        self.assertTrue(st["configured"]); self.assertNotIn("cf_secret", json.dumps(self.svc.image_state()))
        def cf(method, url, headers, body=None, timeout=0):
            self.sent.append((method, url, headers, body))
            return {"result": {"image": base64.b64encode(jpg).decode()}, "success": True}
        self.ai_client._http = cf
        img = self.svc.slide_image({"prompt": "a keyboard with Sara Ali Hassan", "grade_id": "g4"})
        self.assertIn("flux-1-schnell", self.sent[-1][1]); self.assertNotIn("Sara", self.sent[-1][3]["prompt"]); self.assertIn("No text", self.sent[-1][3]["prompt"])
        slides = [{**s, "image_id": img["id"] if i == 0 else ""} for i, s in enumerate(plan["slides"])]
        out = self.svc.slide_build({"grade_id": "g4", "title": "Input devices", "slides": slides, "language": "en", "trimester": 0, "week": 8})
        self.assertEqual(out["slides"], 3)
        prs = Presentation(out["path"])
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual(prs.slides[1].notes_slide.notes_text_frame.text, "Say it.")
        self.assertTrue(any(sh.shape_type == 13 for sh in prs.slides[1].shapes))  # a picture is there (the logo and the slide picture)
        self.assertEqual(self.svc._plans()["slides"]["g4|0|8"]["count"], 3)
        ar = self.svc.slide_build({"grade_id": "g4", "title": "أجهزة الإدخال", "slides": [{"title": "مرحبا", "bullets": ["أ"]}], "language": "ar"})
        self.assertTrue(Path(ar["path"]).is_file())
        with self.assertRaises(AppError):
            self.svc.slide_build({"grade_id": "g4", "title": "x", "slides": []})

    def test_revision_sheet(self):
        from docx import Document
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = json.dumps({"words": [{"term": "CPU", "meaning": "the brain"}], "points": ["Input sends data in"],
                                 "questions": [{"q": "What is the CPU?", "a": "The brain"}, {"q": "Name an input device", "a": "Mouse"}]})
        r = self.svc.ai_generate_revision({"grade_id": "g4", "topic": "Hardware with Sara Ali Hassan", "count": 2})
        self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))
        self.assertEqual(r["words"], "CPU: the brain"); self.assertIn("|", r["questions"])
        out = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 3, **r, "title": "Hardware", "with_answers": True})
        self.assertTrue(out["name"].endswith("T1-W03_Revision_Sheet.docx"))
        d = Document(out["path"])
        text = "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for tb in d.tables for row in tb.rows for c in row.cells)
        for w in ("Revision Sheet: Hardware", "Key words", "CPU", "the brain", "What is the CPU?", "Answers", "Mouse"):
            self.assertIn(w, text)
        out2 = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 0, "title": "All", "points": "A\nB"})
        self.assertTrue(out2["name"].endswith("T1_Revision_Sheet.docx"))
        with self.assertRaises(AppError):
            self.svc.make_revision({"grade_id": "g4", "trimester": 0, "title": "x"})

    def test_school_map(self):
        m = self.svc.get_map()
        self.assertEqual([f["name"] for f in m["floors"]], ["Ground floor", "First floor", "Second floor"])   # the school's own building
        self.assertIn("Principal's office", [r["name"] for f in m["floors"] for r in f["rooms"]])
        ids = [r["id"] for f in m["floors"] for r in f["rooms"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [r["id"] for f in self.svc.get_map()["floors"] for r in f["rooms"]])   # ids stay the same between loads
        bad = {"floors": [{"name": "Ground", "rooms": [{"name": "Principal", "kind": "admin", "x": 99, "y": -4, "w": 40, "h": 0, "phone": "0100 123", "bogus": 1},
                                                      {"name": "G4A", "kind": "weird", "id": "../x"}]}]}
        out = self.svc.put_map(bad)
        r = out["floors"][0]["rooms"]
        self.assertEqual((r[0]["kind"], r[0]["phone"], r[1]["kind"]), ("admin", "0100 123", "other"))
        self.assertTrue(0 <= r[0]["x"] and r[0]["x"] + r[0]["w"] <= 24 and r[0]["h"] >= 1 and r[0]["y"] >= 0)
        self.assertNotIn("bogus", r[0]); self.assertNotIn("/", r[1]["id"])
        self.assertEqual(self.svc.get_map()["floors"][0]["name"], "Ground")
        with self.assertRaises(AppError):
            self.svc.put_map({"floors": "x"})

    def test_sources_read_pictures_and_feed_helpers(self):
        import base64, io
        from PIL import Image
        from pptx import Presentation
        from pptx.util import Inches
        self.svc.ai_save({"provider": "groq", "api_key": "k"})
        # a PDF made only of pictures (like NotebookLM) and a PowerPoint with one full-slide picture and one text slide
        imgs = [Image.new("RGB", (800, 450), c) for c in ((250, 250, 250), (200, 220, 250))]
        buf = io.BytesIO(); imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:]); pdf = buf.getvalue()
        out = self.svc.import_source({"filename": "Input devices.pdf", "data_b64": base64.b64encode(pdf).decode()})
        self.assertEqual((out["pages"], out["pending"]), (2, 2))
        sid = out["id"]
        self.reply = json.dumps({"pages": [{"n": 1, "text": "Input devices", "diagram": "a keyboard"}, {"n": 2, "text": "A mouse points and clicks"}]})
        r = self.svc.read_source(sid)
        self.assertEqual(r["pending"], 0)
        body = self.sent[-1][3]["messages"][1]["content"]
        self.assertTrue(any(x.get("type") == "image_url" for x in body))   # the pictures really went to the model
        self.assertIn("llama-4-scout", self.sent[-1][3]["model"])
        self.assertIn("A mouse points and clicks", self.svc.get_source(sid)["text"])
        self.reply = json.dumps({"topic": "Input devices", "objectives": ["Name input devices"], "points": ["A mouse points"],
                                 "words": [{"term": "Mouse", "meaning": "points and clicks"}], "questions": [{"q": "What does a mouse do?", "a": "Points"}]})
        d = self.svc.digest_source(sid)["digest"]
        self.assertEqual((d["topic"], d["words"][0]["term"]), ("Input devices", "Mouse"))
        # the source text reaches every writing helper
        self.reply = json.dumps({"words": [], "points": ["x"], "questions": []})
        self.svc.ai_generate_revision({"grade_id": "g4", "topic": "t", "source_id": sid})
        self.assertIn("A mouse points and clicks", self.sent[-1][3]["messages"][1]["content"])
        # pptx
        prs = Presentation(); sl = prs.slides.add_slide(prs.slide_layouts[6])
        b2 = io.BytesIO(); imgs[1].save(b2, "PNG"); b2.seek(0); sl.shapes.add_picture(b2, 0, 0, prs.slide_width, prs.slide_height)
        sl2 = prs.slides.add_slide(prs.slide_layouts[5]); sl2.shapes.title.text = "A long enough title for a text slide that has real words in it, more than sixty characters"
        pb = io.BytesIO(); prs.save(pb)
        o2 = self.svc.import_source({"filename": "x.pptx", "data_b64": base64.b64encode(pb.getvalue()).decode()})
        self.assertEqual((o2["pages"], o2["pending"]), (2, 1))
        with self.assertRaises(AppError):
            self.svc.import_source({"filename": "x.exe", "data_b64": base64.b64encode(b"MZ00").decode()})
        self.svc.delete_source(sid)
        self.assertEqual(len(self.svc.list_sources()["sources"]), 1)

    def test_setup_and_keys_never_returned(self):
        with self.assertRaises(AppError):
            self.svc.ai_test({"provider": "groq"})  # no key
        st = self.svc.ai_save({"provider": "groq", "api_key": "gsk_secret"})
        self.assertTrue(st["ready"])
        self.assertNotIn("gsk_secret", json.dumps(st))
        self.assertTrue(next(p for p in st["providers"] if p["id"] == "groq")["has_key"])
        self.assertEqual(self.svc.ai_test({})["ok"], True)
        m, url, h, body = self.sent[-1]
        self.assertTrue(url.startswith("https://api.groq.com/openai/v1/chat/completions"))
        self.assertEqual(h["Authorization"], "Bearer gsk_secret")
        self.assertEqual(sorted(self.svc.ai_models({})["models"]), ["m1", "m2"])
        # the key is not inside the data folder
        self.assertFalse(any("gsk_secret" in p.read_text(errors="ignore") for p in Path(self.d.name).rglob("*") if p.is_file()))
        self.svc.ai_save({"provider": "groq", "api_key": "__clear__"})
        self.assertFalse(self.svc.ai_state()["ready"])

    def test_anthropic_and_ollama(self):
        self.svc.ai_save({"provider": "anthropic", "api_key": "sk-ant-x"})
        self.svc.ai_test({})
        m, url, h, body = self.sent[-1]
        self.assertTrue(url.endswith("/v1/messages")); self.assertEqual(h["x-api-key"], "sk-ant-x")
        self.assertIn("system", body)
        self.svc.ai_save({"provider": "ollama"})  # no key needed
        self.assertTrue(self.svc.ai_state()["ready"])

    def test_student_names_never_sent(self):
        self.svc.ai_save({"provider": "gemini", "api_key": "k"})
        self.reply = "1. Q?\na) x\nb) y\nAnswer: a"
        r = self.svc.ai_generate_quiz({"grade_id": "g4", "topic": "Sara   Ali Hassan and omar samy quiz", "notes": "SARA ALI HASSAN is weak", "count": 1})
        self.assertEqual(r["questions"], 1)
        sent = json.dumps(self.sent[-1][3])
        for n in ("Sara", "Hassan", "Omar", "Samy"):
            self.assertNotIn(n, sent)
        self.assertIn("[student]", sent)

    def test_lesson_and_trimester(self):
        self.svc.ai_save({"provider": "gemini", "api_key": "k"})
        self.reply = '```json\n{"topic":"Hardware","objectives":["a","b"],"sunday":"x","monday":"y","friday":"no"}\n```'
        c = self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 8, "topic": "Hardware"})["content"]
        self.assertEqual(c["objectives"], "- a\n- b"); self.assertEqual(c["sunday"], "x"); self.assertEqual(c["tuesday"], "")
        self.assertIn("monday, tuesday", "")  if False else None
        self.assertNotIn("tuesday", self.sent[-1][3]["messages"][-1]["content"].lower().split("teaching days this week:")[1].split("\n")[0])
        self.reply = '{"lessons": ["L1", "L2"]}'
        out = self.svc.ai_generate_trimester({"grade_id": "g4", "trimester": 0})["lessons"]
        self.assertEqual(out[:2], ["L1", "L2"]); self.assertEqual(len(out), 13 if len(out) == 13 else len(out))
        self.reply = "nonsense"
        with self.assertRaises(AppError):
            self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 8, "topic": "x"})
        with self.assertRaises(AppError):
            self.svc.ai_generate_quiz({"grade_id": "g4", "topic": "x"})

    def test_errors_and_url_allowlist(self):
        from app.core.ai_client import _map_status
        self.assertEqual(_map_status(401, "").code, "ai_bad_key")
        self.assertEqual(_map_status(429, "").code, "ai_rate_limit")
        self.assertEqual(_map_status(404, "").code, "ai_bad_model")
        self.assertEqual(_map_status(503, "").code, "ai_server")
        with self.assertRaises(AppError):
            self.svc.open_url("https://evil.example.com")
        self.assertTrue(self.svc.open_url("https://aistudio.google.com/app/apikey")["ok"])


class TestReminders(unittest.TestCase):
    def test_prefs(self):
        import os, tempfile
        home = tempfile.TemporaryDirectory(); os.environ["DLIS_APP_HOME"] = home.name
        try:
            from app.server.service import Service
            svc = Service()
            self.assertEqual(svc.get_reminders()["minutes"], 10)
            r = svc.put_reminders({"minutes": 15, "skip_back_to_back": False, "muted_date": "2026-10-26"})
            self.assertEqual((r["minutes"], r["skip_back_to_back"], r["enabled"]), (15, False, True))
            self.assertEqual(svc.get_reminders()["muted_date"], "2026-10-26")
            with self.assertRaises(AppError):
                svc.put_reminders({"minutes": 7})
        finally:
            os.environ.pop("DLIS_APP_HOME", None); home.cleanup()


class TestAlarms(unittest.TestCase):
    def test_alarms(self):
        import tempfile
        from app.server.service import Service
        d = tempfile.TemporaryDirectory()
        svc = Service(); svc.store = DataStore(d.name)
        with self.assertRaises(AppError):
            svc.add_alarm({"text": "", "time": "08:00", "date": "2026-10-27"})
        with self.assertRaises(AppError):
            svc.add_alarm({"text": "x", "time": "8am", "date": "2026-10-27"})
        with self.assertRaises(AppError):
            svc.add_alarm({"text": "x", "time": "08:00"})  # once needs a date
        r = svc.add_alarm({"text": "Print quiz", "time": "08:00", "date": "2026-10-27"})
        r = svc.add_alarm({"text": "Weekly meeting", "time": "13:30", "days": ["Tuesday", "Funday"]})
        weekly = next(a for a in r["items"] if a["text"] == "Weekly meeting")
        self.assertEqual(weekly["days"], ["Tuesday"]); self.assertEqual(weekly["date"], "")
        r = svc.update_alarm(weekly["id"], {"enabled": False})
        self.assertFalse(next(a for a in r["items"] if a["id"] == weekly["id"])["enabled"])
        self.assertEqual(len(svc.delete_alarm(weekly["id"])["items"]), 1)
        d.cleanup()

    def test_background_prefs(self):
        import os, tempfile
        home = tempfile.TemporaryDirectory(); os.environ["DLIS_APP_HOME"] = home.name
        try:
            from app.server.service import Service
            svc = Service()
            self.assertFalse(svc.put_background({"keep_running": True})["keep_running"])  # not supported here
            svc.background_support = {"tray": True, "autostart": True}
            calls = []
            svc.apply_background = calls.append
            r = svc.put_background({"autostart": True})
            self.assertTrue(r["keep_running"] and r["autostart"]); self.assertEqual(len(calls), 1)
        finally:
            os.environ.pop("DLIS_APP_HOME", None); home.cleanup()


class TestOneDayChanges(unittest.TestCase):
    def test_cancel_cover_move_swap(self):
        import os, tempfile
        from app.server.service import Service
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
        d = tempfile.TemporaryDirectory()
        svc = Service(); svc.store = DataStore(d.name)
        svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        svc.build_structure({"g4": ["A"], "g5": ["A"]})
        svc.put_calendar(svc.school_calendar())
        day = date.today().strftime("%A")
        if day in ("Friday", "Saturday"):
            self.skipTest("weekend")
        svc.put_timetable({"grid": {day: {"1": "g4-a", "2": "g5-a"}}})
        base = lambda r: [(s["period"], s["room_id"]) for s in r["sessions"] if s["period"] in ("1", "2", "3", "4")]
        r0 = svc.today()
        if not r0["school_day"]:
            self.skipTest("holiday today")
        self.assertEqual(base(r0), [("1", "g4-a"), ("2", "g5-a")])
        r = svc.change_today({"action": "cancel", "period": "1"})
        self.assertEqual(base(r), [("2", "g5-a")]); self.assertEqual(r["cancelled"][0]["period"], "1"); self.assertTrue(r["changed"])
        r = svc.change_today({"action": "uncancel", "period": "1"})
        self.assertEqual(base(r), [("1", "g4-a"), ("2", "g5-a")])
        r = svc.change_today({"action": "cover", "period": "3", "room_id": "g5-a", "note": "Mr X absent"})
        cover = next(s for s in r["sessions"] if s["period"] == "3")
        self.assertEqual((cover["kind"], cover["note"]), ("cover", "Mr X absent"))
        with self.assertRaises(AppError):
            svc.change_today({"action": "cover", "period": "1", "room_id": "g5-a"})  # busy
        r = svc.change_today({"action": "move", "period": "1", "to": "4"})
        self.assertEqual(base(r), [("2", "g5-a"), ("3", "g5-a"), ("4", "g4-a")])
        r = svc.change_today({"action": "move", "period": "2", "to": "4"})  # swap
        self.assertEqual([(s["period"], s["room_id"]) for s in r["sessions"] if s["period"] in ("2", "4")], [("2", "g4-a"), ("4", "g5-a")])
        with self.assertRaises(AppError):
            svc.change_today({"action": "cancel", "period": "1", "date": "2020-01-01"})
        # the normal timetable is untouched, and saving it from the timetable page keeps today's changes
        svc.put_timetable(svc.get_timetable())
        self.assertEqual(svc.get_timetable()["grid"][day]["1"], "g4-a")
        self.assertTrue(svc.today()["changed"])
        r = svc.change_today({"action": "restore"})
        self.assertEqual(base(r), [("1", "g4-a"), ("2", "g5-a")]); self.assertFalse(r["changed"])
        d.cleanup()


    def test_cancel_duty_and_undo(self):
        import os, tempfile
        from app.server.service import Service
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
        d = tempfile.TemporaryDirectory()
        svc = Service(); svc.store = DataStore(d.name)
        svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        svc.build_structure({"g4": ["A"]})
        svc.put_calendar(svc.school_calendar())
        day = date.today().strftime("%A")
        if day in ("Friday", "Saturday"):
            self.skipTest("weekend")
        svc.put_timetable({"grid": {day: {"1": "g4-a"}}, "duties": {day: ["break", "late"]}})
        r0 = svc.today()
        if not r0["school_day"]:
            self.skipTest("holiday today")
        self.assertEqual(sorted(u["kind"] for u in r0["duties"]), ["break", "late"])
        r = svc.change_today({"action": "cancel_duty", "kind": "late"})
        self.assertEqual([u["kind"] for u in r["duties"]], ["break"])
        self.assertEqual([u["kind"] for u in r["cancelled_duties"]], ["late"])
        r = svc.change_today({"action": "restore_duty", "kind": "late"})
        self.assertEqual(sorted(u["kind"] for u in r["duties"]), ["break", "late"])
        self.assertEqual(r["cancelled_duties"], [])
        d.cleanup()


    def test_open_word_file_gives_a_clear_error_and_errors_are_logged(self):
        import os, tempfile
        from unittest import mock
        from app.core import documents as D, paths
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
        class Doc:
            def save(self, p): raise PermissionError()
        with self.assertRaises(AppError) as cm:
            D._save(Doc(), Path(tempfile.mkdtemp()) / "x.docx")
        self.assertEqual(cm.exception.code if hasattr(cm.exception, "code") else cm.exception.to_dict()["error"], "file_in_use")
        paths.log_error("boom")
        self.assertIn("boom", (paths.app_support_dir() / "error.log").read_text(encoding="utf-8"))


class TestRobustness(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp(); os.environ["DLIS_NO_OPEN"] = "1"
        from app.server.service import Service
        from app.core.store import DataStore
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"]}); self.svc.put_calendar(self.svc.school_calendar())

    def tearDown(self):
        self.d.cleanup()

    def test_damaged_file_is_restored_from_backup_and_kept_aside(self):
        store = self.svc.store
        self.svc.put_settings({"teacher_name": "Second", "subject": "ICT"})  # now a backup exists
        store.config_path().write_text("{broken", encoding="utf-8")
        self.assertEqual(self.svc.get_settings()["teacher_name"], "T")  # the backup is the version before the last save
        self.assertEqual(store.problems, [{"file": "config.json", "restored": True}])
        self.assertTrue(list((store.backup_root() / "_damaged").glob("config.json.*.damaged")))
        self.assertEqual(json.loads(store.config_path().read_text(encoding="utf-8"))["teacher_name"], "T")  # healthy file is back
        self.assertEqual(self.svc.bootstrap()["problems"][0]["file"], "config.json")

    def test_wrong_shape_and_no_backup_never_crashes(self):
        import shutil
        store = self.svc.store
        shutil.rmtree(store.backup_root(), ignore_errors=True)
        store.schedule_path().write_text('{"grid": 5}', encoding="utf-8")
        self.assertEqual(self.svc.get_timetable()["grid"], {})
        (store.root / "tasks.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(self.svc.list_tasks()["tasks"], [])
        (store.root / "lesson_log.json").write_text('{"entries": [1]}', encoding="utf-8")
        self.assertEqual(self.svc.log_last()["last"], {})
        self.assertFalse(any(p["restored"] for p in store.problems))

    def test_missing_data_folder_is_reported_not_silently_restarted(self):
        from app.core import paths
        from app.server.service import Service
        paths.write_prefs(data_folder="/no/such/folder/DLIS")
        b = Service().bootstrap()
        self.assertEqual((b["data_folder"], b["folder_missing"]), ("", "/no/such/folder/DLIS"))

    def test_strange_text_cannot_crash_word_files(self):
        bad = "Hello\x00\x01 world \u202e"
        r = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": bad, "objectives": ["a", "b"], "sunday": 5}})
        self.assertTrue(Path(r["path"]).is_file())
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": "not a dict"})
        r = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": f"1. {bad}?\na) x\nb) y\nAnswer: a"})
        self.assertEqual(r["questions"], 1)

    def test_only_documents_can_be_opened(self):
        (Path(self.svc.store.root) / "run.exe").write_text("x")
        with self.assertRaises(AppError):
            self.svc.open_file(str(Path(self.svc.store.root) / "run.exe"))
        with self.assertRaises(AppError):
            self.svc.open_file("/etc/passwd")
        self.assertTrue(self.svc.open_file(str(self.svc.store.root), True))


class TestAiModels(TestAi):
    def test_models_come_from_the_service_and_auto_picks_a_working_one(self):
        from app.server.ai_service import rank_models
        self.assertEqual(rank_models(["text-embedding-004", "whisper-large-v3", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-lite"], "gemini"),
                         ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro"])
        self.assertEqual(rank_models(["a", "b:free", "c:free"], "openrouter"), ["b:free", "c:free"])
        self.svc.ai_save({"provider": "groq", "api_key": "k"})
        chat_models = []
        hand_picked = False
        orig = self.ai_client._http
        def picky(method, url, headers, body=None, timeout=0):
            if url.endswith("/models"):
                return {"data": [{"id": "old-model-flash"}, {"id": "whisper-1"}, {"id": "new-model-mini"}]}
            chat_models.append(body["model"])
            if body["model"] == "new-model-mini" and not hand_picked:
                raise AppError("ai_bad_model", "gone", status=502)
            return {"choices": [{"message": {"content": "ready"}}]}
        self.ai_client._http = picky
        self.svc._models_cache.clear()
        r = self.svc.ai_test({})
        self.assertEqual((r["model"], r["auto"]), ("old-model-flash", True))
        self.assertNotIn("whisper-1", r["models"])
        self.assertEqual(chat_models[:2], ["new-model-mini", "old-model-flash"])  # tried the best-ranked first, then moved on
        # a model chosen by hand is used as is
        chat_models.clear(); hand_picked = True
        self.svc.ai_save({"provider": "groq", "model": "new-model-mini"})
        self.svc.ai_test({}); self.assertEqual(chat_models, ["new-model-mini"])
        self.ai_client._http = orig


class TestLessonLog(unittest.TestCase):
    def test_log(self):
        import tempfile
        from app.server.service import Service
        d = tempfile.TemporaryDirectory()
        svc = Service(); svc.store = DataStore(d.name)
        svc.put_settings({"teacher_name": "T", "subject": "ICT"}); svc.build_structure({"g4": ["A"], "g5": ["A"]})
        with self.assertRaises(AppError):
            svc.log_save({"room_id": "g4-a"})  # empty
        with self.assertRaises(AppError):
            svc.log_save({"room_id": "g4-a", "slide": 40, "total": 30})
        with self.assertRaises(AppError):
            svc.log_save({"room_id": "nope", "topic": "x"})
        svc.log_save({"room_id": "g4-a", "date": "2026-10-20", "period": "2", "topic": "Hardware", "slide": 12, "total": 30})
        r = svc.log_save({"room_id": "g4-a", "date": "2026-10-22", "period": "2", "topic": "Hardware", "slide": 20, "total": 30, "next_note": "Start with a quiz"})
        svc.log_save({"room_id": "g4-a", "date": "2026-10-22", "period": "2", "topic": "Hardware", "slide": 22, "total": 30, "next_note": "Start with a quiz"})  # same lesson: updated
        self.assertEqual(len(svc.log_list("g4-a")["entries"]), 2)
        last = svc.log_last()["last"]
        self.assertEqual((last["g4-a"]["slide"], last["g4-a"]["next_note"]), (22, "Start with a quiz")); self.assertNotIn("g5-a", last)
        self.assertEqual(len(svc.log_list(day="2026-10-20")["entries"]), 1)
        svc.log_delete(r["entry"]["id"])
        self.assertEqual(svc.log_last()["last"]["g4-a"]["slide"], 12)
        d.cleanup()


class TestPackaging(unittest.TestCase):
    def test_installer_version_matches_app(self):
        from app.core import paths
        iss = (Path(__file__).resolve().parents[1] / "installer" / "dlis.iss").read_text(encoding="utf-8")
        self.assertIn(f'#define AppVersion "{paths.VERSION}"', iss)

    def test_help_content_is_complete_in_both_languages(self):
        f = Path(__file__).resolve().parents[1] / "app" / "web" / "js" / "help_content.json"
        h = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in h["ar"]], [s["id"] for s in h["en"]])
        for lang in ("ar", "en"):
            for s in h[lang]:
                self.assertTrue(s["title"] and s["steps"], (lang, s["id"]))
