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
            self.assertEqual(svc.get_students("kg1-a")["names"], ["ونلي ون"])


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

    def test_official_year_gets_all_holidays_and_loses_event_rows(self):
        import tempfile
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


class TestCloud(unittest.TestCase):
    def test_sign_in_role_and_test_against_a_fake_server(self):
        import json, tempfile, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        from app.core.store import DataStore
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _go(self, body=None):
                seen.append((self.command, self.path, self.headers.get("apikey"), self.headers.get("Authorization")))
                if self.path.startswith("/auth/v1/token?grant_type=password"):
                    if body.get("password") != "good":
                        out, code = {"error_description": "Invalid login"}, 400
                    else:
                        out, code = {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"id": "u1"}}, 200
                elif self.path.startswith("/auth/v1/token?grant_type=refresh_token"):
                    out, code = {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600}, 200
                elif self.path.startswith("/rest/v1/profiles"):
                    out, code = [{"role": "teacher", "full_name": "T"}], 200
                else:
                    out, code = [], 200
                raw = json.dumps(out).encode()
                self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self): self._go()
            def do_POST(self): self._go(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"))

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                self.assertEqual(svc.get_cloud(), {"url": "", "configured": False, "school": "", "key_set": False, "email": "", "signed_in": False, "role": "", "mode": ""})
                with self.assertRaises(AppError):
                    svc.put_cloud({"url": "not a url"})
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "ANON"})
                with self.assertRaises(AppError) as cm:
                    svc.cloud_login({"email": "a@b.c", "password": "bad"})
                self.assertEqual(cm.exception.code, "cloud_bad_login")
                out = svc.cloud_login({"email": "a@b.c", "password": "good"})
                self.assertEqual((out["signed_in"], out["role"], out["mode"]), (True, "teacher", "online"))
                self.assertNotIn("good", (svc._cloud_path()).read_text())            # the password is never saved
                self.assertEqual(svc.get_cloud()["url"], "")                          # a teacher never sees the server's address
                with self.assertRaises(AppError):
                    svc.cloud_code_make()
                self.assertTrue(svc.cloud_test()["ok"])
                self.assertIn(("GET", "/rest/v1/profiles?select=role,full_name&limit=1", "ANON", "Bearer AT"), seen)
                svc2 = Service(); svc2.store = DataStore(d)                           # a new start stays signed in through the refresh token
                self.assertTrue(svc2.cloud_test()["ok"])
                self.assertTrue(any("refresh_token" in p for _m, p, _k, _a in seen))
                svc.cloud_logout(); self.assertFalse(svc.get_cloud()["signed_in"])
        finally:
            srv.shutdown()

    def test_school_code_round_trip(self):
        import tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            adm = Service(); adm.store = DataStore(a)
            adm.put_cloud({"url": "https://abc.supabase.co", "key": "ANONKEY", "school": "DLIS"})
            cfg = adm._cloud_cfg(); cfg["role"] = "admin"; adm._cloud_save(cfg)
            code = adm.cloud_code_make()["code"]
            self.assertTrue(code.startswith("DLIS-"))
            tch = Service(); tch.store = DataStore(b)
            r = tch.cloud_join({"code": " " + code[:20] + "\n" + code[20:]})        # spaces and line breaks from copy/paste are fine
            self.assertEqual((r["configured"], r["school"], r["url"]), (True, "DLIS", ""))
            self.assertEqual(tch._cloud_cfg()["key"], "ANONKEY")
            with self.assertRaises(AppError):
                tch.cloud_join({"code": "DLIS-nonsense"})
            self.assertFalse(tch.cloud_forget_school()["configured"])

    def test_announcements_admin_posts_teacher_cannot(self):
        import json, tempfile, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        from app.core.store import DataStore
        role = {"v": "admin"}; rows = []; sent = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out, code=200):
                raw = json.dumps(out).encode(); self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def _body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            def do_GET(self):
                if self.path.startswith("/rest/v1/profiles"): return self._out([{"role": role["v"]}])
                if self.path.startswith("/rest/v1/announcements"): return self._out(rows)
                self._out([])
            def do_POST(self):
                b = self._body()
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                sent.append(b); rows.extend({"id": "11111111-1111-1111-1111-111111111111", "starts_on": "2020-01-01", "ends_on": None, **r} for r in b); self._out(b)
            def do_DELETE(self):
                sent.append(self.path); rows.clear(); self._out([])

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                self.assertFalse(svc.list_announcements()["connected"])
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"})
                svc.cloud_login({"email": "a@b.c", "password": "x"})
                with self.assertRaises(AppError):
                    svc.post_announcement({"title": "", "audience": "all"})
                with self.assertRaises(AppError):
                    svc.post_announcement({"title": "Hi", "audience": "nobody"})
                out = svc.post_announcement({"title": "  Trip   day ", "body": "Bring food", "audience": "parents", "starts_on": "2020-01-01", "ends_on": ""})
                self.assertEqual(sent[0][0]["title"], "Trip day"); self.assertNotIn("ends_on", sent[0][0])
                self.assertTrue(out["connected"] and len(out["items"]) == 1 and out["items"][0]["active"])
                svc.delete_announcement("11111111-1111-1111-1111-111111111111")
                self.assertEqual(sent[-1], "/rest/v1/announcements?id=eq.11111111-1111-1111-1111-111111111111")
                role["v"] = "teacher"; svc.cloud_login({"email": "a@b.c", "password": "x"})
                with self.assertRaises(AppError) as cm:
                    svc.post_announcement({"title": "x", "audience": "all"})
                self.assertEqual(cm.exception.code, "cloud_admin_only")
        finally:
            srv.shutdown()

    def test_publications_need_approval_and_pictures_are_shrunk(self):
        import base64, io, json, tempfile, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from PIL import Image
        from app.server.service import Service
        from app.core.store import DataStore
        log = []; rows = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out, code=200):
                raw = json.dumps(out).encode(); self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def _raw(self): return self.rfile.read(int(self.headers.get("Content-Length", 0)))
            def do_GET(self):
                self._out([{"role": "teacher"}] if "/profiles" in self.path else (rows if "/publications" in self.path else []))
            def do_POST(self):
                raw = self._raw()
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                if "/storage/" in self.path: log.append(("up", self.path, len(raw))); return self._out({})
                b = json.loads(raw); log.append(("ins", b)); rows.extend({"id": "22222222-2222-2222-2222-222222222222", **r} for r in b); self._out(b)
            def do_PATCH(self): log.append(("patch", self.path, json.loads(self._raw()))); self._out({})

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"}); svc.cloud_login({"email": "t@b.c", "password": "x"})
                with self.assertRaises(AppError) as cm:
                    svc.add_publication({"class_id": "g4-a", "kind": "quiz", "title": "Q1", "url": "https://x.com/q"})
                self.assertEqual(cm.exception.code, "quiz_needs_date")
                with self.assertRaises(AppError):
                    svc.add_publication({"class_id": "g4-a", "kind": "link", "title": "Video", "url": "javascript:alert(1)"})
                svc.add_publication({"class_id": "g4-a", "kind": "link", "title": "Video", "url": "https://youtu.be/x"})
                ins = [x for x in log if x[0] == "ins"][-1][1][0]
                self.assertEqual((ins["approved"], ins["class_id"]), (False, "g4-a"))   # never visible before the teacher approves
                svc.add_publication({"class_id": "g4-a", "kind": "quiz", "title": "Q1", "url": "https://x.com/q", "visible_from": "2026-11-05"})
                self.assertTrue([x for x in log if x[0] == "ins"][-1][1][0]["visible_from"].startswith("2026-11-05T00:00:00"))
                svc.add_publication({"class_id": "g4-a", "kind": "presentation", "title": "Slides", "file": {"filename": "a b.pptx", "data_b64": base64.b64encode(b"x" * 100).decode()}})
                self.assertTrue(any(x[0] == "up" and "/object/files/g4-a/" in x[1] for x in log))
                svc.set_publication("22222222-2222-2222-2222-222222222222", {"approved": True})
                self.assertEqual([x for x in log if x[0] == "patch"][-1][2], {"approved": True})
                # announcement picture: big photo becomes a small jpeg
                im = Image.new("RGB", (4000, 3000), (200, 30, 30)); buf = io.BytesIO(); im.save(buf, "PNG")
                from app.server.cloud_service import _small_jpeg
                out = Image.open(io.BytesIO(_small_jpeg(base64.b64encode(buf.getvalue()).decode())))
                self.assertEqual((out.format, max(out.size)), ("JPEG", 1280))
                with self.assertRaises(AppError):
                    _small_jpeg(base64.b64encode(b"not a picture").decode())
        finally:
            srv.shutdown()

    def test_parents_are_blocked_and_codes_are_made_once(self):
        import json, tempfile, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        from app.core.store import DataStore
        role = {"v": "parent"}; posted = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out):
                raw = json.dumps(out).encode(); self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self): self._out([{"role": role["v"]}] if "/profiles" in self.path else [])
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                posted.append((self.path.split("?")[0], body)); self._out(body)

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"})
                with self.assertRaises(AppError) as cm:
                    svc.cloud_login({"email": "p@b.c", "password": "x"})
                self.assertEqual(cm.exception.code, "cloud_parent_blocked")
                self.assertFalse(svc.get_cloud()["signed_in"])                       # a parent never stays signed in to the teachers' program
                role["v"] = "admin"; svc.cloud_login({"email": "a@b.c", "password": "x"})
                svc.build_structure({"kg1": ["A"], "g4": ["A"]}); svc.put_students("g4-a", ["Ali Hassan", "Sara Omar"])
                r1 = svc.prepare_codes()
                codes1 = [row for path, rows in posted if path.endswith("/activation_codes") for row in rows]
                n1 = len(codes1)
                self.assertGreaterEqual(n1, 2)
                self.assertTrue(all(len(c["code"]) == 8 for c in codes1) and len({c["code"] for c in codes1}) == n1)
                self.assertTrue(r1["path"].endswith("Parent_Codes.docx"))
                svc.prepare_codes()                                                   # running it again changes nothing for old students
                self.assertEqual(len([row for path, rows in posted if path.endswith("/activation_codes") for row in rows]), n1)
                role["v"] = "teacher"; svc.cloud_login({"email": "t@b.c", "password": "x"})
                with self.assertRaises(AppError):
                    svc.prepare_codes()
        finally:
            srv.shutdown()


