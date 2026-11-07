"""A school year of data in one teacher's folder, then the hard cases: how long the screens' data takes, many requests at once
(reads and saves together), a folder name with Arabic letters, spaces and brackets, a damaged file, the weekly backup.
Run:  python scripts/stress.py        (about a minute; prints a table, exits 1 if something is slow or fails)"""
import json, os, statistics, sys, tempfile, threading, time, urllib.error, urllib.request, zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _s in (sys.stdout, sys.stderr):   # Windows consoles default to a code page that cannot print Arabic
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
home = tempfile.mkdtemp()
data = Path(tempfile.mkdtemp()) / "مدرسة دار لقمان (نسخة 2026) - بيانات المدرس"   # Arabic letters, spaces, brackets
os.environ.update(DLIS_APP_HOME=home, HOME=home, USERPROFILE=home, PYTHONUTF8="1")
sys.path.insert(0, str(ROOT))
from app.server.http import AppServer

server = AppServer()
server.start_in_thread()
url = f"http://127.0.0.1:{server.port_number}"
token = server.token
proc = server
fails, slow = [], []


def call(method, path, body=None, ok=(200,)):
    req = urllib.request.Request(url + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-DLIS-Token": token, "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw, st = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read(), e.code
    dt = (time.perf_counter() - t0) * 1000
    if st not in ok:
        fails.append(f"{method} {path} -> {st} {raw[:120]!r}")
    return (json.loads(raw) if raw else None), dt


try:
    d, _ = call("POST", "/api/data-folder", {"path": str(data)})
    print("data-folder ->", (d or {}).get("data_folder"))
    assert data.exists(), "the folder with Arabic letters was not created"
    call("PUT", "/api/settings", {"teacher_name": "بلال عبدالناصر", "subject": "ICT"})
    grades = ["kg1", "kg2"] + [f"g{i}" for i in range(1, 12)]
    call("POST", "/api/structure/build", {"selection": {g: ["A", "B", "C"] for g in grades}})
    st, _ = call("GET", "/api/structure")
    rooms = [r["id"] for r in st["rooms"]]
    for i, rid in enumerate(rooms):   # 30 students in every class
        call("PUT", f"/api/rooms/{rid}/students", {"names": [f"طالب رقم {i}-{k} عبدالرحمن" for k in range(30)]})
    # a full week of lessons and a busy calendar, so Today and the year overview have real work to do
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    grid = {d: {str(p): rooms[(i * 8 + p) % len(rooms)] for p in range(1, 7)} for i, d in enumerate(days)}
    call("PUT", "/api/timetable", {"grid": grid, "overrides": {}, "duties": {"Monday": ["break"], "Wednesday": ["late"]}})
    call("PUT", "/api/calendar", {"academic_year": "2026-2027",
         "trimesters": [{"name": "T1", "start": "2026-09-01", "end": "2026-12-10", "week1_start": ""},
                        {"name": "T2", "start": "2027-01-04", "end": "2027-03-25", "week1_start": ""},
                        {"name": "T3", "start": "2027-04-12", "end": "2027-06-24", "week1_start": ""}],
         "holidays": [{"start": f"2026-{m:02d}-{d:02d}", "end": "", "name": f"إجازة {m}/{d}"} for m, d in ((10, 6), (10, 15), (11, 2), (11, 30))],
         "events": [{"date": (date(2026, 9, 1) + timedelta(days=k * 3)).isoformat(), "name": f"فعالية رقم {k}", "kind": "event"} for k in range(120)]})
    t0 = date(2026, 9, 1)
    for k in range(400):   # 400 tasks
        call("POST", "/api/tasks", {"title": f"مهمة رقم {k} للتجربة", "importance": ["high", "medium", "low"][k % 3],
                                    "deadline": (t0 + timedelta(days=k % 120)).isoformat()})
    for w in range(30):    # 30 weeks of lesson logs for 6 classes, 4 lessons a week
        for rid in rooms[:6]:
            for p in range(1, 5):
                call("POST", "/api/log", {"room_id": rid, "date": (t0 + timedelta(days=w * 7 + p % 5)).isoformat(), "period": str(p),
                                          "topic": f"درس {w}-{p}", "slide": 5, "total": 20, "note": "ملاحظة " * 10})
    size = sum(f.stat().st_size for f in data.rglob("*") if f.is_file()) / 1024
    print(f"data folder: {len(rooms)} classes, {len(rooms) * 30} students, 400 tasks, 720 log lines, {size:.0f} KB")

    print(f"\n{'endpoint':38}{'median ms':>10}{'max ms':>8}")
    for path in ["/api/bootstrap", "/api/structure", "/api/overview", "/api/tasks", "/api/today?date=2026-10-11", "/api/today?date=2026-10-28", "/api/log/last",
                 "/api/timetable", "/api/calendar", f"/api/rooms/{rooms[3]}/students", "/api/reminders", "/api/week-prep"]:
        first, _ = call("GET", path, ok=(200, 404, 409))
        ts = [call("GET", path, ok=(200, 404, 409))[1] for _ in range(7)]
        med = statistics.median(ts)
        size = len(json.dumps(first, ensure_ascii=False)) // 1024 if first is not None else -1
        print(f"{path:38}{med:10.0f}{max(ts):8.0f}{size:6} KB" if size >= 0 else f"{path:38}{med:10.0f}{max(ts):8.0f}   (no data / 404)")
        if med > 250:
            slow.append(f"{path} median {med:.0f} ms")

    # many things at once: 6 readers and 2 savers together for 10 seconds
    stop = time.time() + 10
    counts = {"reads": 0, "writes": 0}

    def reader():
        while time.time() < stop:
            for p in ("/api/tasks", "/api/today?date=2026-10-11", "/api/structure", "/api/overview"):
                call("GET", p, ok=(200, 404, 409)); counts["reads"] += 1

    def writer(n):
        i = 0
        while time.time() < stop:
            call("POST", "/api/tasks", {"title": f"تزامن {n}-{i}"}); counts["writes"] += 1; i += 1
    th = [threading.Thread(target=reader) for _ in range(6)] + [threading.Thread(target=writer, args=(n,)) for n in range(2)]
    [x.start() for x in th]; [x.join() for x in th]
    after, _ = call("GET", "/api/tasks")
    print(f"\nat the same time: {counts['reads']} reads and {counts['writes']} saves in 10 s, tasks now {len(after['tasks'])}")
    if len(after["tasks"]) != 400 + counts["writes"]:
        fails.append(f"a save was lost: expected {400 + counts['writes']} tasks, found {len(after['tasks'])}")

    # a damaged file: the app must still open and say so, not crash
    victim = next(p for p in data.rglob("*.json") if p.stat().st_size > 50 and "_backup" not in p.parts)
    victim.write_text("{ this is not json", encoding="utf-8")
    _, dt = call("GET", "/api/bootstrap")
    r, _ = call("GET", "/api/structure", ok=(200, 409, 500))
    left = [f.name for f in data.rglob("*.json*") if "damaged" in f.name or "corrupt" in f.name or "bad" in f.name]
    print(f"damaged file {victim.name}: bootstrap {dt:.0f} ms, structure answered, quarantined copies: {left or 'none'}")

    # the weekly copy, on this much data
    from app.core.store import DataStore
    t1 = time.perf_counter()
    z = DataStore(data).auto_backup(every_days=0)
    names = zipfile.ZipFile(z).namelist()
    print(f"weekly backup: {(time.perf_counter() - t1) * 1000:.0f} ms, {z.stat().st_size / 1024:.0f} KB, {len(names)} files, "
          f"students files: {sum('student' in n.lower() for n in names)}, log files: {sum('log' in n.lower() for n in names)}")
finally:
    server.shutdown()

print()
for x in slow: print("SLOW:", x)
for x in fails[:15]: print("FAIL:", x)
print("OK" if not slow and not fails else f"{len(slow)} slow, {len(fails)} failures")
sys.exit(1 if slow or fails else 0)
