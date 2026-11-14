"""Takes the screenshots used by README.md / README_AR.md (docs/images/en and docs/images/ar) with MADE-UP data only:
made-up teacher, made-up students, a fixed day and time so every picture looks the same each time.
    python scripts/make_readme_shots.py          (about 1 minute)"""
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
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
os.environ["DLIS_SCHOOL_DATA"] = str(ROOT / "tests" / "fixtures" / "school_data")   # made-up lists, never a school's real ones
sys.path.insert(0, str(ROOT))

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

from PIL import Image
from playwright.sync_api import sync_playwright

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

OUT = ROOT / "docs" / "images"
SHOTS = [  # (file, hash, wait selector, extra action)
    ("today", "today", ".tl, .today, .panel", None),
    ("timetable", "timetable", ".tt, table", None),
    ("calendar", "calendar", ".cal-year, .cal, .panel", None),
    ("tasks", "tasks", ".panel", None),
    ("create", "docs", ".cr-hub", None),
    ("tool", "tools?tool=lesson_starter", ".panel", None),
    ("files", "library", ".lib-tree, .panel", None),
    ("bank", "bank", ".bk-card", None),
    ("classes", "classes", ".students li", None),
    ("grades", "grades", "table, .panel", None),
    ("behavior", "behavior", ".panel", None),
    ("seating", "seating", ".panel", None),
    ("map", "map", ".panel, svg", None),
    ("settings", "settings", ".panel", None),
]
with sync_playwright() as p:
    b = p.chromium.launch()
    for lang in ("en", "ar"):
        call("PUT", "/api/prefs", {"language": lang})
        out = OUT / lang; out.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        pg = ctx.new_page(); pg.clock.set_fixed_time(NOW)
        pg.add_init_script("localStorage.setItem('dlis.lang','%s')" % lang)
        pg.goto(base + "/"); pg.wait_for_timeout(900)
        for i, (name, h_, sel, _) in enumerate(SHOTS, 1):
            pg.evaluate(f"location.hash='#/{h_}'")
            try:
                pg.wait_for_selector("#main:not(.busy)", timeout=8000); pg.wait_for_selector(sel, timeout=8000)
            except Exception:
                print("  (no", sel, "on", name, ")")
            pg.wait_for_timeout(700)
            f = out / f"{i:02d}-{name}.png"
            pg.screenshot(path=str(f))
            Image.open(f).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(f, optimize=True)
        ctx.close()
    b.close()
s.shutdown()
print("done:", sum(1 for _ in OUT.rglob("*.png")), "pictures,", sum(f.stat().st_size for f in OUT.rglob("*.png")) // 1024, "KB")
