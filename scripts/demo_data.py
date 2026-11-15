"""Made-up demo data for the README pictures and the speed measurements: a made-up teacher, made-up students, a fixed day with the
server believing it is that day. Importing this module starts an in-process server (`s`, `base`, `call`) and fills it with data."""
import base64
import datetime as dt
import io
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp(); os.environ["DLIS_NO_KEYCHAIN"] = "1"
os.environ["DLIS_SCHOOL_DATA"] = str(ROOT / "tests" / "fixtures" / "school_data")   # made-up lists, never a school's real ones
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

DAY = dt.date(2026, 11, 17)             # a Tuesday in the first trimester
NOW = "2026-11-17T10:20:00"
class FakeDate(dt.date):                # the server believes it is DAY
    @classmethod
    def today(cls):
        return cls(DAY.year, DAY.month, DAY.day)

import importlib
import pkgutil

import app.core
import app.server

for pkg in (app.core, app.server):
    for mod in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        m = importlib.import_module(mod.name)
        if getattr(m, "date", None) is dt.date:
            m.date = FakeDate


from app.server.http import AppServer

s = AppServer(); s.start_in_thread()
base = f"http://127.0.0.1:{s.port_number}"
def call(m, p, b=None):
    r = urllib.request.Request(base + p, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"X-DLIS-Token": s.token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r).read() or b"null")

NAMES = ["أحمد سمير حسن", "ليلى محمود علي", "عمر خالد إبراهيم", "مريم أشرف سعيد", "يوسف هاني كمال", "نور ياسر فؤاد", "كريم عادل مصطفى", "سلمى وائل عثمان", "آدم طارق منصور", "جنى رامي صلاح", "زياد ماجد فتحي", "هدى بلال شريف"]
call("POST", "/api/data-folder", {"path": tempfile.mkdtemp() + "/data"})
call("POST", "/api/whats-new/seen", {})
call("PUT", "/api/settings", {"teacher_name": "ماجد حسن", "name_en": "Majed Hassan", "subject": "ICT", "setup_done": True})
call("POST", "/api/structure/build", {"selection": {"g4": ["A", "B"], "g5": ["A"], "g6": ["A"], "g7": ["A"]}})
call("PUT", "/api/calendar", call("GET", "/api/school-calendar"))
rooms = [r["id"] for r in call("GET", "/api/structure")["rooms"]]
g4a = next(r for r in rooms if r.startswith("g4"))
for r in rooms:
    call("PUT", f"/api/rooms/{r}/students", {"names": NAMES})
tt = call("GET", "/api/timetable"); days = call("GET", "/api/settings")["working_days"]; periods = [p["name"] for p in tt["periods"]]
grid = {d: {p: rooms[(i + j) % len(rooms)] for j, p in enumerate(periods) if (i + j) % 5 != 4} for i, d in enumerate(days)}
call("PUT", "/api/timetable", {"grid": grid, "duties": {d: ["break"] for d in days}})
for title, imp, dl in [("Prepare the Grade 4 quiz", "high", "2026-11-19"), ("Upload last week's marks to the LMS", "medium", "2026-11-18"), ("Print the revision sheets", "low", "2026-11-24")]:
    call("POST", "/api/tasks", {"title": title, "importance": imp, "deadline": dl})
for st_, kind, note in [(NAMES[1], "good", "Helped a classmate with the mouse"), (NAMES[2], "concern", "Late three times this week"), (NAMES[4], "good", "Great answer in class")]:
    call("POST", "/api/behavior", {"room_id": g4a, "student": st_, "kind": kind, "note": note, "date": "2026-11-16"})
call("PUT", "/api/seating", {"room_id": g4a, "rows": 3, "cols": 4, "seats": {f"{i // 4}-{i % 4}": n for i, n in enumerate(NAMES)}})
rows = [{"name": n, "marks": {"behavior": 8 + i % 3, "attendance": 9 + i % 2, "quiz": 14 + i % 6}} for i, n in enumerate(NAMES)]
call("PUT", "/api/grades", {"room_id": g4a, "trimester": 0, "week": 8, "rows": rows})
call("POST", "/api/log", {"room_id": g4a, "date": "2026-11-16", "period": "2", "topic": "Input devices", "slide": 8, "total": 12, "next_note": "Bring a mouse to class"})
from docx import Document

d = Document(); d.add_paragraph("Chapter one is about input devices such as the keyboard and the mouse."); buf = io.BytesIO(); d.save(buf)
call("POST", "/api/sources/import", {"filename": "ICT Grade 4 Book.docx", "data_b64": base64.b64encode(buf.getvalue()).decode()})
TOPICS = [("Input devices", "easy"), ("Output devices", "medium"), ("Networks", "hard"), ("Software", "medium")]
for tp, lv in TOPICS:
    qs = "\n\n".join(f"{i}. Question {i} about {tp.lower()}?\na) First answer\nb) Second answer\nc) Third answer\nAnswer: a" for i in range(1, 5))
    call("POST", "/api/bank", {"grade_id": "g4", "topic": tp, "level": lv, "text": qs})
call("POST", "/api/docs/quiz", {"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
ids = [i["id"] for i in call("GET", "/api/bank?grade_id=g4")["items"]]
s.service._bank_mark_used(ids[:5], "Grade 4 T1-W08 Quiz 1")
call("PUT", "/api/bank/basket", {"ids": [ids[0], ids[5], ids[9]]})
lib = call("GET", "/api/library")
bk = [i for i in lib["items"] if i["kind"] == "book"][0]
call("POST", "/api/library/place", {"rel": bk["rel"], "pid": "auto", "t": 0, "w": 8, "note": "Chapter one: input devices"})
call("POST", "/api/library/message", {"text": "Tomorrow we finish the mouse. Bring your book. The quiz is next week.", "g": "g4", "t": 0, "w": 8})
call("POST", "/api/library/link", {"title": "Keyboard basics (video)", "url": "https://example.com/keyboard"})

