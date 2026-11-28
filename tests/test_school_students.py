"""The whole school in one file: every row says the class."""
import base64
import io
import unittest
from pathlib import Path

import helpers
from app.core.errors import AppError
from app.core.school_students import group_by_room, parse_school_rows, room_key, rows_of

HTML = """<html><body><table>
<tr><th>اسم المستخدم</th><th>اسم الطالب</th><th>النوع</th><th>كلمة المرور</th><th>الصف</th><th>المجموعة</th><th>العنوان</th><th>الموبايل</th></tr>
<tr><td>1001</td><td>سارة علي حسن</td><td>أنثى</td><td>SecretPass99</td><td>Grade4</td><td>Grade4 A</td><td>شارع السر 5</td><td>01000000001</td></tr>
<tr><td>1002</td><td>عمر سامي</td><td>ذكر</td><td>SecretPass98</td><td>Grade4</td><td>Grade4 A</td><td>شارع السر 6</td><td>01000000002</td></tr>
<tr><td>1003</td><td>ليلى أحمد</td><td>أنثى</td><td>SecretPass97</td><td>PRE-K</td><td>PRE- K</td><td>شارع السر 7</td><td>01000000003</td></tr>
<tr><td>1004</td><td>كيجي اتنين</td><td>ذكر</td><td>SecretPass96</td><td>FS2</td><td>FS2 A</td><td>شارع السر 8</td><td>01000000004</td></tr>
</table></body></html>"""


class TestRoomKey(unittest.TestCase):
    def test_how_people_write_a_class(self):
        for label, want in (("g4-a", ("g4", "a")), ("Grade 4 A", ("g4", "a")), ("Grade10 B", ("g10", "b")), ("KG1 A", ("kg1", "a")), ("FS2 A", ("kg2", "a")),
                            ("PRE-K", ("kg1", "a")), ("PRE- K", ("kg1", "a")), ("Grade 13 A", None), ("hello", None), ("", None)):
            self.assertEqual(room_key(label), want, label)


class TestParse(unittest.TestCase):
    def test_the_old_school_export_is_read_without_the_private_columns(self):
        items = parse_school_rows(rows_of("export.xls", HTML.encode("utf-8"), ""))
        self.assertEqual(items, [("Grade4 A", "سارة علي حسن", ""), ("Grade4 A", "عمر سامي", ""), ("PRE- K", "ليلى أحمد", ""), ("FS2 A", "كيجي اتنين", "")])
        self.assertNotIn("SecretPass", repr(items)); self.assertNotIn("0100000", repr(items))
        groups, unknown = group_by_room(items)
        self.assertEqual(sorted(groups), [("g4", "a"), ("kg1", "a"), ("kg2", "a")]); self.assertEqual(unknown, [])

    def test_a_sheet_with_headers_and_english(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(["Room id", "Class", "Name", "English name", "Active"])
        ws.append(["g4-a", "Grade 4 A", "سارة علي حسن", "Sarah Aly Hassan", "Yes"])
        ws.append(["(not in the app)", "PRE-K", "ليلى أحمد", "Layla Ahmed", "Yes"])
        out = io.BytesIO(); wb.save(out)
        items = parse_school_rows(rows_of("a.xlsx", out.getvalue(), ""))
        self.assertEqual(items, [("g4-a", "سارة علي حسن", "Sarah Aly Hassan"), ("PRE-K", "ليلى أحمد", "Layla Ahmed")])

    def test_pasted_lines_without_headers(self):
        items = parse_school_rows(rows_of("", b"", "Grade 5 A\tملك اشرف محمد\tMalak Ashraf Mohamed\nKG1 A, سيف سامي\nhello\tworld"))
        self.assertEqual(items, [("Grade 5 A", "ملك اشرف محمد", "Malak Ashraf Mohamed"), ("KG1 A", "سيف سامي", "")])


class TestImportAll(helpers.AiCase):
    def _file(self, name="export.xls"):
        return {"filename": name, "data_b64": base64.b64encode(HTML.encode("utf-8")).decode()}

    def test_preview_then_import_adds_the_classes_and_places_every_student(self):
        self.svc.build_structure({"g4": ["A"]})
        p = self.svc.students_all_preview(self._file())
        self.assertEqual((p["students"], p["new_classes"]), (4, 2))
        r = self.svc.students_all_import({**self._file(), "add_classes": True})
        self.assertEqual((r["rooms"], r["students"]), (3, 4))
        self.assertEqual(self.svc.get_students("g4-a")["names"], ["سارة علي حسن", "عمر سامي"])
        self.assertEqual(self.svc.get_students("kg1-a")["names"], ["ليلى أحمد"])         # PRE-K sits with KG1
        self.assertEqual(self.svc.get_students("kg2-a")["names"], ["كيجي اتنين"])
        blob = b"".join(f.read_bytes() for f in Path(self.svc.store.root).rglob("*.csv"))
        self.assertNotIn(b"SecretPass", blob); self.assertNotIn(b"0100000", blob)       # passwords and phones never reach the app's data

    def test_without_adding_classes_the_unknown_ones_are_skipped_and_said(self):
        self.svc.build_structure({"g4": ["A"]})
        r = self.svc.students_all_import(self._file())
        self.assertEqual((r["rooms"], r["students"]), (1, 2))
        self.assertEqual(sorted(s["name"] for s in r["skipped"]), ["KG1 A", "KG2 A"])

    def test_add_mode_keeps_the_class_and_the_english_spelling(self):
        self.svc.build_structure({"g4": ["A"]})
        self.svc.put_students("g4-a", ["سارة علي حسن", "قديم"], ["Sarah Aly Hassan", ""])
        self.svc.students_all_import({**self._file(), "replace": False})
        got = self.svc.get_students("g4-a")
        self.assertEqual(got["names"], ["سارة علي حسن", "قديم", "عمر سامي"])
        self.assertEqual(got["english"][0], "Sarah Aly Hassan")

    def test_a_file_without_classes_is_said_plainly(self):
        with self.assertRaises(AppError) as c:
            self.svc.students_all_import({"text": "سارة علي\nعمر سامي"})
        self.assertEqual(c.exception.code, "school_students_none")


if __name__ == "__main__":
    unittest.main()
