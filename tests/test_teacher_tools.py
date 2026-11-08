import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helpers import AiCase   # sets the import path and blocks the real internet
from app.core.errors import AppError
from app.core.store import DataStore


class TestTeacherTools(AiCase):
    def test_catalog_is_well_formed(self):
        from app.server.tools_catalog import TOOLS, GROUPS
        cat = self.svc.tools_catalog()
        self.assertEqual(len(cat["tools"]), len(TOOLS)); self.assertGreaterEqual(len(TOOLS), 27)
        ids = [x["id"] for x in TOOLS]
        self.assertEqual(len(ids), len(set(ids)))
        groups = {g[0] for g in GROUPS}
        for x in TOOLS:
            self.assertIn(x["group"], groups)
            for k in ("en", "ar"):
                self.assertTrue(x["name"][k] and x["desc"][k], x["id"])
            self.assertTrue(x["instruction"].strip(), x["id"])
            self.assertTrue(x["fields"], x["id"])
            self.assertTrue(any(f["required"] for f in x["fields"]), x["id"])
            keys = [f["key"] for f in x["fields"]]
            self.assertEqual(len(keys), len(set(keys)), x["id"])
            for f in x["fields"]:
                self.assertTrue(f["label"]["en"] and f["label"]["ar"], x["id"])
                self.assertIn(f["type"], ("text", "textarea", "number", "select"))
                if f["type"] == "select":
                    self.assertTrue(f["options"], x["id"])

    def test_run_asks_ai_hides_names_and_cleans_markdown(self):
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = "**Rubric**\n## Criteria\n- Clear | Good | Weak"
        r = self.svc.tools_run({"tool": "rubric", "grade_id": "g4", "language": "ar",
                                "values": {"task": "Poster about Sara Ali Hassan's hobby", "criteria": "Clarity", "levels": "4"}})
        self.assertNotIn("**", r["text"]); self.assertNotIn("#", r["text"]); self.assertIn("Rubric", r["text"])
        body = json.dumps(self.sent[-1][3])
        self.assertNotIn("Sara", body); self.assertIn("Arabic", body); self.assertIn("ICT", body)
        with self.assertRaises(AppError):
            self.svc.tools_run({"tool": "rubric", "values": {}})                 # a required field is empty
        with self.assertRaises(AppError):
            self.svc.tools_run({"tool": "nope", "values": {}})

    def test_run_stays_inside_the_chosen_source(self):
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        import base64
        sid = self.svc.import_source({"filename": "Unit 1.txt", "data_b64": base64.b64encode(("The mouse is an input device. " * 30).encode()).decode()})["id"]
        self.reply = "ok"
        self.svc.tools_run({"tool": "summarizer", "values": {"text": "x", "length": "short"}, "source_id": sid})
        self.assertIn("SOURCE MATERIAL", json.dumps(self.sent[-1][3]))

    def test_word_file_with_table_and_arabic(self):
        from docx import Document
        text = "Unit plan\n- Aim one\n- Aim two\nCriterion | Good | Weak\nClear | 4 | 1\n1. Start\nعنوان بالعربي\n- نقطة"
        out = self.svc.tools_word({"tool": "unit_plan", "text": text, "grade_id": "g4"})
        self.assertTrue(Path(out["path"]).exists())
        doc = Document(out["path"])
        alltext = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for tb in doc.tables for r in tb.rows for c in r.cells)
        self.assertIn("Aim one", alltext); self.assertIn("نقطة", alltext); self.assertTrue(doc.tables)
        out2 = self.svc.tools_word({"tool": "unit_plan", "text": text, "grade_id": "g4"})
        self.assertNotEqual(out["path"], out2["path"])                           # a second save never replaces the first
        out3 = self.svc.tools_word({"tool": "unit_plan", "text": text})          # no class chosen
        self.assertIn("Tools", out3["rel"])
        with self.assertRaises(AppError):
            self.svc.tools_word({"tool": "unit_plan", "text": "  "})

    def test_student_tools_cannot_be_shared(self):
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        out = self.svc.tools_word({"tool": "report_comment", "text": "[student] works hard.", "grade_id": "g4"})
        mine = [f for f in self.svc.library_list()["items"] if f["name"] == out["name"]]
        self.assertTrue(mine and mine[0]["private"])
        ok = self.svc.tools_word({"tool": "rubric", "text": "Rubric", "grade_id": "g4"})
        self.assertFalse([f for f in self.svc.library_list()["items"] if f["name"] == ok["name"]][0]["private"])

    def test_answers_from_my_sources_with_slide_numbers(self):
        import base64
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        text = "The mouse is an input device. " * 30
        sid = self.svc.import_source({"filename": "Unit 1.txt", "data_b64": base64.b64encode(text.encode()).decode()})["id"]
        self.reply = "ok"
        self.svc.ai_chat({"messages": [{"role": "user", "content": "What is a mouse?"}], "source_id": sid})
        system = self.sent[-1][3]["messages"][0]["content"]
        self.assertIn("SOURCE MATERIAL", system); self.assertIn("[Slide 3]", system); self.assertIn("do not guess", system)
        self.svc.ai_chat({"messages": [{"role": "user", "content": "What is a mouse?"}]})          # no source: nothing added
        self.assertNotIn("SOURCE MATERIAL", self.sent[-1][3]["messages"][0]["content"])
        self.svc.tools_run({"tool": "summarizer", "values": {"text": "x", "length": "One paragraph"}, "source_id": sid, "cite": True})
        self.assertIn("[Slide 3]", json.dumps(self.sent[-1][3]))
        self.svc.tools_run({"tool": "summarizer", "values": {"text": "x", "length": "One paragraph"}, "source_id": sid})
        self.assertNotIn("[Slide 3]", json.dumps(self.sent[-1][3])); self.assertIn("SOURCE MATERIAL", json.dumps(self.sent[-1][3]))