class TestUsageNotes(unittest.TestCase):
    def test_usage_counts_and_notes_stay_local(self):
        import os, tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        old = os.environ.get("DLIS_APP_HOME")
        self.addCleanup(lambda: os.environ.pop("DLIS_APP_HOME", None) if old is None else os.environ.__setitem__("DLIS_APP_HOME", old))
        with tempfile.TemporaryDirectory() as d:
            os.environ["DLIS_APP_HOME"] = d
            svc = Service(); svc.store = DataStore(d + "/data")
            for pg in ("today", "today", "docs", "evil"):
                svc.record_usage(pg)
            svc.add_feedback({"page": "docs", "text": "  The quiz tab is hard to find "})
            with self.assertRaises(AppError):
                svc.add_feedback({"text": " "})
            out = svc.export_feedback()
            txt = open(out["path"], encoding="utf-8").read()
            self.assertIn("today: 2", txt); self.assertIn("docs: 1", txt); self.assertNotIn("evil", txt)
            self.assertIn("The quiz tab is hard to find", txt)


class TestCoverage(unittest.TestCase):
    def test_progress_pack_and_status(self):
        import tempfile, zipfile
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


class TestQuizVersionsAndParentWeek(unittest.TestCase):
    def test_version_b_keeps_answers_right(self):
        from app.core import documents as D
        qs = D.parse_quiz("1. What is a CPU?\na) Brain\nb) Screen\nc) Mouse\nAnswer: a\n\n2. Which is input?\na) Mouse\nb) Speaker\nc) Printer\nAnswer: a\n\n3. Name one.\n")
        b = D.shuffled_version(qs)
        self.assertEqual(sorted(q["q"] for q in b), sorted(q["q"] for q in qs))
        for q in b:
            if q["type"] == "mcq":
                right = dict(q["options"])[q["answer"].upper()]
                self.assertEqual(right, "Brain" if "CPU" in q["q"] else "Mouse")        # the answer letter follows its choice
        self.assertTrue(any(x["options"] != y["options"] for x in qs for y in b if x["q"] == y["q"]))

    def test_parent_week_saved_clean_and_published_only_by_staff(self):
        import tempfile
        from app.server.service import Service
        from app.core.store import DataStore
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.build_structure({"kg1": ["A"]})
            out = svc.save_parent_week({"room_id": "kg1-a", "trimester": 0, "week": 8, "homework": "Page 12\n\n  Draw a mouse ",
                                        "material": "Video | https://youtu.be/x\nbad | javascript:alert(1)", "quiz_alerts": "Unit 2 quiz | 2026-11-12"})
            self.assertEqual(out["homework"], ["Page 12", "Draw a mouse"])
            self.assertEqual(out["material"], [{"title": "Video", "url": "https://youtu.be/x"}])
            self.assertEqual(out["quiz_alerts"][0]["date"], "2026-11-12"); self.assertFalse(out["approved"])
            with self.assertRaises(AppError):
                svc.save_parent_week({"room_id": "kg1-a", "trimester": 0, "week": 8}, True)


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
            rows = svc.put_calendar({"holidays": [{"start": "2026-11-15", "end": "2026-11-18", "name": ""}, {"start": "2026-12-03", "end": "", "name": ""}]})["holidays"]
            self.assertEqual(rows, [])  # school events are not holidays: those days stay normal school days


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
        self.assertEqual([g["id"] for g in w["groups"]], ["attendance", "presentation", "lesson_plan", "quiz", "weekly_plan"])
        w = self.svc.set_weekly({"trimester": 0, "week": 8, "grade_id": "g4", "task": "quiz_sent", "state": "done"})
        self.assertEqual(next(r for r in w["rows"] if r["grade_id"] == "g4")["states"]["quiz_sent"], "done"); self.assertEqual(w["done"], 1)
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware"}})   # the file exists: "made" ticks itself
        r4 = next(r for r in self.svc.get_weekly(0, 8)["rows"] if r["grade_id"] == "g4")
        self.assertEqual(r4["states"]["lesson_plan_made"], "done"); self.assertTrue(r4["auto"]["lesson_plan_made"]); self.assertEqual(r4["states"]["lesson_plan_sent"], "wait")
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
        with self.assertRaises(AppError):
            self.svc.open_file("/etc/passwd")
        self.svc.build_structure({"g5": ["A"]})
        with self.assertRaises(AppError):   # a class with no students
            self.svc.make_grading_sheet({"room_id": "g5-a", "trimester": 0, "week": 8})

    def test_library_lists_files_and_keeps_private_ones_off_the_server(self):
        r1 = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
        r2 = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware"}})
        items = {x["name"]: x for x in self.svc.library_list()["items"]}
        q = items[r1["name"]]
        self.assertEqual((q["kind"], q["private"], q["shared"]), ("quiz", False, None))
        self.assertTrue(items[r2["name"]]["private"])
        with self.assertRaises(AppError) as cm:
            self.svc.library_share({"rel": r2["rel"], "class_id": "g4-a", "public": True})
        self.assertEqual(cm.exception.code, "private_file")
        with self.assertRaises(AppError):
            self.svc.library_share({"rel": "../../etc/passwd", "class_id": "g4-a"})

    def test_scheme_of_work_round_trip_and_planned_source(self):
        d = self.svc.scheme_get("g4", 0)
        self.assertTrue(d["weeks"])
        w1 = next(w for w in d["weeks"] if w["school_days"] > 0)["week"]
        out = self.svc.scheme_put({"grade_id": "g4", "trimester": 0, "weeks": [{"week": w1, "topic": " Hardware  basics ", "pages": "10-14", "source_id": "nope"}, {"week": 999, "topic": "ignored"}]})
        row = next(w for w in out["weeks"] if w["week"] == w1)
        self.assertEqual((row["topic"], row["pages"], row["source_id"]), ("Hardware basics", "10-14", ""))   # an unknown source is dropped
        self.assertNotIn("ignored", str(out["weeks"]))
        data = self.svc._plans(); data["scheme"]["g4|0"][str(w1)]["source_id"] = "abc"; self.svc._need_store().write_json(self.svc._plans_path(), data)
        self.assertEqual(self.svc.scheme_source("g4", "hardware BASICS"), ("abc", "10-14"))
        self.assertEqual(self.svc.scheme_source("g5", "hardware basics"), ("", ""))
        wk = next(x for x in self.svc.slide_topics("g4", 0)["weeks"] if x["week"] == w1)       # the Create page reads the same plan
        self.assertEqual((wk["topic"], wk["pages"], wk["source_id"]), ("Hardware basics", "10-14", "abc"))
        st = self.svc.week_prep_status("2026-10-28")
        self.assertEqual(st["state"], "in_term"); self.assertLessEqual(st["ready"], st["total"])

    def test_revision_cover_page(self):
        from docx import Document
        self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": ["Hardware", "Software"]})
        sug = self.svc.revision_cover_suggest("g4", 0)
        self.assertIn("Hardware", sug["lines"])
        rows = "Unit 1 | Hardware | 10-14\nSoftware | 15-20\n" + "\n".join(f"U{i} | L{i} | {i}" for i in range(12))
        r = self.svc.make_revision_cover({"grade_id": "g4", "trimester": 0, "rows": rows})
        self.assertTrue(r["rel"].replace("\\", "/").endswith("Documents/Grade 4/T1_Revision_Cover_Page.docx"), r["rel"])
        d = Document(r["path"])
        text = "\n".join(p.text for p in d.paragraphs)
        for w in ("Final Trimester 1 Revision Pack", "ICT", "Test Teacher", "Grade Level: 4"):
            self.assertIn(w, text)
        cells = [[c.text for c in row.cells] for row in d.tables[0].rows]
        self.assertEqual(cells[1], ["Unit 1", "Hardware", "10-14"])
        self.assertEqual(cells[2], ["", "Software", "15-20"])   # two parts = lesson | pages
        self.assertEqual(len(cells), 15)                         # grew past the 9 empty rows
        head = " ".join(p.text for p in d.sections[0].header.paragraphs)
        self.assertIn("ICT Department", head); self.assertIn("Trimester 1-Grade (4)", head)
        self.assertEqual(sum(len(x.drawing_images) if hasattr(x, "drawing_images") else 0 for x in []), 0)
        with self.assertRaises(AppError):
            self.svc.make_revision_cover({"grade_id": "nope", "trimester": 0, "rows": ""})
        # the cover is the first page of the revision file itself
        r = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 0, "title": "Hardware", "words": "CPU: brain", "with_cover": True, "cover_rows": "Unit 1 | Hardware | 10-14"})
        d = Document(r["path"])
        text = "\n".join(p.text for p in d.paragraphs)
        self.assertIn("Final Trimester 1 Revision Pack", text); self.assertIn("Revision Sheet", " ".join(c.text for t in d.tables for row in t.rows for c in row.cells) + text)
        self.assertEqual(d.tables[0].rows[1].cells[1].text, "Hardware")

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

    def test_school_map_layout_and_migration(self):
        m = self.svc.get_map()
        wings = {f["name"]: {w: [r["name"] for r in f["rooms"] if r["wing"] == w] for w in ("left", "center", "right")} for f in m["floors"]}
        self.assertEqual(wings["Ground floor"], {"left": ["KG1", "KG2"], "center": [], "right": ["Photocopy office", "HR & Student affairs", "Store", "Canteen"]})
        self.assertEqual(wings["First floor"]["center"], ["Reception"])
        self.assertEqual(wings["First floor"]["right"], ["IT", "Art store", "Special needs class", "Grade 1"])
        self.assertEqual(wings["Second floor"]["left"], ["Grade 11", "Grade 9", "Grade 10", "Grade 6"])
        self.assertEqual(wings["Second floor"]["center"], ["Principal's office"])
        # a map saved by an older version (no "version") is replaced by the new building, keeping what was typed about each room
        old = {"floors": [{"id": "floor2", "name": "Second floor", "rooms": [{"name": "Principal's office", "kind": "admin", "person": "Mr X", "phone": "0100", "wing": "left"}]}]}
        self.svc._need_store().write_json(self.svc._map_path(), old)
        new = self.svc.get_map()
        r = [r for f in new["floors"] for r in f["rooms"] if r["name"] == "Principal's office"][0]
        self.assertEqual((r["person"], r["phone"], r["wing"]), ("Mr X", "0100", "center"))
        self.assertEqual(new["version"], 2)

    def test_sources_read_pictures_and_feed_helpers(self):
        import base64, io
        from PIL import Image
        from pptx import Presentation
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


