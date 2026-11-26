"""Pasting names: the English spelling written next to an Arabic name is kept with it."""
import io
import unittest

import helpers  # noqa: F401
from app.core.students import parse_file, parse_text


class TestNamesWithEnglish(unittest.TestCase):
    def test_two_columns_pasted_from_excel(self):
        r = parse_text("ملك اشرف محمد\tMalak Ashraf Mohamed\nسيف محمد سامي\tSeif Mohamed Samy")
        self.assertEqual(r["names"], ["ملك اشرف محمد", "سيف محمد سامي"])
        self.assertEqual(r["english"], ["Malak Ashraf Mohamed", "Seif Mohamed Samy"])

    def test_both_written_in_one_line_and_either_order(self):
        r = parse_text("ملك اشرف محمد - Malak Ashraf Mohamed\nSeif Mohamed Samy  سيف محمد سامي\nليلى أحمد حسن, Layla Ahmed Hassan")
        self.assertEqual(r["english"], ["Malak Ashraf Mohamed", "Seif Mohamed Samy", "Layla Ahmed Hassan"])
        self.assertEqual(r["names"][1], "سيف محمد سامي")

    def test_a_whole_sheet_with_class_and_header_is_understood(self):
        text = "Room id\tClass\tName\tEnglish name\tActive\ng4-a\tGrade 4 A\tملك اشرف محمد\tMalak Ashraf Mohamed\tYes\ng4-a\tGrade 4 A\tسيف محمد سامي\tSeif Mohamed Samy\tNo"
        r = parse_text(text)
        self.assertEqual(r["names"], ["ملك اشرف محمد", "سيف محمد سامي"])
        self.assertEqual(r["english"], ["Malak Ashraf Mohamed", "Seif Mohamed Samy"])

    def test_gender_and_class_columns_are_never_taken_for_english(self):
        r = parse_text("1008\tملك اشرف محمد\tFemale\tGrade9 A\n1009\tسيف محمد سامي\tMale\tGrade9 A")
        self.assertEqual(r["names"], ["ملك اشرف محمد", "سيف محمد سامي"])
        self.assertEqual(r["english"], ["", ""])

    def test_plain_arabic_list_is_as_before(self):
        r = parse_text("1. سارة علي\n2. عمر سامي")
        self.assertEqual((r["names"], r["english"]), (["سارة علي", "عمر سامي"], ["", ""]))

    def test_excel_file(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(["Name", "English name"]); ws.append(["ملك اشرف محمد", "Malak Ashraf Mohamed"])
        out = io.BytesIO(); wb.save(out)
        r = parse_file("a.xlsx", out.getvalue())
        self.assertEqual((r["names"], r["english"]), (["ملك اشرف محمد"], ["Malak Ashraf Mohamed"]))


if __name__ == "__main__":
    unittest.main()
