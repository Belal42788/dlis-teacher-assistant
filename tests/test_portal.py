"""The family portal in a real browser against a fake school server (scripts/portal_check.py): a parent, a student, a phone, and a teacher turned away."""
import subprocess
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401  (the tests never reach the real internet)

ROOT = Path(__file__).resolve().parents[1]
try:
    import playwright  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


class TestPortal(unittest.TestCase):
    @unittest.skipUnless(HAVE, "playwright is not installed")
    def test_portal_in_a_browser(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/portal_check.py")], cwd=ROOT, capture_output=True, text=True, timeout=280)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-2500:])
        self.assertIn("portal ok", out.stdout)

    def test_portal_files_are_all_there(self):
        for rel in ("index.html", "portal.css", "config.js", "js/main.js", "js/core.js", "js/data.js", "js/study.js", "js/talk.js", "js/i18n.js", "js/calendar.js", "js/fresh.js", "calendar.json",
                    "img/logo-mark.png", "img/logo.png", "fonts/Cairo-Regular.ttf", "fonts/Cairo-Bold.ttf"):
            self.assertTrue((ROOT / "portal" / rel).is_file(), rel)

    def test_every_portal_text_exists_in_both_languages(self):
        import re
        js = "".join((ROOT / "portal/js" / f).read_text(encoding="utf-8") for f in ("main.js", "study.js", "talk.js", "calendar.js"))
        text = (ROOT / "portal/js/i18n.js").read_text(encoding="utf-8")
        ar, en = text.split("const en = {")
        keys = lambda block: set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*):", block))
        used = set(re.findall(r"\bt\(\"([A-Za-z_][A-Za-z0-9_]*)\"\)", js))
        self.assertFalse(used - keys(ar), f"missing in Arabic: {used - keys(ar)}")
        self.assertFalse(used - keys(en), f"missing in English: {used - keys(en)}")
        self.assertFalse(keys(ar) ^ keys(en), f"Arabic and English differ: {keys(ar) ^ keys(en)}")

    def test_the_portal_calendar_matches_the_school_calendar(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/make_portal_calendar.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_the_portal_calendar_knows_which_grades_an_event_is_for(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from make_portal_calendar import build, grades_of
        self.assertEqual(grades_of("Book Week Middle School (G6 – G8)"), ["g6", "g7", "g8"])
        self.assertEqual(grades_of("Character Day Event (KG1 – G5)")[:2], ["kg1", "kg2"])
        self.assertIsNone(grades_of("Sports Day For All School"))
        cal = build()
        self.assertFalse([e for e in cal["events"] if "staff" in e["en"].lower()], "staff-only days must not reach the parents")
        self.assertTrue(all(h["ar"] for h in cal["holidays"]))


if __name__ == "__main__":
    unittest.main()


class TestMessagesPage(unittest.TestCase):
    @unittest.skipUnless(HAVE, "playwright is not installed")
    def test_messages_page_in_a_browser(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/messages_check.py")], cwd=ROOT, capture_output=True, text=True, timeout=280)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-2500:])
        self.assertIn("messages ok", out.stdout)


class TestYearEndPage(unittest.TestCase):
    @unittest.skipUnless(HAVE, "playwright is not installed")
    def test_year_end_in_a_browser(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/yearend_check.py")], cwd=ROOT, capture_output=True, text=True, timeout=280)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-2500:])
        self.assertIn("yearend ok", out.stdout)


class TestSchoolImportPage(unittest.TestCase):
    @unittest.skipUnless(HAVE, "playwright is not installed")
    def test_school_import_in_a_browser(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/school_import_check.py")], cwd=ROOT, capture_output=True, text=True, timeout=280)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-2500:])
        self.assertIn("school import ok", out.stdout)