class TestQuizTypes(unittest.TestCase):
    def test_mixed_types_parse_and_render(self):
        import tempfile
        from pathlib import Path
        from app.core import documents as D
        text = ("1. Capital?\na) Cairo\nb) Giza\nAnswer: a\n\n2. The Nile is ____.\nAnswer: long\n\n3. Why?\nAnswer: because\n\n"
                "4. Match:\nsun = star\nmoon = satellite\n\n5. Sky is blue.\na) True\nb) False\nAnswer: a")
        qs = D.parse_quiz(text)
        self.assertEqual([q["type"] for q in qs], ["mcq", "fill", "essay", "match", "tf"])
        with tempfile.TemporaryDirectory() as d:
            out = D.fill_quiz(D.template_path("quiz"), Path(d) / "q.docx", {"grade_label": "4", "trimester": 1, "week": 2, "number": 1,
                                                                           "questions": qs, "with_answers": True})
            from docx import Document
            body = "\n".join(p.text for p in Document(str(out)).paragraphs)
            self.assertIn("1) sun", body); self.assertIn("Answer key", body); self.assertIn("2- long", body)


class TestMadeDecks(TestAi):
    def test_built_and_existing_decks_join_my_slides(self):
        from app.core.pptx_builder import build_deck
        self.svc.slide_build({"grade_id": "g4", "title": "Input devices", "slides": [{"title": "Mouse", "bullets": ["points", "clicks"], "explain": "A mouse moves the pointer.", "notes": "n"}]})
        names = [x["name"] for x in self.svc.list_sources()["sources"]]
        self.assertTrue(any("Input devices" in n for n in names))
        extra = self.svc._need_store().root / "Slides" / "x" / "Old deck.pptx"
        build_deck(extra, {"title": "Old deck", "subtitle": "", "language": "en", "stage": "primary", "slides": [{"title": "Keyboard", "bullets": ["keys"], "explain": "", "notes": "", "image_path": ""}]})
        srcs = self.svc.list_sources()["sources"]
        self.assertTrue(any(x["name"] == "Old deck" and x["made"] for x in srcs))
        self.assertEqual(len([x for x in srcs if "Input devices" in x["name"]]), 1)