class TestGradeFillAndReminder(AiCase):
    def test_full_mark_fill_skips_the_absent(self):
        from docx import Document
        out = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 3, "lang": "ar", "fill": ["behavior", "classwork", "nonsense"], "absent": ["عمر سامي"]})
        rows = Document(out["path"]).tables[1].rows
        self.assertEqual([c.text for c in rows[1].cells][2:7], ["2"] * 5)         # behaviour: 5 boxes x 2 = 10
        self.assertEqual([c.text for c in rows[1].cells][12:17], ["3"] * 5)        # classwork: 5 x 3 = 15
        self.assertEqual([c.text for c in rows[1].cells][7:12], [""] * 5)          # a part that was not chosen stays empty
        self.assertTrue(all(c.text == "" for c in rows[2].cells[2:]))              # the absent student stays empty
        plain = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 3, "lang": "ar"})
        self.assertTrue(all(c.text == "" for c in Document(plain["path"]).tables[1].rows[1].cells[2:]))
        from openpyxl import load_workbook
        x = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 3, "lang": "ar", "format": "xlsx", "fill": ["behavior", "attendance", "classwork", "homework"], "absent": ["عمر سامي"]})
        ws = load_workbook(x["path"]).active
        self.assertEqual([ws.cell(3, 3).value, ws.cell(4, 3).value], [50, None])


class TestTomorrowAlert(AiCase):
    def test_evening_alert_finds_next_lessons_and_missing_plans(self):
        from datetime import date, timedelta
        wk = self.svc.overview()["trimesters"][0]["weeks"]
        w = wk[3]
        sun = date.fromisoformat(w["start"])
        while sun.weekday() != 6:                                    # a Sunday inside the term
            sun += timedelta(days=1)
        r = self.svc.tomorrow_prep(sun.isoformat())                  # Sunday evening -> Monday lesson
        self.assertTrue(r["found"] and r["tomorrow"]); self.assertEqual(r["date"], (sun + timedelta(days=1)).isoformat())
        self.assertEqual(r["lessons"], 1); self.assertEqual(len(r["missing"]), 1)
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": w["number"], "content": {"topic": "Hardware"}})
        self.assertEqual(self.svc.tomorrow_prep(sun.isoformat())["missing"], [])
        thu = sun + timedelta(days=4)                                # Thursday evening -> Sunday, said with its date
        r = self.svc.tomorrow_prep(thu.isoformat())
        self.assertTrue(r["found"]); self.assertFalse(r["tomorrow"])
        fri = sun + timedelta(days=5)                                # the weekend itself: no alert
        self.assertFalse(self.svc.tomorrow_prep(fri.isoformat())["found"])
        self.assertTrue(self.svc.get_reminders()["tomorrow"]); self.assertEqual(self.svc.put_reminders({"tomorrow_time": "20:30"})["tomorrow_time"], "20:30")
        with self.assertRaises(AppError):
            self.svc.put_reminders({"tomorrow_time": "25:00"})


