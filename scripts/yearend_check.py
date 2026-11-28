"""Settings > End of the year in a real browser: tick a leaving student, confirm, and see the classes move up (desktop and phone)."""
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
        call("POST", "/api/structure/build", {"selection": {"g4": ["A"], "g5": ["A"], "g12": ["A"]}})
        call("PUT", "/api/rooms/g4-a/students", {"names": ["سارة علي", "عمر سامي", "طالب منتقل"]})
        call("PUT", "/api/rooms/g5-a/students", {"names": ["يوسف حسن"]})
        call("PUT", "/api/rooms/g12-a/students", {"names": ["متخرج واحد"]})
        pg = b.new_page(viewport={"width": width, "height": 900}, bypass_csp=True)
        pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base + "/"); pg.wait_for_timeout(900)
        pg.evaluate("location.hash='#/settings'"); pg.wait_for_selector("text=End of the year"); pg.click("text=End of the year")
        pg.wait_for_selector(".ye-room"); check(pg.locator(".ye-room").count() == 3, "three classes are listed")
        check("graduate" in pg.inner_text(".ye-rooms"), "the last grade is said to graduate")
        pg.locator(".ye-room >> nth=0").locator("summary").click(); pg.locator(".ye-name >> text=طالب منتقل").click()
        pg.click("#ye-ok") if pg.locator("#ye-ok").count() else pg.click(".ye-ok input")
        pg.click("button.primary >> text=Start end of year"); pg.click(".modal footer >> text=Start end of year")
        pg.wait_for_selector("text=is done")
        check(call("GET", "/api/rooms/g5-a/students")["names"] == ["سارة علي", "عمر سامي"], "Grade 4 A moved up to Grade 5 A without the one who left")
        check(call("GET", "/api/rooms/g12-a/students")["names"] == [], "Grade 12 left")
        check(width > 700 or pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "no sideways scroll on the phone")
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / f"yearend_{width}.png"))
        pg.close()
    b.close()
real = [e for e in errors if "Failed to load resource" not in e]
check(not real, f"browser errors: {real[:3]}")
s.shutdown(); print("yearend ok")
