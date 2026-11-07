import base64
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()

from app.server.http import AppServer

LEGACY = Path(os.environ.get("DLIS_LEGACY_SAMPLE", "/home/claude/proj/DLIS_Data"))


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = AppServer()
        cls.server.start_in_thread()
        cls.base = f"http://127.0.0.1:{cls.server.port_number}"
        cls.data = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def call(self, method, path, body=None, token=True, host=None, expect=200):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-DLIS-Token"] = self.server.token
        if host:
            headers["Host"] = host
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        self.assertEqual(status, expect, raw[:300])
        return json.loads(raw) if raw else None

    # ---- security
    def test_01_security(self):
        self.call("GET", "/api/bootstrap", token=False, expect=403)
        self.call("GET", "/api/bootstrap", host="evil.example.com", expect=403)
        page = urllib.request.urlopen(self.base + "/").read().decode()
        self.assertIn(self.server.token, page)
        self.assertNotIn("__TOKEN__", page)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/../core/store.py")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/%2e%2e/core/store.py")

    # ---- first run flow
    def test_02_flow(self):
        b = self.call("GET", "/api/bootstrap")
        self.assertEqual(b["data_folder"], "")
        self.call("GET", "/api/structure", expect=409)
        self.call("PUT", "/api/prefs", {"language": "ar"})
        self.call("PUT", "/api/prefs", {"language": "xx"}, expect=400)
        b = self.call("POST", "/api/data-folder", {"path": self.data})
        self.assertEqual(b["language"], "ar")
        self.assertFalse(b["setup_done"])

        self.call("PUT", "/api/settings", {"teacher_name": "Bilal", "subject": "ICT"})
        bad = self.call("PUT", "/api/settings", {"working_days": ["Noday"]}, expect=400)
        self.assertEqual(bad["error"], "invalid_data")

        s = self.call("POST", "/api/structure/build", {"selection": {"g4": ["A", "B"], "kg1": ["A"]}})
        self.assertEqual(len(s["rooms"]), 3)
        self.assertIn("presets", s)
        self.call("POST", "/api/structure/build", {"selection": {"g99": ["A"]}}, expect=400)

        r = self.call("POST", "/api/students/parse", {"text": "1. Sara\n2. Omar\n3. sara"})
        self.assertEqual(r["names"], ["Sara", "Omar"])
        f = self.call("POST", "/api/students/parse",
                      {"filename": "list.csv", "data_b64": base64.b64encode("Name\nلمى\nيوسف".encode()).decode()})
        self.assertEqual(f["names"], ["لمى", "يوسف"])
        self.call("PUT", "/api/rooms/g4-a/students", {"names": r["names"]})
        self.assertEqual(self.call("GET", "/api/rooms/g4-a/students")["names"], ["سارة", "عمر"])
        self._certificates()
        self._behavior_and_seating()
        self.call("GET", "/api/rooms/nope/students", expect=404)
        self.call("GET", "/api/rooms/..%2F..%2Fx/students", expect=404)
        self.assertEqual([x for x in self.call("GET", "/api/structure")["rooms"] if x["id"] == "g4-a"][0]["student_count"], 2)

        tt = {"periods": [{"name": "99", "start": "01:00", "end": "01:05"}],  # the client cannot change periods
              "grid": {"Sunday": {"1": "g4-a", "2": "ghost"}}, "overrides": {}, "duties": {"Monday": ["break"], "Wednesday": ["break", "late", "bogus"]}}
        saved = self.call("PUT", "/api/timetable", tt)
        self.assertEqual(saved["grid"]["Sunday"], {"1": "g4-a", "2": ""})
        self.assertEqual([p["name"] for p in saved["periods"]], [str(i) for i in range(1, 9)])
        self.assertEqual(saved["periods"][0]["start"], "08:15")
        self.assertEqual(saved["duties"]["Wednesday"], ["break", "late"])
        self.assertIn("bell", saved)

        cal = {"academic_year": "2026-2027",
               "trimesters": [{"name": "T1", "start": "2026-09-01", "end": "2026-11-30", "week1_start": ""}],
               "holidays": [{"start": "2026-10-06", "end": "", "name": "Holiday"}], "events": []}
        self.call("PUT", "/api/calendar", cal)
        cal["trimesters"][0]["end"] = "2026-08-01"
        self.assertEqual(self.call("PUT", "/api/calendar", cal, expect=400)["error"], "trimester_dates")
        cal["trimesters"][0]["end"] = "2026-11-30"; cal["holidays"][0]["start"] = "6/10/2026"
        self.assertEqual(self.call("PUT", "/api/calendar", cal, expect=400)["error"], "invalid_data")

        t = self.call("GET", "/api/today?date=2026-10-11")  # Sunday, week 7
        self.assertEqual(t["position"]["week"], 7)
        self.assertEqual([s["room_id"] for s in t["sessions"]], ["g4-a"])
        h = self.call("GET", "/api/today?date=2026-10-06")
        self.assertEqual(h["holiday"]["name"], "Holiday")
        self.assertEqual(h["sessions"], [])
        self.assertEqual(self.call("GET", "/api/today?date=2026-10-09")["weekend"], True)
        self.call("GET", "/api/today?date=nonsense", expect=400)
        ov = self.call("GET", "/api/overview")
        self.assertEqual(ov["trimesters"][0]["weeks"][0]["start"], "2026-08-30")

        self.call("POST", "/api/setup/finish")
        self.assertTrue(self.call("GET", "/api/bootstrap")["setup_done"])
        z = self.call("POST", "/api/backup")
        self.assertTrue((Path(self.data) / "Exports" / z["name"]).exists())

        # removing a class cleans the timetable
        st = self.call("GET", "/api/structure")
        st["rooms"] = [r for r in st["rooms"] if r["id"] != "g4-a"]
        self.call("PUT", "/api/structure", st)
        self.assertEqual(self.call("GET", "/api/timetable")["grid"]["Sunday"]["1"], "")
        st["rooms"].append({"id": "x1", "grade_id": "none", "name": "x"})
        self.assertEqual(self.call("PUT", "/api/structure", st, expect=400)["error"], "missing_grade")

    @unittest.skipUnless(LEGACY.exists(), "no legacy sample")
    # ---- certificates (runs inside the flow, while the first class has its students)
    def _certificates(self):
        from docx import Document
        def texts(r): return "\n".join(p.text for p in Document(r["path"]).paragraphs) + "\n".join(c.text for t in Document(r["path"]).tables for row in t.rows for c in row.cells)
        r = self.call("POST", "/api/docs/certificates", {"room_id": "g4-a", "occasion": "excellence", "lang": "ar"})
        self.assertEqual(r["count"], 2)
        self.assertTrue(Path(r["path"]).is_file())
        self.assertIn("شهادة تفوّق", texts(r)); self.assertIn("سارة", texts(r))
        import zipfile
        z = zipfile.ZipFile(r["path"])   # the app's own font (Cairo) travels inside the file
        self.assertTrue({"word/fonts/font1.odttf", "word/fonts/font2.odttf"} <= set(z.namelist()))
        self.assertIn(b"embedTrueTypeFonts", z.read("word/settings.xml"))
        self.assertIn(b'w:name="Cairo"', z.read("word/fontTable.xml"))
        r = self.call("POST", "/api/docs/certificates", {"room_id": "g4-a", "students": ["عمر"], "extra_names": "Guest One\nGuest Two", "occasion": "thanks", "kind": "card", "lang": "en"})
        self.assertEqual(r["count"], 3)
        self.assertIn("Guest Two", texts(r)); self.assertIn("Thank You", texts(r))
        r = self.call("POST", "/api/docs/certificates", {"room_id": "", "extra_names": "Only Me", "occasion": "custom", "title": "Best Reader", "text": "for reading 20 books"})
        self.assertEqual(r["count"], 1); self.assertIn("for reading 20 books", texts(r))
        self.call("POST", "/api/docs/certificates", {"room_id": "g4-a", "occasion": "custom"}, expect=400)
        self.call("POST", "/api/docs/certificates", {"room_id": "", "occasion": "excellence"}, expect=409)
        self.call("POST", "/api/docs/certificates", {"room_id": "g4-a", "occasion": "nope"}, expect=400)

    # ---- behaviour notes and seating (inside the flow too)
    def _behavior_and_seating(self):
        r = self.call("POST", "/api/behavior", {"room_id": "g4-a", "student": "سارة", "kind": "good", "note": "Helped a classmate"})
        n1 = r["note"]["id"]
        n2 = self.call("POST", "/api/behavior", {"room_id": "g4-a", "student": "عمر", "kind": "concern", "note": "Late three times"})["note"]["id"]
        self.call("POST", "/api/behavior", {"room_id": "g4-a", "student": "nobody", "note": "x"}, expect=404)
        self.call("POST", "/api/behavior", {"room_id": "g4-a", "student": "سارة", "note": "  "}, expect=400)
        self.call("POST", "/api/behavior", {"room_id": "g4-a", "student": "سارة", "kind": "bad", "note": "x"}, expect=400)
        d = self.call("GET", "/api/behavior?room=g4-a")
        self.assertEqual(len(d["notes"]), 2)
        self.assertEqual(d["counts"]["عمر"], {"good": 0, "concern": 1, "open": 1})
        self.call("POST", f"/api/behavior/{n2}/done", {"done": True})
        self.assertEqual(self.call("GET", "/api/behavior?room=g4-a")["counts"]["عمر"]["open"], 0)
        self.call("POST", f"/api/behavior/{n1}/done", {"done": True})   # a good note is never "open"
        self.assertFalse(next(x for x in self.call("GET", "/api/behavior?room=g4-a")["notes"] if x["id"] == n1)["done"])
        self.call("POST", f"/api/behavior/{n1}/delete", {})
        self.assertEqual(len(self.call("GET", "/api/behavior?room=g4-a")["notes"]), 1)
        self.call("GET", "/api/behavior?room=nope", expect=404)

        c = self.call("GET", "/api/seating?room=g4-a")
        self.assertEqual((c["rows"], c["cols"], c["seats"], c["saved"]), (5, 6, {}, False))
        c = self.call("PUT", "/api/seating", {"room_id": "g4-a", "rows": 2, "cols": 3, "seats": {"0-0": "سارة", "1-2": "عمر", "9-9": "سارة"}})
        self.assertEqual(c["seats"], {"0-0": "سارة", "1-2": "عمر"})   # a seat outside the grid is dropped
        self.call("PUT", "/api/seating", {"room_id": "g4-a", "rows": 2, "cols": 3, "seats": {"0-0": "سارة", "0-1": "سارة"}}, expect=400)
        self.call("PUT", "/api/seating", {"room_id": "g4-a", "rows": 2, "cols": 3, "seats": {"0-0": "ghost"}}, expect=404)
        self.call("PUT", "/api/seating", {"room_id": "g4-a", "rows": 99, "cols": 3, "seats": {}}, expect=400)
        c = self.call("PUT", "/api/seating", {"room_id": "g4-a", "rows": 1, "cols": 2, "seats": {"0-0": "سارة", "1-2": "عمر"}})
        self.assertEqual(c["seats"], {"0-0": "سارة"})
        self.assertTrue(self.call("GET", "/api/seating?room=g4-a")["saved"])

    def test_03_legacy_and_folder_browser(self):
        self.call("POST", "/api/import/legacy", {"path": tempfile.mkdtemp()}, expect=400)
        rep = self.call("POST", "/api/import/legacy", {"path": str(LEGACY), "dry_run": True})
        self.assertGreater(rep["rooms"], 0)
        fs = self.call("GET", "/api/fs/list?path=" + str(Path(self.data).parent))
        self.assertTrue(fs["dirs"] and fs["path"])
        made = self.call("POST", "/api/fs/mkdir", {"parent": self.data, "name": "نسخة"})
        self.assertTrue(made["path"].endswith("نسخة"))
        self.call("POST", "/api/fs/mkdir", {"parent": self.data, "name": "a/b"}, expect=400)

    def test_04_unknown(self):
        self.call("GET", "/api/nothing", expect=404)
        self.call("POST", "/api/bootstrap", {}, expect=405)


if __name__ == "__main__":
    unittest.main()