class TestGrades(AiCase):
    def test_marks_are_kept_checked_imported_and_uploaded(self):
        import base64
        from unittest import mock
        names = self.svc.get_students("g4-a")["names"]
        base = {"room_id": "g4-a", "trimester": 0, "week": 3}
        out = self.svc.grades_put({**base, "rows": [{"name": names[0], "marks": {"behavior": 10, "attendance": "10", "quiz": 18.5}}, {"name": names[1], "absent": True, "marks": {"behavior": 5}}, {"name": "nobody"}]})
        self.assertEqual(out["students"][0]["marks"], {"behavior": 10, "attendance": 10, "quiz": 18.5})
        self.assertTrue(out["students"][1]["absent"]); self.assertEqual(out["students"][1]["marks"], {})
        with self.assertRaises(AppError):
            self.svc.grades_put({**base, "rows": [{"name": names[0], "marks": {"behavior": 11}}]})
        self.assertEqual(self.svc.grades_get("g4-a", 0, 3)["students"][0]["marks"]["quiz"], 18.5)   # the bad save changed nothing
        csv_text = "Student Name,Grade (50)\nSara Ali Hassan,45\nOmar Samy,40\nSomeone Else,10\n"
        r = self.svc.grades_import({**base, "filename": "lms.csv", "data_b64": base64.b64encode(csv_text.encode()).decode()})
        self.assertEqual(r["imported"], 2); self.assertEqual(r["unmatched"], ["Someone Else"]); self.assertEqual(r["lms_max"], 50)
        self.assertEqual([s["marks"].get("lms") for s in r["students"]], [45, 40]); self.assertFalse(r["students"][1]["absent"])
        # upload: students are found on the school server by name; absent ones are cleared there
        calls = []
        class Fake:
            def select(self, table, q): calls.append(("select", table, q)); return [{"code": "s1", "display_name": names[0]}, {"code": "s2", "display_name": names[1]}]
            def upsert(self, table, rows, on): calls.append(("upsert", table, rows, on))
            def delete(self, table, q): calls.append(("delete", table, q))
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "teacher"}), mock.patch.object(self.svc, "_cloud_client", return_value=Fake()):
            res = self.svc.grades_upload(base)
        up = [c for c in calls if c[0] == "upsert"][0]
        self.assertEqual(res["sent"], 2); self.assertEqual({r["item"] for r in up[2]}, {"Behavior", "Attendance", "Quiz", "Total"})
        self.assertTrue(all(r["subject"] == "ICT" and r["trimester"] == 0 and r["week"] == 3 for r in up[2]))
        self.assertEqual(up[3], "student_code,trimester,week,subject,item")
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "parent"}):
            with self.assertRaises(AppError):
                self.svc.grades_upload(base)
        self.assertTrue(self.svc.grades_get("g4-a", 0, 3)["uploaded"])


class TestInsights(AiCase):
    def test_class_overview_from_marks_and_log(self):
        names = self.svc.get_students("g4-a")["names"]
        for week, rows in ((2, [{"name": names[0], "marks": {"behavior": 10, "classwork": 15}}, {"name": names[1], "marks": {"behavior": 2, "classwork": 3}}]),
                            (3, [{"name": names[0], "marks": {"behavior": 10}}, {"name": names[1], "absent": True}]),
                            (4, [{"name": names[0], "marks": {"quiz": 20}}, {"name": names[1], "absent": True}])):
            self.svc.grades_put({"room_id": "g4-a", "trimester": 0, "week": week, "rows": rows})
        r = self.svc.insights_get("g4-a", 0)
        self.assertEqual([w["week"] for w in r["weeks"]], [2, 3, 4])
        self.assertEqual(r["weeks"][0]["avg"], 60)                    # (100 + 20) / 2
        self.assertEqual(r["weeks"][1]["marked"], 1); self.assertEqual(r["absences"], 2)
        a, b = r["rows"]
        self.assertEqual(a["avg"], 100); self.assertFalse(a["attention"])
        self.assertEqual((b["avg"], b["absent"]), (20, 2)); self.assertTrue(b["attention"])
        self.assertEqual(self.svc.insights_get("g4-a", 1)["weeks"], [])


class TestSchemeUnits(AiCase):
    def test_unit_and_curriculum_objectives_reach_the_ai_and_the_files_page(self):
        w = self.svc.overview()["trimesters"][0]["weeks"][3]["number"]
        self.svc.scheme_put({"grade_id": "g4", "trimester": 0, "weeks": [{"week": w, "topic": "Hardware", "unit": "Unit 2: Computers", "objectives": "Name the parts\n\nExplain what a CPU does"}]})
        got = [x for x in self.svc.scheme_get("g4", 0)["weeks"] if x["week"] == w][0]
        self.assertEqual((got["unit"], got["objectives"]), ("Unit 2: Computers", "Name the parts\nExplain what a CPU does"))
        top = [x for x in self.svc.slide_topics("g4", 0)["weeks"] if x["week"] == w][0]
        self.assertEqual((top["unit"], top["curriculum"]), ("Unit 2: Computers", "Name the parts\nExplain what a CPU does"))
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = json.dumps({"topic": "Hardware"})
        self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": w, "topic": "hardware"})
        sent = json.dumps(self.sent[-1][3])
        self.assertIn("CURRICULUM OBJECTIVES", sent); self.assertIn("Explain what a CPU does", sent)


class TestLessonLog(unittest.TestCase):
    def test_log(self):
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


class TestReminders(unittest.TestCase):
    def test_prefs(self):
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
        from app.core import documents as D, paths
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
        class Doc:
            def save(self, p): raise PermissionError()
        with self.assertRaises(AppError) as cm:
            D._save(Doc(), Path(tempfile.mkdtemp()) / "x.docx")
        self.assertEqual(cm.exception.code if hasattr(cm.exception, "code") else cm.exception.to_dict()["error"], "file_in_use")
        paths.log_error("boom")
        self.assertIn("boom", (paths.app_support_dir() / "error.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