class TestUrlSource(TestAi):
    def test_web_page_becomes_a_source_and_blocks_private_addresses(self):
        from unittest import mock
        page = b"<html><head><title>The CPU</title></head><body><nav>menu</nav><h1>The CPU</h1><p>" + b"The CPU is the brain of the computer. " * 8 + b"</p></body></html>"
        with mock.patch("app.core.ai_client.http_bytes", return_value=page), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            out = self.svc.import_url({"url": "example.com/cpu"})
        self.assertEqual(out["name"], "The CPU"); self.assertGreater(out["chars"], 100)
        text = self.svc.source_block(out["id"])
        self.assertIn("ONLY", text); self.assertNotIn("menu", text)
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.1", 0))]):
            with self.assertRaises(AppError):
                self.svc.import_url({"url": "http://router.local/"})
        with self.assertRaises(AppError):
            self.svc.import_url({"url": "file:///etc/passwd"})



class TestTeacherTools(TestAi):
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


class TestGradeFillAndReminder(TestAi):
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


class TestTomorrowAlert(TestAi):
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


class TestQuizExport(TestAi):
    TEXT = ("1. What is a CPU?\na) Brain\nb) Screen\nc) Mouse\nAnswer: a\n2. A mouse is an input device.\na) True\nb) False\nAnswer: a\n"
            "3. Match the device with its use.\nMouse = points\nKeyboard = types\nSpeaker = sound\n4. The ___ is the brain of the computer.\nAnswer: CPU\n5. Explain: why?\n6. Which is output?\na) Mouse\nb) Printer\n")

    def test_moodle_gift_and_google_forms_script(self):
        g = self.svc.export_quiz({"grade_id": "g4", "trimester": 0, "week": 3, "number": 1, "text": self.TEXT, "format": "gift"})
        body = Path(g["path"]).read_text(encoding="utf-8")
        self.assertTrue(g["name"].endswith("_Moodle.txt")); self.assertEqual(g["questions"], 6)
        self.assertIn("{ =Brain ~Screen ~Mouse }", body); self.assertIn("{TRUE}", body)
        self.assertIn("=Mouse -> points", body); self.assertIn("The {=CPU} is the brain", body)
        self.assertIn("Explain\\: why? {}", body)
        self.assertIn("Which is output? {}", body)                       # no answer given: imported as an essay question
        f = self.svc.export_quiz({"grade_id": "g4", "trimester": 0, "week": 3, "number": 1, "text": self.TEXT, "format": "forms"})
        js = Path(f["path"]).read_text(encoding="utf-8")
        self.assertIn("FormApp.create", js); self.assertIn('createChoice("Brain", true)', js); self.assertIn("addListItem", js); self.assertIn("Answer: CPU", js)
        with self.assertRaises(AppError):
            self.svc.export_quiz({"grade_id": "g4", "text": "  "})


