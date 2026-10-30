"""Drive the real app in a browser: whole first-run guide in Arabic, then every page, then English."""
import datetime as _dt, os, subprocess, sys, tempfile, time, re, json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = Path(os.environ.get("SHOTS", "/tmp/shots")); SHOTS.mkdir(exist_ok=True, parents=True)
home = tempfile.mkdtemp(); data = Path(tempfile.mkdtemp()) / "My DLIS"
env = dict(os.environ, DLIS_APP_HOME=home, HOME=home)  # fake HOME so the folder picker is isolated
(Path(home) / "Documents").mkdir()
# the server thinks it is a school day (Wed 28 Oct 2026), so the screens do not depend on the weekday the test runs on
_fake = Path(tempfile.mkdtemp()); (_fake / "sitecustomize.py").write_text(
    "import datetime as _d\nclass date(_d.date):\n    @classmethod\n    def today(cls):\n        return cls(2026, 10, 28)\n_d.date = date\n")
env["PYTHONPATH"] = str(_fake)
proc = subprocess.Popen([sys.executable, "-m", "app", "--no-window"], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
url = proc.stdout.readline().strip()
print("server", url)
errors = []

def setdate(loc, iso):
    """Fill one day/month/year field (loc = the .date3 element)."""
    y, m, d = (int(x) for x in iso.split("-"))
    sel = loc.locator("select"); sel.nth(0).select_option(str(d)); sel.nth(1).select_option(str(m)); sel.nth(2).select_option(str(y))
# ---- a tiny fake AI service so the AI screens can be tested without internet
import json as _json, threading as _th
from http.server import BaseHTTPRequestHandler as _H, HTTPServer as _S
class _Fake(_H):
    def log_message(self, *a): pass
    def do_GET(self):
        self._out({"data": [{"id": "fake-model"}]})
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = _json.loads(self.rfile.read(n))
        prompt = body["messages"][-1]["content"]
        if isinstance(prompt, list): prompt = prompt[0]["text"]
        if "multiple-choice" in prompt: txt = "1. What is a CPU?\na) Brain\nb) Screen\nAnswer: a\n\n2. Which is input?\na) Mouse\nb) Speaker\nAnswer: a"
        elif '"pages"' in prompt: txt = _json.dumps({"pages": [{"n": 1, "text": "Input devices: keyboard and mouse", "diagram": "a keyboard"}]})
        elif 'short lesson title' in prompt: txt = _json.dumps({"topic": "Input devices", "objectives": ["Name input devices"], "points": ["A mouse points"], "words": [{"term": "Mouse", "meaning": "points and clicks"}], "questions": [{"q": "What is a mouse?", "a": "An input device"}]})
        elif '"words"' in prompt: txt = _json.dumps({"words": [{"term": "CPU", "meaning": "the brain"}], "points": ["Input sends data in"], "questions": [{"q": "What is the CPU?", "a": "The brain"}]})
        elif '"slides"' in prompt: txt = _json.dumps({"slides": [{"title": "What we learn", "bullets": ["Keyboard", "Mouse"], "notes": "Say hi", "image_prompt": "a keyboard"}, {"title": "Recap", "bullets": ["Input devices send data"], "notes": "", "image_prompt": ""}]})
        elif '"lessons"' in prompt: txt = _json.dumps({"lessons": ["Intro", "Hardware"]})
        elif "JSON object" in prompt: txt = _json.dumps({"topic": "Hardware", "objectives": ["Name parts", "Explain use"], "sunday": "Warm up"})
        elif "[student]" in prompt: txt = "Dear parent of [student], thank you for your support."
        else: txt = "ready"
        self._out({"choices": [{"message": {"content": txt}}]})
    def _out(self, d):
        b = _json.dumps(d).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
_fake = _S(("127.0.0.1", 0), _Fake); _th.Thread(target=_fake.serve_forever, daemon=True).start()
FAKE_URL = f"http://127.0.0.1:{_fake.server_address[1]}/v1"

try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 860})
        page = ctx.new_page(); page.clock.install(time=_dt.datetime(2026, 10, 28, 9, 0, 0))
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        shot = lambda n: page.screenshot(path=str(SHOTS / f"{n}.png"))
        page.goto(url); page.wait_for_selector(".lang-pick"); shot("01_language")
        page.click("button[lang=ar]")
        page.wait_for_selector(".folder-box"); assert page.evaluate("document.documentElement.dir") == "rtl"; shot("02_folder")
        # choose another folder through the picker, create a new folder
        page.click("text=اختيار مجلد آخر"); page.wait_for_selector(".folders"); shot("02b_picker")
        page.fill("#newfolder", "My DLIS"); page.click("text=إنشاء مجلد"); page.wait_for_function("document.querySelector('.crumb').textContent.endsWith('My DLIS')")
        page.click("text=استخدم هذا المجلد >> nth=-1")
        page.wait_for_function("document.querySelector('.folder-box').textContent.endsWith('My DLIS')")
        page.click(".wiz-foot .btn.primary")
        page.wait_for_selector("text=عرّفنا بنفسك")
        # about: validation first
        page.click(".wiz-foot .btn.primary"); page.wait_for_selector(".toast.error"); shot("03_about_error")
        page.fill("input[autocomplete=name]", "بلال عبدالناصر"); page.select_option(".panel select", "ICT"); shot("03_about")
        page.click(".wiz-foot .btn.primary")
        page.wait_for_selector(".grade-row")
        # classes: tick G4 + sections B, G5, whole KG stage
        rows = page.locator(".grade-row")
        for label in ("الصف الرابع", "الصف الخامس"):
            page.locator(".grade-row", has_text=label).locator("input[type=checkbox]").check()
        page.locator(".grade-row", has_text="الصف الرابع").locator("button.chip", has_text="B").click()
        page.locator(".stage-title", has=page.locator("h3", has_text="رياض الأطفال")).locator("button").click()
        shot("04_classes")
        page.click(".wiz-foot .btn.primary")
        page.wait_for_selector("table.grid")
        # timetable: choose two classes
        sels = page.locator("table.grid tbody select")
        sels.nth(0).select_option(index=1); sels.nth(6).select_option(index=2)
        assert page.locator("table.grid tbody th").first.inner_text().strip() == "الأحد", "week must start on Sunday"
        assert "8:00 ص" in page.locator("table.grid thead th.p").first.inner_text(), "fixed times shown in 12-hour form"
        assert "G4" in page.locator("table.grid tbody select").first.inner_text(), "short class names in the table"
        shot("05_timetable"); page.click(".wiz-foot .btn.primary")
        page.wait_for_selector(".tri-row")
        for i, (a, z) in enumerate((("2026-09-01", "2026-11-30"), ("2026-12-01", "2027-02-28"))):
            ds = page.locator(".tri-row").nth(i).locator(".date3"); setdate(ds.nth(0), a); setdate(ds.nth(1), z)
        page.click("text=إضافة إجازة"); setdate(page.locator(".list-row").nth(0).locator(".date3").nth(0), "2026-10-06")
        page.locator(".list-row").nth(0).locator("input[type=text]").fill("عيد القوات المسلحة")
        shot("06_calendar"); page.click(".wiz-foot .btn.primary")
        page.wait_for_selector("text=كل شيء جاهز"); shot("07_done")
        page.click("text=الذهاب إلى اليوم")
        page.wait_for_selector(".shell"); page.wait_for_selector(".week-badge"); shot("08_today_ar")
        print("badge:", page.inner_text(".week-badge"))
        page.wait_for_timeout(700); shot("08_today_ar")
        ys = page.evaluate("(() => { if (!document.querySelector('.slot-time b')) return [0, 1]; const b = document.querySelector('.slot-time b'), sp = document.querySelector('.slot-time span'); return [b.getBoundingClientRect().y, sp.getBoundingClientRect().y] })()")
        assert ys[0] < ys[1], f"start time must be shown above the end time: {ys}"

        # pages
        for name, sel in (("classes", ".split"), ("timetable", "table.grid"), ("calendar", "table.weeks"), ("settings", ".seg"), ("help", "details.help")):
            page.click(f".nav a[data-page={name}]"); page.wait_for_selector(sel); page.wait_for_timeout(250); shot(f"09_{name}_ar")
        # AI: set up the "other" service pointing at the fake, test it, then use it on the documents page
        page.click(".nav a[data-page=settings]"); page.click(".seg-btn[data-tab=ai]"); page.wait_for_selector(".ai-grid")
        page.click(".ai-card >> nth=-1"); page.fill(".ai-detail input[type=password]", "test-key")
        page.fill(".ai-detail input[placeholder='https://.../v1']", FAKE_URL); pass
        page.click("text=اختبار الاتصال"); page.wait_for_selector(".ai-detail .banner.ok"); shot("09b_ai_ok")
        page.click(".ai-detail .btn.primary"); page.wait_for_selector(".ai-badge")
        assert "test-key" not in page.content()
        # documents + tasks
        os.environ["DLIS_NO_OPEN"] = "1"
        page.click(".nav a[data-page=docs]"); page.wait_for_selector(".pick-row"); page.wait_for_timeout(300)
        tab = lambda n: page.click(f".seg-btn[data-tab={n}]")
        P = ".panel:not(.sticky-pick):visible"
        tab("wk"); page.wait_for_selector(".wk-grid")
        for el in page.locator(".wk-grid input[type=text]").all(): el.fill("Hardware")
        page.click("text=جهّز كل حاجة"); page.wait_for_selector("text=خلصت:", timeout=60000); shot("15a_week")
        assert page.locator(".wk-line.err").count() == 0, page.inner_text(".wk-out")
        tab("lp"); page.fill(f"{P} input[type=text] >> nth=0", "Hardware")
        page.click(f"{P} >> text=اكتب بالذكاء الاصطناعي"); page.wait_for_function("document.querySelector('textarea').value.includes('Name parts')")
        page.click(f"{P} >> text=إنشاء خطة الدرس"); page.wait_for_selector(".banner.ok"); shot("15_docs_lp")
        tab("quiz"); page.fill(f"{P} .ai-bar input[type=text] >> nth=0", "Computers"); page.click(f"{P} >> text=اكتب بالذكاء الاصطناعي")
        page.wait_for_function("document.querySelector(\"textarea[rows='9']\").value.includes('CPU')"); shot("15b_ai_docs")
        page.fill("textarea[rows='9']", "1. What is a CPU?\na) Brain\nb) Screen\nAnswer: a")
        page.click("text=إنشاء الاختبار"); page.wait_for_selector("text=الملف جاهز"); shot("16_docs_quiz")
        tab("rv"); page.fill("input[placeholder='موضوع (أو مواضيع) المراجعة']", "Hardware"); page.click(f"{P} .ai-bar .btn")
        page.wait_for_function("[...document.querySelectorAll('textarea')].some(t => t.value === 'CPU: the brain')")
        page.click("text=اعمل ملف المراجعة"); page.wait_for_selector("text=Revision_Sheet"); shot("16b_docs_revision")
        tab("gs"); page.click("text=إنشاء كشف الدرجات"); page.wait_for_selector("text=الملف جاهز")
        tab("tp"); page.click("text=إنشاء خطة الفصل الدراسي"); page.wait_for_selector("text=الملف جاهز")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".plan-line"); page.click("text=ورقة للمدرس البديل"); page.wait_for_selector("text=Cover_Sheet"); shot("08c_today_plan")
        page.click(".nav a[data-page=tasks]"); page.wait_for_selector(".task-add")
        page.fill(".task-add input[type=text]", "طباعة الاختبارات"); page.select_option(".task-add select", "high"); setdate(page.locator(".task-add .date3"), "2026-10-20")
        page.click(".task-add .btn.primary"); page.wait_for_selector(".tasks-table tr:not(.auto) td b >> text=طباعة الاختبارات"); shot("17_tasks")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks .tasks-table"); shot("17b_today_tasks")
        # lesson log: log the first lesson, see "last time" + the reminder on Today, then the log page
        page.click(".lesson .btn >> text=سجّل الحصة >> nth=0"); page.fill(".modal input[type=text] >> nth=0", "Hardware")
        page.fill(".modal input[type=number] >> nth=0", "12"); page.fill(".modal input[type=number] >> nth=1", "30"); page.fill(".modal input[type=text] >> nth=1", "ابدأ بكويز")
        page.click(".modal footer .btn.primary"); page.wait_for_selector(".last-log .remember"); page.wait_for_selector("text=عدّل التسجيل"); shot("17g_log_today")
        page.click(".nav a[data-page=classes]"); page.click("a.seg-btn[href='#/log']"); page.wait_for_selector(".tasks-table td >> text=Hardware"); shot("17h_log_page")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks")
        # one-day changes on Today: cancel + undo, then a cover lesson, then back to normal
        page.wait_for_selector(".lesson .btn >> text=إلغاء النهارده"); n0 = page.locator(".lesson:not(.cancelled)").count()
        page.click(".lesson .btn >> text=إلغاء النهارده >> nth=0"); page.wait_for_selector(".lesson.cancelled")
        assert page.locator(".lesson:not(.cancelled)").count() == n0 - 1; shot("17e_cancelled")
        page.click(".lesson.cancelled >> text=رجّعها"); page.wait_for_function("!document.querySelector('.lesson.cancelled')")
        page.click("text=حصة تغطية"); page.fill(".modal input[type=text]", "المدرس غايب"); page.click(".modal footer .btn.primary")
        page.wait_for_selector(".kind.cover"); shot("17f_cover")
        page.click("text=رجّع الجدول العادي"); page.wait_for_function("!document.querySelector('.kind.cover')")
        assert page.locator(".lesson:not(.cancelled)").count() == n0
        # what was typed survives switching tabs
        page.click(".nav a[data-page=docs]"); page.click(".seg-btn[data-tab=lp]"); page.wait_for_selector(".panel textarea")
        page.fill("textarea >> nth=0", "مسودة مهمة"); page.fill(".panel:not(.sticky-pick):visible input[type=text] >> nth=0", "Topic X")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks")
        page.click(".nav a[data-page=docs]"); page.click(".seg-btn[data-tab=lp]"); page.wait_for_selector(".panel textarea")
        page.wait_for_function("document.querySelector('.panel textarea') && document.querySelector('.panel textarea').value === 'مسودة مهمة'")
        assert page.input_value("textarea >> nth=0") == "مسودة مهمة" and page.input_value(".panel:not(.sticky-pick):visible input[type=text] >> nth=0") == "Topic X"
        # AI chat: prompt helper fills the box, send, answer shows, history survives a tab change; prompts editable
        page.click(".nav a[data-page=chat]"); page.wait_for_selector(".chat-log"); 
        page.click(".chat-tool >> text=طلبات جاهزة"); page.click(".chip >> text=اشرح فكرة ببساطة"); page.fill(".chat-tray input[type=text]", "input devices")
        assert "input devices" in page.input_value(".chat-input"), "builder did not fill"
        page.fill(".chat-input", "Explain input devices. Sara is confused"); page.press(".chat-input", "Shift+Enter")
        assert page.input_value(".chat-input").endswith("\n"), "Shift+Enter must add a new line"
        page.press(".chat-input", "Enter")
        page.wait_for_selector(".bubble.assistant:not(.muted)"); shot("17i_chat")
        # parent message: the AI writes [student], the app puts the name in (never sent to the AI)
        page.click(".chat-tool >> text=رسالة لولي أمر"); page.wait_for_function("document.querySelectorAll('.chat-tray select option').length > 3")
        page.select_option(".chat-tray select >> nth=1", index=2); n0 = page.locator(".bubble.user").count()
        page.click("text=اكتب الرسالة"); page.wait_for_function(f"document.querySelectorAll('.bubble.user').length > {n0}")
        page.wait_for_selector("text=حط الاسم وانسخ")
        sent_ok = page.evaluate("[...document.querySelectorAll('.bubble.user')].pop().textContent.includes('[student]')"); assert sent_ok
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks"); page.click(".nav a[data-page=chat]")
        page.wait_for_selector(".bubble.user"); assert page.locator(".bubble").count() == 4
        # history: the chat was saved; a new chat starts empty, the old one opens again from the list
        page.wait_for_selector(".chat-item.on"); page.click(".chat-new"); assert page.locator(".bubble").count() == 0
        page.click(".chat-item >> nth=0"); page.wait_for_function("document.querySelectorAll('.bubble').length == 4"); shot("17i_chat_hist")
        page.click(".nav a[data-page=docs]"); page.click(".seg-btn[data-tab=ai]"); page.fill(".panel:visible textarea >> nth=0", "You are a pirate."); page.click("text=احفظ نسختي"); page.wait_for_selector("text=بتستخدم نسختك")
        page.click("text=ارجع للافتراضي"); page.wait_for_selector("text=بتستخدم الافتراضي"); page.click(".seg-btn[data-tab=lp]")
        # slides: NotebookLM prompt from a typed topic, then the AI source text
        page.click(".nav a[data-page=slides]"); page.wait_for_selector(".panel .btn.primary >> text=اكتب البرومبت")
        page.fill("input[placeholder='موضوع الدرس']", "Input devices"); page.click(".btn.primary >> text=اكتب البرومبت")
        page.wait_for_function("document.querySelector('textarea[dir=ltr]').value.includes('Input devices')"); shot("17j_slides")
        assert "10 slides" in page.input_value("textarea[dir=ltr]")
        page.click("text=اكتب نص المصدر بالـ AI"); page.wait_for_function("[...document.querySelectorAll('textarea')].some(t => t.value === 'ready')")
        # slides built here: AI plan -> editable cards -> PowerPoint file
        page.click(".panel .btn.primary >> text=خطّط السلايدز بالـ AI"); page.wait_for_selector(".slide-card")
        assert page.locator(".slide-card").count() == 2
        page.fill(".slide-card >> nth=0 >> input[type=text]", "What we will learn"); page.click("text=أضف سلايد"); assert page.locator(".slide-card").count() == 3
        shot("17k_slide_editor")
        page.click("text=اعمل ملف PowerPoint"); page.wait_for_selector("text=ملف PowerPoint جاهز")
        # weekly checklist: click a cell to change its state (not yet -> done)
        page.click(".nav a[data-page=tasks]"); page.wait_for_selector("table.wc")
        page.click("table.wc .wc-cell >> nth=0"); page.wait_for_selector("table.wc .wc-cell.done"); shot("17n_weekly")
        # my slides: import an image-only PDF, the app reads it with the (fake) vision AI, then the revision page can use it
        from PIL import Image as _I
        _I.new("RGB", (800, 450), (240, 240, 250)).save("/tmp/nlm.pdf", "PDF")
        page.click(".nav a[data-page=slides]"); page.click("a.seg-btn[href='#/sources']"); page.wait_for_selector("text=أضف مصدر")
        page.set_input_files("input[type=file]", "/tmp/nlm.pdf"); page.wait_for_selector(".src-card >> text=Input devices", timeout=20000); shot("17m_sources")
        page.click(".nav a[data-page=docs]"); page.click(".seg-btn[data-tab=rv]"); page.wait_for_selector(".src-pick select >> visible=true")
        page.select_option(".panel:has(h3:text('ملف المراجعة')) .src-pick select", label=re.compile(r'nlm')) if False else page.select_option(".panel:has(h3:text('ملف المراجعة')) .src-pick select", value=page.eval_on_selector(".panel:has(h3:text('ملف المراجعة')) .src-pick select", "s => [...s.options].find(o => o.textContent.includes('nlm')).value")); page.click("text=املا من سلايداتي")
        page.wait_for_function("[...document.querySelectorAll('textarea')].some(t => t.value === 'Mouse: points and clicks')")
        # school map: add floor + room, name it with a phone, drag, then view it
        page.click(".nav a[data-page=map]"); page.wait_for_selector(".bld"); page.locator(".bld").screenshot(path=str(SHOTS / "17k_building.png")); page.click("text=تعديل الخريطة")
        page.click("text=أضف دور"); page.click(".map-side >> text=أضف غرفة"); page.wait_for_selector(".map-room.sel")
        page.fill(".map-side input[type=text] >> nth=1", "Principal office"); page.select_option(".map-side select >> nth=0", "admin"); page.fill(".map-side input[dir=ltr]", "0100 555 1234")
        box = page.locator(".map-room.sel").bounding_box(); page.mouse.move(box["x"] + 20, box["y"] + 20); page.mouse.down(); page.mouse.move(box["x"] + 220, box["y"] + 90, steps=5); page.mouse.up()
        page.wait_for_timeout(700); page.click("text=تعديل الخريطة"); page.click(".bld-room >> text=Principal office"); page.wait_for_selector("a[href='tel:01005551234']"); shot("17l_map")
        page.reload(); page.wait_for_selector(".nav"); page.click(".nav a[data-page=map]"); page.wait_for_selector(".bld-room >> text=Principal office")
        # layout: sidebar fills the window height, and every page scrolls inside itself
        page.set_viewport_size({"width": 1280, "height": 500})
        for name in ("today", "classes", "docs", "chat", "slides", "map", "tasks", "settings"):
            page.click(f".nav a[data-page={name}]"); page.wait_for_timeout(500)
            m = page.evaluate("(() => { const m = document.querySelector('.main'), s = document.querySelector('.side'); m.scrollTop = 0; return {side: s.getBoundingClientRect().height, win: innerHeight, sh: m.scrollHeight, ch: m.clientHeight, doc: document.documentElement.scrollHeight} })()")
            assert abs(m["side"] - m["win"]) < 2, (name, m)
            assert m["doc"] <= m["win"] + 1, (name, m)
            if m["sh"] > m["ch"] + 5:
                page.mouse.move(700, 300); page.mouse.wheel(0, 400); page.wait_for_timeout(250)
                assert page.evaluate("document.querySelector('.main').scrollTop") > 0, name
        page.set_viewport_size({"width": 1280, "height": 860})
        # tour: a picture of every page and tab (Arabic), tall window so nothing is cut
        if os.environ.get("TOUR"):
            TD = Path(os.environ["TOUR"]); TD.mkdir(exist_ok=True, parents=True); page.set_viewport_size({"width": 1280, "height": 1500}); n = [0]
            def snap(name):
                n[0] += 1; page.wait_for_timeout(600); page.screenshot(path=str(TD / f"{n[0]:02d}_{name}.png"))
            go = lambda p_: (page.click(f".nav a[data-page={p_}]"), page.wait_for_timeout(500))
            go("today"); snap("today")
            go("timetable"); snap("timetable")
            go("calendar"); snap("calendar")
            go("tasks"); snap("tasks")
            page.click("a.seg-btn[href='#/reminders']"); snap("tasks_new_reminder")
            go("classes"); page.click("a.seg-btn[href='#/log']"); snap("classes_lesson_log")
            go("docs")
            for tab_ in ("wk", "lp", "quiz", "rv", "gs", "tp", "ai"):
                page.click(f".seg-btn[data-tab={tab_}]"); snap(f"files_{tab_}")
            go("slides"); snap("slides")
            page.click("a.seg-btn[href='#/sources']"); snap("slides_my_slides")
            go("chat"); snap("chat")
            page.click(".chat-tool >> nth=0"); snap("chat_ready_requests")
            go("classes"); snap("classes")
            go("map"); snap("map_building")
            go("settings")
            for tab_ in ("me", "data", "ai", "rem"):
                page.click(f".seg-btn[data-tab={tab_}]"); snap(f"settings_{tab_}")
            go("help"); snap("help")
            page.set_viewport_size({"width": 1280, "height": 860})
        # reminders: the test button shows a pop-up
        page.click(".nav a[data-page=settings]"); page.click(".seg-btn[data-tab=rem]"); page.wait_for_selector("text=جرّب تنبيه"); page.click("text=جرّب تنبيه")
        page.wait_for_selector(".reminder"); shot("17c_reminder"); page.click(".reminder >> text=تمام")
        page.click(".nav a[data-page=tasks]"); page.click("a.seg-btn[href='#/reminders']"); page.wait_for_selector(".alarm-add")
        page.fill(".alarm-add input[type=text]", "اطبع الكويز"); assert page.locator(".alarm-add .time12 select").count() == 3  # 12-hour picker, 8:00 AM by default
        page.click(".panel:has(.alarm-add) >> text=إضافة"); page.wait_for_selector("text=اطبع الكويز"); shot("17d_alarms"); page.wait_for_selector(".toast", state="detached", timeout=15000)
        page.click("text=كل الأحد") if False else None

        # students: paste a list
        page.click(".nav a[data-page=classes]"); page.wait_for_selector(".students, .banner.info")
        page.click("text=لصق أو استيراد قائمة"); page.fill(".modal textarea", "الاسم\n1. أحمد علي\n2. سارة محمد\n3. أحمد علي\nOmar Hany")
        page.wait_for_selector(".banner.ok"); shot("10_import"); page.click(".modal footer .btn.primary")
        page.wait_for_selector(".students li"); assert page.locator(".students li").count() == 17, page.locator(".students li").count()  # 14 built-in KG1 A + 3 pasted
        page.wait_for_selector("text=تم الحفظ"); shot("11_students")
        # reload: data persists and the app opens straight to the shell
        page.goto(url); page.wait_for_selector(".shell"); page.click(".nav a[data-page=classes]"); page.wait_for_selector(".students li")
        assert page.locator(".students li").count() == 17
        # english + unsaved-changes guard
        page.click(".nav a[data-page=settings]"); page.click(".seg-btn[data-tab=me]"); page.wait_for_selector("button[lang=en]"); page.click("button[lang=en]")
        page.wait_for_selector("text=Settings"); assert page.evaluate("document.documentElement.dir") == "ltr"
        page.click(".nav a[data-page=timetable]"); page.wait_for_selector("table.grid")
        page.locator("table.grid tbody select").nth(2).select_option(index=1)
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".overlay"); shot("12_unsaved_guard")
        page.click(".modal footer .btn >> nth=0")  # cancel -> stay
        assert page.locator("table.grid").count() == 1
        page.click(".nav a[data-page=timetable]") if False else None
        page.click("text=Save"); page.wait_for_selector(".toast.ok")
        for name, sel in (("today", ".week-badge"), ("classes", ".split"), ("calendar", "table.weeks")):
            page.click(f".nav a[data-page={name}]"); page.wait_for_selector(sel); page.wait_for_timeout(250); shot(f"13_{name}_en")
        if os.environ.get("SWEEP"):  # English layout check: report anything that sticks out of its box
            JS = """() => { const out = []; for (const el of document.querySelectorAll('#main *, .nav *')) {
              const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue; const cs = getComputedStyle(el);
              const p = el.parentElement; if (!p) continue; const pr = p.getBoundingClientRect(); const pcs = getComputedStyle(p);
              const clipped = el.scrollWidth > el.clientWidth + 2 && cs.overflowX === 'visible' && el.children.length === 0 && el.textContent.trim().length > 0;
              const outside = (r.right > pr.right + 2 || r.left < pr.left - 2) && pcs.overflowX === 'visible' && cs.position !== 'absolute' && cs.position !== 'fixed' && pr.width > 0;
              if (clipped || outside) out.push((el.tagName + '.' + el.className).slice(0, 50) + ' | ' + el.textContent.trim().slice(0, 40) + ' | ' + Math.round(r.width) + ' vs ' + Math.round(pr.width)); }
              return out.slice(0, 12); }"""
            for route in ("today", "timetable", "calendar", "tasks", "docs", "slides", "sources", "chat", "classes", "log", "map", "settings", "help"):
                page.evaluate(f"location.hash = '#/{route}'"); page.wait_for_timeout(700)
                for r in page.evaluate(JS): print("SWEEP", route, "->", r)
                shot(f"14_{route}_en")
        # reminder timing (fake clock, Monday): lesson at 13:40 -> reminder at 13:31; lesson at 11:35 right after the break duty -> none
        import datetime as _dt
        mon = _dt.date(2026, 10, 28); mon -= _dt.timedelta(days=(mon.weekday() - 0) % 7)
        def at(h, m, day=None):
            day = day or mon
            pg = ctx.new_page(); pg.clock.install(time=_dt.datetime(day.year, day.month, day.day, h, m, 0)); pg.goto(url)
            pg.wait_for_selector(".shell"); pg.clock.run_for(5000); pg.wait_for_timeout(1500); pg.clock.run_for(25000); pg.wait_for_timeout(1500); return pg
        pg = at(13, 31); assert pg.locator(".reminder").count() == 1, "expected a reminder before the 13:40 lesson"; pg.close()
        pg = at(13, 45); pg.click(".nav a[data-page=today]"); pg.wait_for_selector(".slot[data-state=now]"); pg.screenshot(path="/tmp/shots/08b_today_now.png"); pg.close()
        pg = at(8, 1, _dt.date(2026, 10, 28)); assert pg.locator(".reminder:has-text('اطبع الكويز')").count() == 1, "own reminder should pop up"; pg.close()
        pg = at(11, 27); assert pg.locator(".reminder").count() == 0, "no reminder when coming straight from another duty"; pg.close()
        # phone width
        page.set_viewport_size({"width": 400, "height": 800}); page.click(".nav a[data-page=today]"); page.wait_for_timeout(300); shot("14_phone")
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        print("horizontal overflow on phone width:", overflow)
        b.close()
finally:
    proc.terminate()
print("data files:", sorted(x.name for x in data.glob("*")))
print("\n".join(errors) or "no console errors")
