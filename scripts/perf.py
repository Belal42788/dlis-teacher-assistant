"""Measures how fast the program feels: opening it, switching pages, and the slowest server answers. Run it before and after a speed change.
    python scripts/perf.py            normal computer
    python scripts/perf.py --slow     a computer 4 times slower (CPU throttled), like an old school laptop"""
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_data import base, call, s
from playwright.sync_api import sync_playwright

SLOW = "--slow" in sys.argv
PAGES = ["today", "timetable", "calendar", "tasks", "docs", "library", "bank", "classes", "grades", "behavior", "seating", "map", "settings", "chat"]
call("POST", "/api/whats-new/seen", {})
call("PUT", "/api/prefs", {"language": "ar"})

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg)
    if SLOW:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    reqs = []
    pg.on("response", lambda r: reqs.append((r.url.replace(base, ""), r.status, len(r.body()) if r.status == 200 and r.request.resource_type != "fetch" else 0, r.headers.get("content-encoding", ""))))
    # opening the program: from the address to the first page drawn
    cold = []
    for k in range(3):
        reqs.clear()
        t0 = time.perf_counter()
        pg.goto(base + "/#/today"); pg.wait_for_selector("#main:not(.busy) .panel, #main:not(.busy) .tl, #main:not(.busy) .page", timeout=20000)
        cold.append(time.perf_counter() - t0)
        if k == 0:
            first = list(reqs)
        pg.wait_for_timeout(500)
    files = [r for r in first if r[0].endswith((".js", ".css", ".json", ".svg", ".png", ".woff2", ".html")) or r[0] == "/"]
    print(f"OPEN   first {cold[0]*1000:.0f} ms, again {statistics.median(cold[1:])*1000:.0f} ms   files: {len(files)}, {sum(r[2] for r in files)//1024} KB, compressed: {sum(1 for r in files if r[3])}")
    # switching pages
    times = {}
    for page_id in PAGES * 2:
        pg.evaluate("location.hash='#/today'"); pg.wait_for_timeout(150)
        t0 = time.perf_counter()
        pg.evaluate(f"location.hash='#/{page_id}'")
        pg.wait_for_function("(() => { const m = document.querySelector('#main'); return m && !m.classList.contains('busy') && m.children.length > 0; })()", timeout=20000)
        times.setdefault(page_id, []).append((time.perf_counter() - t0) * 1000)
    print("SWITCH ms (best of 2):  " + "  ".join(f"{k} {min(v):.0f}" for k, v in sorted(times.items(), key=lambda kv: -min(kv[1]))))
    b.close()

# the server alone: every list/get call, 5 times
import urllib.request

rooms = [r["id"] for r in call("GET", "/api/structure")["rooms"]]
calls = ["/api/bootstrap", "/api/overview", "/api/structure", "/api/today", "/api/timetable", "/api/tasks", "/api/tools", "/api/library", "/api/bank?grade_id=g4", "/api/bank/topics",
         "/api/school-calendar", "/api/week-prep", "/api/reminders", f"/api/rooms/{rooms[0]}/students", "/api/map", "/api/ai"]
rows = []
for path in calls:
    ts = []
    for _ in range(5):
        r = urllib.request.Request(base + path, headers={"X-DLIS-Token": s.token})
        t0 = time.perf_counter()
        try:
            n = len(urllib.request.urlopen(r).read())
        except Exception:
            n = -1
        ts.append((time.perf_counter() - t0) * 1000)
    rows.append((min(ts), path, n))
print("SERVER ms (best of 5):  " + "  ".join(f"{p.split('?')[0]} {t:.0f}({n // 1024}KB)" for t, p, n in sorted(rows, reverse=True)[:8]))
s.shutdown()