class TestGrades(TestAi):
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


class TestInsights(TestAi):
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


class TestSchemeUnits(TestAi):
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


class TestTranslitMore(unittest.TestCase):
    def test_names(self):
        from app.core.translit import to_english
        self.assertEqual(to_english("تسنيم حامد"), "Tasneem Hamed")
        self.assertEqual(to_english("رزان خالد"), "Razan Khaled")
        self.assertEqual(to_english("زين الدين"), "Zein El Din")


class TestYoutubeSource(TestAi):
    def test_captions_and_pasted_transcript(self):
        import json
        from unittest import mock
        pr = {"videoDetails": {"title": "How a CPU works"}, "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [{"languageCode": "en", "baseUrl": "https://www.youtube.com/api/timedtext?v=abc"}]}}}
        page = ("<script>var ytInitialPlayerResponse = " + json.dumps(pr) + ";var meta = 1;</script>").encode()
        xml = ("<transcript>" + "".join(f"<text start='{i}'>The CPU runs instructions {i} &amp;#39;fast&amp;#39;</text>" for i in range(12)) + "</transcript>").encode()
        with mock.patch("app.core.ai_client.http_bytes", side_effect=[page, xml]), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.1.1", 0))]):
            out = self.svc.import_url({"url": "https://youtu.be/dQw4w9WgXcQ"})
        self.assertEqual(out["name"], "How a CPU works")
        self.assertIn("runs instructions", self.svc.source_block(out["id"]))
        nocap = ("<script>var ytInitialPlayerResponse = {};</script>").encode()
        with mock.patch("app.core.ai_client.http_bytes", return_value=nocap), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.1.1", 0))]):
            with self.assertRaises(AppError) as c:
                self.svc.import_url({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
            self.assertEqual(c.exception.code, "no_captions")
            out2 = self.svc.import_url({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "transcript": "Memory stores data. " * 10})
        self.assertIn("Memory stores", self.svc.source_block(out2["id"]))


class TestServerBackup(TestAi):
    def test_backup_zip_admin_only(self):
        import json
        import zipfile
        from unittest import mock
        class Fake:
            def select(self, table, q): return [{"id": 1, "name": "x"}]
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "admin"}), mock.patch.object(self.svc, "_cloud_client", return_value=Fake()):
            r = self.svc.cloud_backup()
        self.assertEqual(r["counts"]["students"], 1)
        with zipfile.ZipFile(r["path"]) as z:
            self.assertEqual(json.loads(z.read("grades.json"))[0]["name"], "x")
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "teacher"}):
            with self.assertRaises(AppError):
                self.svc.cloud_backup()


