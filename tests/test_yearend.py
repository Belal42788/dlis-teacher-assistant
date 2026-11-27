"""End of the year: backup, archive, classes move up one grade, students leaving, the parents' codes follow the students."""
import json
import unittest
from pathlib import Path

import helpers
from app.core.errors import AppError


class TestYearEnd(helpers.AiCase):
    def setUp(self):
        super().setUp()
        self.svc.build_structure({"kg1": ["A"], "kg2": ["A"], "g4": ["A", "B"], "g5": ["A"], "g12": ["A"]})
        self.svc.put_students("kg1-a", ["كيجي واحد"])
        self.svc.put_students("kg2-a", [])
        self.svc.put_students("g4-a", ["سارة علي", "عمر سامي", "منتقل بعيد"], ["Sarah Aly", "", ""])
        self.svc.put_students("g4-b", ["ليلى أحمد"], ["Layla Ahmed"])
        self.svc.put_students("g5-a", ["يوسف حسن"])
        self.svc.put_students("g12-a", ["متخرج واحد"])
        self.root = Path(self.svc.store.root)
        (self.root / "grades.json").write_text(json.dumps({"g4-a|1|1": {"x": 1}}), encoding="utf-8")
        (self.root / "lesson_log.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
        (self.root / "cloud_students.json").write_text(json.dumps({
            "g4-a|سارة علي": {"student": "s1", "activation": "AAAA1111"},
            "g4-a|منتقل بعيد": {"student": "s2", "activation": "BBBB2222"},
            "g5-a|يوسف حسن": {"student": "s3", "activation": "CCCC3333"},
            "g12-a|متخرج واحد": {"student": "s4", "activation": "DDDD4444"}}), encoding="utf-8")

    def test_preview_says_what_will_happen(self):
        p = self.svc.yearend_preview()
        fate = {r["id"]: r["fate"] for r in p["rooms"]}
        self.assertEqual(fate["kg1-a"], "moves"); self.assertEqual(fate["g4-a"], "moves")
        self.assertEqual(fate["g5-a"], "elsewhere"); self.assertEqual(fate["g12-a"], "graduates")
        self.assertIn("grades.json", p["files"])

    def test_nothing_happens_without_the_confirmation(self):
        with self.assertRaises(AppError) as c:
            self.svc.yearend_run({})
        self.assertEqual(c.exception.code, "yearend_confirm")
        self.assertEqual(self.svc.get_students("g4-a")["names"][0], "سارة علي")

    def test_the_classes_move_up_and_the_records_are_archived(self):
        r = self.svc.yearend_run({"confirm": True, "leaving": {"g4-a": ["منتقل بعيد"]}})
        self.assertTrue(Path(r["backup"]).exists())
        self.assertEqual(self.svc.get_students("kg2-a")["names"], ["كيجي واحد"])
        self.assertEqual(self.svc.get_students("g5-a")["names"], ["سارة علي", "عمر سامي"])        # the old g4-a, without the one who left
        self.assertEqual(self.svc.get_students("g4-a")["names"], [])                               # nobody moves into Grade 4: waits for the newcomers
        self.assertEqual(self.svc.get_students("g4-b")["names"], [])
        self.assertEqual(self.svc.get_students("g12-a")["names"], [])                              # Grade 12 left the school
        self.assertIn("Grade 4 A", r["empty"])
        self.assertEqual((r["moved"], r["left"], r["graduated"], r["elsewhere"]), (3, 1, 1, 2))
        arch = Path(r["archive"])
        self.assertTrue((arch / "grades.json").exists())
        self.assertFalse((self.root / "grades.json").exists())                                     # the new year starts clean
        self.assertIn("متخرج واحد", (arch / "left_the_school.csv").read_text(encoding="utf-8-sig"))
        self.assertIn("سارة علي", (arch / "rooms" / "g4-a" / "students.csv").read_text(encoding="utf-8-sig"))

    def test_the_parents_codes_follow_the_students(self):
        self.svc.yearend_run({"confirm": True, "leaving": {"g4-a": ["منتقل بعيد"]}})
        m = json.loads((self.root / "cloud_students.json").read_text(encoding="utf-8"))
        self.assertEqual(m["g5-a|سارة علي"]["student"], "s1")                                      # same student code: the family stays linked
        self.assertEqual(m["g6-a|يوسف حسن"]["student"], "s3")                                      # moves to a class this app does not have
        self.assertNotIn("g4-a|منتقل بعيد", m)
        self.assertNotIn("g12-a|متخرج واحد", m)
        todo = json.loads((self.root / "yearend.json").read_text(encoding="utf-8"))["server"]
        self.assertEqual(sorted(todo["removed"]), ["s2", "s4"])
        self.assertIn({"code": "s1", "class_id": "g5-a", "grade_id": "g5"}, todo["moved"])

    def test_english_spelling_travels_with_the_student(self):
        self.svc.yearend_run({"confirm": True})
        self.assertEqual(self.svc.get_students("g5-a")["english"][0], "Sarah Aly")

    def test_it_cannot_be_run_twice_by_mistake(self):
        self.svc.yearend_run({"confirm": True})
        with self.assertRaises(AppError) as c:
            self.svc.yearend_run({"confirm": True})
        self.assertEqual(c.exception.code, "yearend_done")
        self.svc.yearend_run({"confirm": True, "again": True})


if __name__ == "__main__":
    unittest.main()
