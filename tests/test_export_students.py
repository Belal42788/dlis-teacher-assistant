"""The students leave as one Excel file: one class, or everyone."""
import unittest

import helpers
from app.core.errors import AppError


class TestExportStudents(helpers.AiCase):
    def _rows(self, r):
        from openpyxl import load_workbook
        return list(load_workbook(r["path"]).active.iter_rows(values_only=True))

    def test_one_class_and_everyone(self):
        self.svc.build_structure({"g4": ["A", "B"]})
        self.svc.put_students("g4-a", ["سارة علي حسن", "عمر سامي"])
        self.svc.put_students("g4-b", ["ليلى أحمد"], ["Layla Ahmed"])
        one = self._rows(self.svc.export_students("g4-a"))
        self.assertEqual(one[0], ("Class", "Name", "English name"))
        self.assertEqual([r[1] for r in one[1:]], ["سارة علي حسن", "عمر سامي"])
        everyone = self.svc.export_students("")
        self.assertEqual(everyone["count"], 3)
        self.assertIn("Layla Ahmed", [r[2] for r in self._rows(everyone)])

    def test_no_students_is_said_plainly(self):
        self.svc.build_structure({"g5": ["A"]})
        with self.assertRaises(AppError):
            self.svc.export_students("g5-a")


if __name__ == "__main__":
    unittest.main()
