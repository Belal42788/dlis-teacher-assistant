"""Classes > Import the whole school in a real browser: paste rows with classes, see the preview, import (desktop and phone)."""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp(); os.environ["DLIS_NO_KEYCHAIN"] = "1"
os.environ["DLIS_SCHOOL_DATA"] = os.path.join(root, "tests", "fixtures", "school_data")
sys.path.insert(0, root)
from playwright.sync_api import sync_playwright

from app.server.http import AppServer

s = AppServer(); s.start_in_thread(); base = f"http://127.0.0.1:{s.port_number}"


def call(m, p, b=None):
    r = urllib.request.Request(base + p, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"X-DLIS-Token": s.token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r).read() or b"null")


def check(cond, msg):
    if not cond:
        print("FAILED:", msg); s.shutdown(); sys.exit(1)


errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1200, 390):
        call("POST", "/api/data-folder", {"path": tempfile.mkdtemp() + "/d"}); call("PUT", "/api/prefs", {"language": "en"})
        call("PUT", "/api/settings", {"teacher_name": "T", "subject": "ICT", "setup_done": True}); call("POST", "/api/whats-new/seen", {})
        call("POST", "/api/structure/build", {"selection": {"g4": ["A"]}})
        pg = b.new_page(viewport={"width": width, "height": 900}, bypass_csp=True)
        pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base + "/"); pg.wait_for_timeout(900)
        pg.evaluate("location.hash='#/classes'"); pg.click("text=Import the whole school")
        pg.fill(".modal textarea", "Grade 4 A\tسارة علي حسن\tSarah Aly Hassan\nGrade 4 A\tعمر سامي\nPRE-K\tليلى أحمد\nKG2 A\tكيجي اتنين\nGrade 99 Z\tمجهول واحد")
        pg.dispatch_event(".modal textarea", "change"); pg.wait_for_selector(".si-table")
        txt = pg.inner_text(".modal")
        check("Found 4 students in 3 classes" in txt, f"preview text: {txt[:200]}")
        check("new class" in txt and "you have it" in txt, "preview says which classes are new")
        check("not understood" in txt, "unknown class is warned about")
        pg.click(".modal footer >> text=Import"); pg.wait_for_timeout(1200)
        check(call("GET", "/api/rooms/g4-a/students")["names"] == ["سارة علي حسن", "عمر سامي"], "Grade 4 A filled")
        check(call("GET", "/api/rooms/kg1-a/students")["names"] == ["ليلى أحمد"], "PRE-K sits with KG1")
        check(call("GET", "/api/rooms/g4-a/students")["english"][0] == "Sarah Aly Hassan", "English kept")
        check(width > 700 or pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "no sideways scroll on the phone")
        pg.close()
    b.close()
real = [e for e in errors if "Failed to load resource" not in e]
check(not real, f"browser errors: {real[:3]}")
s.shutdown(); print("school import ok")