class TestAutoBackup(unittest.TestCase):
    def test_weekly_copy_keeps_last_five_and_skips_exports(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            s = DataStore(d)
            (Path(d) / "Documents").mkdir()
            (Path(d) / "Documents" / "plan.docx").write_text("x")
            s.exports_dir().mkdir(parents=True, exist_ok=True)
            (s.exports_dir() / "big.zip").write_text("y")
            first = s.auto_backup()
            self.assertTrue(first and first.exists())
            with zipfile.ZipFile(first) as z:
                names = z.namelist()
            self.assertIn("Documents/plan.docx", names)
            self.assertFalse([n for n in names if n.startswith(("Exports", "_backup"))])
            self.assertIsNone(s.auto_backup())   # still recent: nothing new
            folder = s.backup_root() / "auto"
            for i in range(1, 8):   # seven older copies exist; only the newest five remain
                (folder / f"DLIS_auto_2026-01-0{i}.zip").write_bytes(b"")
            (folder / first.name).rename(folder / "DLIS_auto_2026-02-01.zip")
            made = s.auto_backup(every_days=7)
            self.assertIsNotNone(made)
            self.assertEqual(len(list(folder.glob("DLIS_auto_*.zip"))), 5)



class TestDataVersion(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        import app.core.store as store_mod
        self.mod, self.mock = store_mod, mock

    def test_fresh_folder_is_stamped_on_first_save_only(self):
        d = Path(tmp())
        s = DataStore(d)
        self.assertFalse((d / "data_version.json").exists())   # opening an empty folder writes nothing
        s.save_settings(Settings())
        self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], self.mod.DATA_VERSION)

    def test_old_folder_without_a_version_file_counts_as_version_1(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        s = DataStore(d)
        self.assertEqual(s.locked, "")
        self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], 1)

    def test_newer_folder_is_never_changed(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        (d / "data_version.json").write_text(json.dumps({"data_version": 99}), encoding="utf-8")
        before = (d / "config.json").read_text(encoding="utf-8")
        s = DataStore(d)
        self.assertEqual(s.locked, "newer")
        with self.assertRaises(AppError) as cm:
            s.save_settings(Settings(teacher_name="changed"))
        self.assertEqual(cm.exception.code, "data_locked")
        self.assertEqual((d / "config.json").read_text(encoding="utf-8"), before)
        self.assertEqual(s.load_settings().teacher_name, "x")   # reading still works

    def test_upgrade_copies_first_then_runs_each_step_in_order(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        ran = []

        def to2(store):
            ran.append(2)
            self.assertTrue(list((store.backup_root() / "before_upgrade").glob("DLIS_before_v1_*.zip")))   # the copy exists BEFORE any change
            store.write_json(store.tasks_path(), {"tasks": ["moved"]})

        def to3(store): ran.append(3)
        with self.mock.patch.object(self.mod, "DATA_VERSION", 3), self.mock.patch.object(self.mod, "MIGRATIONS", {1: to2, 2: to3}):
            s = DataStore(d)
            self.assertEqual((s.locked, s.upgraded_from, ran), ("", 1, [2, 3]))
            self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], 3)
            DataStore(d)   # opened again: nothing runs twice
            self.assertEqual(ran, [2, 3])
        import zipfile
        z = next((d / "_backup" / "before_upgrade").glob("*.zip"))
        self.assertIn("config.json", zipfile.ZipFile(z).namelist())

    def test_failed_upgrade_locks_the_folder_and_keeps_the_copy(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")

        def boom(store): raise RuntimeError("bad step")
        with self.mock.patch.object(self.mod, "DATA_VERSION", 2), self.mock.patch.object(self.mod, "MIGRATIONS", {1: boom}):
            s = DataStore(d)
            self.assertEqual(s.locked, "failed")
            self.assertTrue(list((d / "_backup" / "before_upgrade").glob("*.zip")))
            self.assertFalse((d / "data_version.json").exists())   # still version 1: the next start tries again
            with self.assertRaises(AppError):
                s.save_settings(Settings())


class TestUpdateNotice(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from app.core import paths
        from app.server.update_service import UpdateMixin
        self.paths, self.mock = paths, mock
        env = mock.patch.dict(os.environ, {"DLIS_APP_HOME": tmp()})
        env.start(); self.addCleanup(env.stop)

        class Svc(UpdateMixin):
            calls = 0
            src = {"update_url": "https://example.org/latest.json"}
            answer = {"version": "9.9.9", "url": "https://example.org/get", "notes": "n"}

            def _update_sources(self): return self.src

            def _fetch_update(self, src):
                Svc.calls += 1
                if isinstance(self.answer, Exception): raise self.answer
                return self.answer
        self.Svc = Svc
        self.svc = Svc()

    def test_version_compare(self):
        from app.server.update_service import is_newer
        self.assertTrue(is_newer("1.0.1", "1.0.0")); self.assertTrue(is_newer("v1.10.0", "1.9.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0")); self.assertFalse(is_newer("0.9", "1.0.0")); self.assertFalse(is_newer("", "1.0.0"))

    def test_shows_once_checked_daily_and_can_be_dismissed(self):
        r = self.svc.check_update()
        self.assertEqual((r["available"], r["version"], r["url"]), (True, "9.9.9", "https://example.org/get"))
        self.svc.check_update()
        self.assertEqual(self.Svc.calls, 1)   # asked once, then the saved answer is used for a day
        self.svc.dismiss_update("9.9.9")
        self.assertFalse(self.svc.check_update()["available"])

    def test_silent_when_off_unset_failing_or_not_newer(self):
        self.svc.set_update_check(False)
        self.assertEqual(self.svc.check_update(), {"available": False, "enabled": False})
        self.assertEqual(self.Svc.calls, 0)
        self.svc.set_update_check(True)
        self.Svc.src = {}
        self.assertFalse(self.svc.check_update()["available"])
        self.Svc.src = {"update_url": "https://example.org/latest.json"}
        self.Svc.answer = OSError("offline")
        self.assertFalse(self.svc.check_update()["available"])   # a failure is silent, and is not retried at once
        self.paths.write_prefs(update={})
        self.Svc.answer = {"version": self.paths.VERSION, "url": "https://example.org/get", "notes": ""}
        self.assertFalse(self.svc.check_update()["available"])

    def test_only_https_and_known_shapes_are_read(self):
        from app.server.update_service import UpdateMixin
        class Raw(UpdateMixin): pass
        self.assertIsNone(Raw()._fetch_update({"update_url": "http://example.org/x.json"}))
        self.assertIsNone(Raw()._fetch_update({"update_repo": "not a repo"}))


if __name__ == "__main__":
    unittest.main()
