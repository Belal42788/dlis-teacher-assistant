"""Weekly marks: typed on screen (or taken from an LMS file), kept on this computer, and sent to the parents' portal on request.

One sheet = one class, one trimester, one week. The five parts follow the school's grading sheet (see documents.GRADE_TOTALS).
Absent students have no marks (their rows stay empty and are removed from the portal)."""
from __future__ import annotations

import base64
import csv
import io
import re
import urllib.parse
from datetime import date

from ..core import documents as D
from ..core.errors import AppError

PARTS = [("behavior", "Behavior"), ("attendance", "Attendance"), ("classwork", "Classwork"), ("homework", "Homework"), ("quiz", "Quiz")]


def norm_name(s: str) -> str:
    s = re.sub(r"[ً-ٰٟـ]", "", str(s or "").lower())
    s = re.sub(r"[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def _same_person(a: str, b: str) -> bool:
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(short) >= 2 and all(w in long_ for w in short)


def _table(filename: str, data: bytes) -> list[list[str]]:
    low = (filename or "").lower()
    if low.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:
            raise AppError("file_unreadable", f"Could not read the Excel file: {e}", status=400) from e
        return [["" if c is None else str(c).strip() for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
    text = None
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = data.decode(enc); break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AppError("file_unreadable", "Could not read the file.", status=400)
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]


def _num(v):
    try:
        x = float(str(v).replace(",", ".").strip())
        return int(x) if x == int(x) else round(x, 2)
    except (ValueError, TypeError):
        return None


class GradesMixin:
    def _grades_path(self):
        return self._need_store().root / "grades.json"

    def _grades(self) -> dict:
        return self._need_store().read_json(self._grades_path(), {}, check=lambda x: isinstance(x, dict) or (_ for _ in ()).throw(ValueError("bad"))) or {}

    @staticmethod
    def _gkey(room, tri, week) -> str:
        return f"{room}|{int(tri)}|{int(week)}"

    def grades_get(self, room_id: str, tri: int, week: int) -> dict:
        self._room(room_id)
        names = self.get_students(room_id)["names"]
        cur = self._grades().get(self._gkey(room_id, tri, week), {})
        marks, absent = cur.get("marks", {}), set(cur.get("absent", []))
        return {"room_id": room_id, "trimester": tri, "week": week,
                "parts": [{"key": k, "label": lab, "max": D.GRADE_TOTALS[k]} for k, lab in PARTS],
                "students": [{"name": n, "absent": n in absent, "marks": marks.get(n, {})} for n in names],
                "lms_max": cur.get("lms_max") or 0, "uploaded": cur.get("uploaded", ""),
                "role": self._cloud_cfg()["role"]}

    def grades_put(self, b: dict) -> dict:
        room, tri, week = str(b.get("room_id", "")), int(b.get("trimester", 0)), int(b.get("week", 1))
        self._room(room)
        valid = set(self.get_students(room)["names"])
        lms_max = _num(b.get("lms_max")) or 0
        marks, absent = {}, []
        for r in b.get("rows") or []:
            name = str(r.get("name", ""))
            if name not in valid:
                continue
            if r.get("absent"):
                absent.append(name); continue
            keep = {}
            for k, _l in PARTS:
                v = _num((r.get("marks") or {}).get(k))
                if v is None:
                    continue
                if v < 0 or v > D.GRADE_TOTALS[k]:
                    raise AppError("grade_out_of_range", f"{name}: {k} must be between 0 and {D.GRADE_TOTALS[k]}.", status=400)
                keep[k] = v
            v = _num((r.get("marks") or {}).get("lms"))
            if v is not None:
                if v < 0 or (lms_max and v > lms_max):
                    raise AppError("grade_out_of_range", f"{name}: the LMS grade must be between 0 and {lms_max}.", status=400)
                keep["lms"] = v
            if keep:
                marks[name] = keep
        data = self._grades()
        key = self._gkey(room, tri, week)
        data[key] = {"absent": absent, "marks": marks, "lms_max": lms_max, "uploaded": data.get(key, {}).get("uploaded", "")}
        self._need_store().write_json(self._grades_path(), data)
        return self.grades_get(room, tri, week)

    def grades_import(self, b: dict) -> dict:
        """An LMS grade file (Excel or CSV with a name column and a grade column): the grades are matched to the class list by name."""
        room, tri, week = str(b.get("room_id", "")), int(b.get("trimester", 0)), int(b.get("week", 1))
        self._room(room)
        try:
            raw = base64.b64decode(b.get("data_b64") or "")
        except ValueError as e:
            raise AppError("file_unreadable", status=400) from e
        rows = [r for r in _table(str(b.get("filename", "")), raw) if any(c for c in r)]
        if len(rows) < 2:
            raise AppError("file_unreadable", "The file has no rows.", status=400)
        head = rows[0]
        name_c = next((i for i, c in enumerate(head) if re.search(r"name|student|اسم|الطالب|طالب", c, re.I)), None)
        grade_c = next((i for i, c in enumerate(head) if re.search(r"grade|score|mark|total|point|درج|المجموع|النتيجة", c, re.I)), None)
        body = rows[1:]
        if grade_c is None:
            width = max(len(r) for r in body)
            grade_c = next((i for i in range(width - 1, -1, -1) if sum(_num(r[i]) is not None for r in body if i < len(r)) >= max(1, len(body) // 2)), None)
        if name_c is None:
            width = max(len(r) for r in body)
            name_c = next((i for i in range(width) if i != grade_c and sum(bool(r[i].strip()) and _num(r[i]) is None for r in body if i < len(r)) >= max(1, len(body) // 2)), None)
        if name_c is None or grade_c is None:
            raise AppError("columns_not_found", "Could not find a student-name column and a grade column.", status=400)
        mx = _num(b.get("max"))
        if not mx:
            m = re.search(r"[(/]\s*(\d+(?:\.\d+)?)\s*\)?\s*$", head[grade_c]) or re.search(r"(\d+(?:\.\d+)?)", head[grade_c])
            mx = _num(m.group(1)) if m else 0
        st = self.get_students(room)
        names, english = st["names"], [e or a for e, a in zip(st["english"], st.get("auto") or st["english"])]
        data = self._grades()
        key = self._gkey(room, tri, week)
        sheet = data.get(key) or {"absent": [], "marks": {}, "lms_max": 0, "uploaded": ""}
        done, unmatched = 0, []
        for r in body:
            if name_c >= len(r) or grade_c >= len(r) or not r[name_c].strip():
                continue
            score = _num(r[grade_c])
            if score is None:
                continue
            i = next((i for i, n in enumerate(names) if _same_person(n, r[name_c]) or _same_person(english[i] if i < len(english) else "", r[name_c])), None)
            if i is None:
                unmatched.append(r[name_c].strip()); continue
            sheet["marks"].setdefault(names[i], {})["lms"] = score
            if names[i] in sheet["absent"]:
                sheet["absent"].remove(names[i])
            done += 1
        if done:
            sheet["lms_max"] = mx or sheet.get("lms_max") or 0
            data[key] = sheet
            self._need_store().write_json(self._grades_path(), data)
        return {**self.grades_get(room, tri, week), "imported": done, "unmatched": unmatched}

    def grades_upload(self, b: dict) -> dict:
        """Send this sheet to the parents' portal. Students are found on the school server by name (the administration made their codes)."""
        cfg = self._cloud_cfg()
        if cfg["role"] not in ("teacher", "admin"):
            raise AppError("cloud_staff_only", "Sign in with a teacher account first.", status=403)
        room, tri, week = str(b.get("room_id", "")), int(b.get("trimester", 0)), int(b.get("week", 1))
        self._room(room)
        sheet = self.grades_get(room, tri, week)
        subject = self._need_store().load_settings().subject or "Subject"
        c = self._cloud_client()
        theirs = c.select("students", f"select=code,display_name&class_id=eq.{room}")
        if not theirs:
            raise AppError("no_server_students", "This class is not on the school server yet. Ask the administration to prepare the parents' codes first.", status=409)
        st = self.get_students(room)
        english = [e or a for e, a in zip(st["english"], st.get("auto") or st["english"])]
        rows, gone, missing = [], [], []
        for i, s in enumerate(sheet["students"]):
            code = next((x["code"] for x in theirs if _same_person(x["display_name"], s["name"]) or _same_person(x["display_name"], english[i] if i < len(english) else "")), None)
            if not code:
                missing.append(s["name"]); continue
            if s["absent"] or not s["marks"]:
                gone.append(code); continue
            for k, label in PARTS:
                if k in s["marks"]:
                    rows.append({"student_code": code, "trimester": tri, "week": week, "subject": subject, "item": label, "score": s["marks"][k], "max_score": D.GRADE_TOTALS[k]})
            if "lms" in s["marks"]:
                rows.append({"student_code": code, "trimester": tri, "week": week, "subject": subject, "item": "Total", "score": s["marks"]["lms"], "max_score": sheet["lms_max"] or None})
        for code in gone:        # an absent student shows nothing for that week
            c.delete("grades", f"student_code=eq.{code}&trimester=eq.{tri}&week=eq.{week}&subject=eq.{urllib.parse.quote(subject, safe='')}")
        if rows:
            c.upsert("grades", rows, "student_code,trimester,week,subject,item")
        data = self._grades()
        key = self._gkey(room, tri, week)
        if key in data:
            data[key]["uploaded"] = date.today().isoformat()
            self._need_store().write_json(self._grades_path(), data)
        return {"sent": len({r["student_code"] for r in rows}), "rows": len(rows), "missing": missing}


# ---------------------------------------------------------------- class overview (marks + lesson log)
ATTENTION_PCT, ATTENTION_ABSENT = 60, 2


def _pct(marks: dict, lms_max) -> float | None:
    """A student's week as a percentage of the parts that were marked (or of the LMS grade when only that exists)."""
    got = sum(marks[k] for k in D.GRADE_TOTALS if k in marks)
    out = sum(D.GRADE_TOTALS[k] for k in D.GRADE_TOTALS if k in marks)
    if out:
        return got / out * 100
    if "lms" in marks and lms_max:
        return marks["lms"] / lms_max * 100
    return None


class InsightsMixin:
    def insights_get(self, room_id: str, tri: int) -> dict:
        room = self._room(room_id)
        names = self.get_students(room_id)["names"]
        sheets = {int(k.split("|")[2]): v for k, v in self._grades().items() if k.startswith(f"{room_id}|{int(tri)}|")}
        weeks, per = [], {n: {"pcts": [], "absent": 0, "last": None} for n in names}
        for w in sorted(sheets):
            sh = sheets[w]
            pcts = []
            for n in names:
                if n in sh.get("absent", []):
                    per[n]["absent"] += 1
                    continue
                p = _pct(sh.get("marks", {}).get(n, {}), sh.get("lms_max"))
                if p is not None:
                    pcts.append(p); per[n]["pcts"].append(p); per[n]["last"] = round(p)
            weeks.append({"week": w, "avg": round(sum(pcts) / len(pcts)) if pcts else None, "marked": len(pcts), "absent": len(sh.get("absent", []))})
        rows = []
        for n in names:
            p = per[n]["pcts"]
            avg = round(sum(p) / len(p)) if p else None
            rows.append({"name": n, "avg": avg, "absent": per[n]["absent"], "last": per[n]["last"],
                         "attention": (avg is not None and avg < ATTENTION_PCT) or per[n]["absent"] >= ATTENTION_ABSENT})
        allp = [x for v in per.values() for x in v["pcts"]]
        cal = self._calendar_service()
        try:
            ws = cal.trimester_weeks(int(tri))
            lo, hi = ws[0]["start"], ws[-1]["end"]
        except (IndexError, KeyError):
            lo, hi = "0000-00-00", "9999-99-99"
        entries = sorted((e for e in self._log_data()["entries"] if e["room_id"] == room_id and lo <= e["date"] <= hi), key=lambda e: e["date"])
        return {"room_id": room_id, "room": room.name, "trimester": tri, "students": len(names), "avg": round(sum(allp) / len(allp)) if allp else None,
                "weeks": weeks, "rows": rows, "attention_pct": ATTENTION_PCT, "attention_absent": ATTENTION_ABSENT,
                "lessons": len(entries), "last_topic": entries[-1].get("topic", "") if entries else "", "last_date": entries[-1]["date"] if entries else "",
                "absences": sum(w["absent"] for w in weeks)}
