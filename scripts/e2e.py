"""Drive the real app in a browser: whole first-run guide in Arabic, then every page, then English."""
import datetime as _dt, os, subprocess, sys, tempfile, re, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = Path(os.environ.get("SHOTS", str(Path(tempfile.gettempdir()) / "shots"))); SHOTS.mkdir(exist_ok=True, parents=True)
home = tempfile.mkdtemp(); data = Path(tempfile.mkdtemp()) / "My DLIS"
env = dict(os.environ, DLIS_APP_HOME=home, HOME=home, USERPROFILE=home, PYTHONUTF8="1")  # fake home so the folder picker is isolated (HOME on Mac/Linux, USERPROFILE on Windows)
(Path(home) / "Documents").mkdir()
# the server thinks it is a school day (Wed 28 Oct 2026), so the screens do not depend on the weekday the test runs on
_fake = Path(tempfile.mkdtemp()); (_fake / "sitecustomize.py").write_text(
    "import datetime as _d\nclass date(_d.date):\n    @classmethod\n    def today(cls):\n        return cls(2026, 10, 28)\n_d.date = date\n")
env["PYTHONPATH"] = str(_fake)
proc = subprocess.Popen([sys.executable, "-m", "app", "--no-window"], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
url = proc.stdout.readline().strip()
print("server", url)
errors = []

inflight = {}   # requests the browser has sent and not heard back from yet: shown when a screen does not appear


def track(pg):
    pg.on("request", lambda r: inflight.__setitem__(r, time.time()))
    pg.on("requestfinished", lambda r: inflight.pop(r, None))
    pg.on("requestfailed", lambda r: inflight.pop(r, None))


def why_stuck(pg):
    """A screen did not appear (this has timed out a few times on Windows and once on Linux, never in the same place twice):
    say what the browser is still waiting for, whether the server still answers, and what the screen shows."""
    now = time.time()
    try:
        print("STUCK. requests still waiting:", [(r.method, r.url.split("/", 3)[-1][:70], round(now - t, 1)) for r, t in inflight.items()])
    except Exception as e:
        print("STUCK. could not list the requests:", e)
    t0 = time.time()
    try:
        print("server answers:", urllib.request.urlopen(url, timeout=8).status, f"in {time.time() - t0:.2f}s")
    except Exception as e:
        print("server does NOT answer within 8s:", repr(e))
    try:
        print("screen says:", pg.inner_text("body")[:300].replace("\n", " | "))
        print("pending in the page:", pg.evaluate("performance.getEntriesByType('resource').filter(r => r.responseEnd === 0).map(r => r.name)"))
    except Exception as e:
        print("could not read the screen:", e)
    print("console so far:", errors[-8:])


def wait_docs(page):
    """Wait for the Create page. This once timed out on one Linux run and never again; if it happens again, say what the page was
    showing and what the console said, so the cause can be found instead of guessed."""
    try:
        page.wait_for_selector("#main:not(.busy) .steps")
    except Exception:
        print("DOCS PAGE DID NOT APPEAR.")
        raise


def pick_kind(page, kind):
    """Create page is three steps: go to step 2 if needed, then press the card of the file kind."""
    if page.is_visible("[data-step-next]"):
        page.click("[data-step-next]")
    elif not page.is_visible(".opt[data-kind-opt]"):
        page.click(".steps .st:nth-child(2)")   # already on step 3 from last time: go back to the choice
    page.click(f".opt[data-kind-opt={kind}]")


def _open_group(page_):
    """The menu shows the pages of one group at a time: open the group of a page before clicking its link."""
    orig = page_.click
    def click(sel, *a, **k):
        m = re.match(r"\.nav a\[data-page=(\w+)\]$", sel)
        if m:
            page_.evaluate("(id) => { const l = document.querySelector(`.nav a[data-page=${id}]`); const g = l && l.dataset.group; const t = g && document.querySelector(`.tab[data-group=${g}]`); if (t) t.click(); }", m.group(1))
        return orig(sel, *a, **k)
    page_.click = click
    return page_


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
        if "DETAILS FROM THE TEACHER" in prompt: txt = "**Rubric** for [student]\nCriterion | Good | Weak\nClarity | 4 | 1"
        elif "multiple-choice" in prompt: txt = "1. What is a CPU?\na) Brain\nb) Screen\nAnswer: a\n\n2. Which is input?\na) Mouse\nb) Speaker\nAnswer: a"
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
        page = _open_group(ctx.new_page()); page.clock.install(time=_dt.datetime(2026, 10, 28, 9, 0, 0))
        track(page)
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
        page.wait_for_selector("text=هتشتغل إزاي"); shot("02c_account"); page.click("text=اشتغل من غير سيرفر")
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
        pill = page.locator(".slot-time").first
        if pill.count():
            assert re.search(r"\d", pill.inner_text()) and " – " in (pill.get_attribute("title") or ""), "the time on the line must show the start, with the whole range as its tooltip"

        # start-up hint on Today: the AI hint leads to the AI help section
        page.wait_for_selector(".banner:has-text('المساعد الذكي لسه مش شغال')"); shot("08b_today_hints")
        page.click(".banner >> text=إزاي أشغّله؟"); page.wait_for_selector("details.help[open]:has-text('الذكاء الاصطناعي')"); assert page.locator("details.help[open]").count() == 1
        page.click(".nav a[data-page=calendar]"); page.click(".nav a[data-page=today]"); page.wait_for_selector(".week-badge"); page.wait_for_timeout(500)
        # pages
        for name, sel in (("classes", ".split"), ("timetable", "table.grid"), ("calendar", ".wk-line"), ("settings", ".seg"), ("help", "details.help")):
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
        tab = lambda n: pick_kind(page, n)
        P = ".panel:not(.sticky-pick):visible"
        tab("wk"); page.wait_for_selector(".wk-grid")
        for el in page.locator(".wk-grid input[type=text]").all(): el.fill("Hardware")
        page.click("text=جهّز كل حاجة"); page.wait_for_selector("text=خلصت:", timeout=60000); shot("15a_week")
        assert page.locator(".wk-line.err").count() == 0, page.inner_text(".wk-out")
        tab("lp"); page.fill(f"{P} input[type=text] >> nth=0", "Hardware")
        page.click(f"{P} >> text=اكتب بالذكاء الاصطناعي"); page.wait_for_function("document.querySelector('textarea').value.includes('Name parts')")
        page.click(f"{P} >> text=إنشاء خطة الدرس"); page.wait_for_selector(".banner.ok:visible"); shot("15_docs_lp")
        tab("quiz"); page.fill(f"{P} .ai-bar input[type=text] >> nth=0", "Computers"); page.click(f"{P} >> text=اكتب بالذكاء الاصطناعي")
        page.wait_for_function("document.querySelector(\"textarea[rows='9']\").value.includes('CPU')"); shot("15b_ai_docs")
        page.fill("textarea[rows='9']", "1. What is a CPU?\na) Brain\nb) Screen\nAnswer: a")
        page.click("text=إنشاء الاختبار"); page.wait_for_selector("text=الملف جاهز"); shot("16_docs_quiz")
        page.click("button:has-text('ملف Moodle')"); page.wait_for_selector(".banner.ok:visible:has-text('Moodle.txt')"); page.click("button:has-text('Google Forms')"); page.wait_for_selector(".banner.ok:visible:has-text('GoogleForms.txt')")
        tab("rv"); page.fill("input[placeholder='موضوع (أو مواضيع) المراجعة']", "Hardware"); page.click(f"{P} .ai-bar .btn")
        page.wait_for_function("[...document.querySelectorAll('textarea')].some(t => t.value === 'CPU: the brain')")
        page.click("text=اعمل ملف المراجعة"); page.wait_for_selector("text=Revision_Sheet"); shot("16b_docs_revision")
        tab("gs"); page.click("text=إنشاء كشف الدرجات"); page.wait_for_selector("text=الملف جاهز")
        page.click(".nav a[data-page=scheme]"); page.wait_for_selector(".sw-card"); page.click("text=اعمل ملف Word للخطة"); page.wait_for_selector("text=الملف جاهز")
        page.fill(".sw-card input[placeholder='الوحدة 2'] >> nth=0", "Unit 2"); page.fill(".sw-card textarea >> nth=0", "Name the parts\nExplain the CPU"); page.click("button:has-text('حفظ')"); page.wait_for_timeout(600)
        page.reload(); page.wait_for_selector(".nav"); page.click(".nav a[data-page=scheme]"); page.wait_for_selector(".sw-card")
        assert page.input_value(".sw-card input[placeholder='الوحدة 2'] >> nth=0") == "Unit 2" and "Explain the CPU" in page.input_value(".sw-card textarea >> nth=0")
        page.evaluate("window.__cp = ''; navigator.clipboard.writeText = async (x) => { window.__cp = x; }")
        page.goto(page.url.split("#")[0] + "#/parentweek"); page.wait_for_selector("button:has-text('عربي')")
        page.fill("textarea >> nth=0", "صفحة 12"); page.click("button:has-text('عربي')"); page.wait_for_timeout(300)
        cp = page.evaluate("window.__cp"); assert "السلام عليكم" in cp and "صفحة 12" in cp, cp
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
        page.click("a.seg-btn[href='#/progress']"); page.wait_for_selector(".bar"); shot("17h2_progress")
        page.click("text=ملف التفتيش")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks")
        # one-day changes on Today: cancel + undo, then a cover lesson, then back to normal
        page.click(".lesson summary >> nth=0"); page.wait_for_selector(".lesson .menu-item >> text=إلغاء النهارده"); n0 = page.locator(".lesson:not(.cancelled)").count()
        page.click(".lesson .menu-item >> text=إلغاء النهارده >> nth=0"); page.wait_for_selector(".lesson.cancelled")
        assert page.locator(".lesson:not(.cancelled)").count() == n0 - 1; shot("17e_cancelled")
        page.click(".lesson.cancelled >> text=رجّعها"); page.wait_for_function("!document.querySelector('.lesson.cancelled')")
        page.click("text=حصة تغطية"); page.fill(".modal input[type=text]", "المدرس غايب"); page.click(".modal footer .btn.primary")
        page.wait_for_selector(".kind.cover"); shot("17f_cover")
        page.click("text=رجّع الجدول العادي"); page.wait_for_function("!document.querySelector('.kind.cover')")
        assert page.locator(".lesson:not(.cancelled)").count() == n0
        # what was typed survives switching tabs
        page.click(".nav a[data-page=docs]"); wait_docs(page); pick_kind(page, "lp"); page.wait_for_selector(".main .panel textarea >> visible=true")
        page.fill(".main .panel textarea >> visible=true >> nth=0", "مسودة مهمة"); page.fill(".panel:not(.sticky-pick):visible input[type=text] >> nth=0", "Topic X")
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".today-tasks")
        page.click(".nav a[data-page=docs]"); wait_docs(page); pick_kind(page, "lp"); page.wait_for_selector(".main .panel textarea >> visible=true")
        page.wait_for_function("[...document.querySelectorAll('.main .panel textarea')].some((x) => x.offsetParent && x.value === 'مسودة مهمة')")
        assert page.input_value(".main .panel textarea >> visible=true >> nth=0") == "مسودة مهمة" and page.input_value(".panel:not(.sticky-pick):visible input[type=text] >> nth=0") == "Topic X"
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
        page.click(".nav a[data-page=settings]"); page.click(".seg-btn[data-tab=ai]"); page.fill(".panel:visible textarea >> nth=0", "You are a pirate."); page.click("text=احفظ نسختي"); page.wait_for_selector("text=بتستخدم نسختك")
        page.click("text=ارجع للافتراضي"); page.wait_for_selector("text=بتستخدم الافتراضي")
        # slides: NotebookLM prompt from a typed topic, then the AI source text
        page.click(".nav a[data-page=docs]"); wait_docs(page); pick_kind(page, "sl"); page.wait_for_selector("details.fold summary >> visible=true")
        page.fill("input[placeholder='موضوع الدرس']", "Input devices"); page.click("details.fold summary >> visible=true"); page.click(".btn.primary >> text=اكتب البرومبت")
        page.wait_for_function("[...document.querySelectorAll('details.fold textarea[dir=ltr]')].some((x) => x.value.includes('Input devices'))"); shot("17j_slides")
        assert "10 slides" in page.input_value("details.fold textarea[dir=ltr] >> nth=0")
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
        _I.new("RGB", (800, 450), (240, 240, 250)).save(str(Path(tempfile.gettempdir()) / "nlm.pdf"), "PDF")
        page.click(".nav a[data-page=library]"); page.wait_for_selector("details.add-src")
        page.set_input_files("input[type=file]", str(Path(tempfile.gettempdir()) / "nlm.pdf")); page.wait_for_selector(".file-row:has-text('nlm'):has-text('Input devices')", timeout=20000); shot("17m_sources")
        page.click(".nav a[data-page=docs]"); wait_docs(page); pick_kind(page, "rv"); page.wait_for_selector(".src-pick select >> visible=true")
        page.select_option(".panel:has(h3:text('ملف المراجعة')) .src-pick select", label=re.compile(r'nlm')) if False else page.select_option(".panel:has(h3:text('ملف المراجعة')) .src-pick select", value=page.eval_on_selector(".panel:has(h3:text('ملف المراجعة')) .src-pick select", "s => [...s.options].find(o => o.textContent.includes('nlm')).value")); page.click("text=املا من سلايداتي")
        page.wait_for_function("[...document.querySelectorAll('textarea')].some(t => t.value === 'Mouse: points and clicks')")
        # certificates: a file for the whole class, in Arabic
        page.click(".nav a[data-page=docs]"); wait_docs(page); pick_kind(page, "ct")
        page.click("button:has-text('اعمل الملف')"); page.wait_for_selector(".banner.ok:visible:has-text('في الملف')", timeout=20000); shot("17o_certificates")
        # behaviour note, then a seat
        page.evaluate("location.hash='#/behavior'"); page.wait_for_selector("#main:not(.busy) .panel input[type=text]")
        page.fill(".panel input[type=text]", "مشاركة ممتازة"); page.keyboard.press("Enter"); page.wait_for_selector(".bh-note", timeout=10000); shot("17p_behavior")
        page.evaluate("location.hash='#/seating'"); page.wait_for_selector("#main:not(.busy) .seat")
        page.click(".st-pool .chip >> nth=0"); page.click(".seat >> nth=0"); page.wait_for_selector(".seat.full", timeout=10000); shot("17p_seating")
        # teacher tools: pick a tool, fill its form, the (fake) AI writes, save as Word; a student tool offers the name picker
        page.click(".nav a[data-page=docs]"); page.click("a.seg-btn[href='#/tools']"); page.wait_for_selector(".tl-form")
        page.select_option("select[aria-label='اختار الأداة']", "rubric")
        for el in page.locator(".tl-form input, .tl-form textarea").all(): el.fill("4" if el.get_attribute("type") == "number" else "Poster project")
        page.click("button:has-text('اكتبها')"); page.wait_for_function("document.querySelector('.tl-out').value.includes('Clarity')", timeout=20000)
        assert "**" not in page.input_value(".tl-out")
        page.click("button:has-text('احفظ كملف Word')"); page.wait_for_selector("text=الملف جاهز"); shot("17q_tools")
        page.select_option("select[aria-label='اختار الأداة']", "report_comment")
        for el in page.locator(".tl-form input, .tl-form textarea").all(): el.fill("4" if el.get_attribute("type") == "number" else "Works hard")
        page.click("button:has-text('اكتبها')"); page.wait_for_function("document.querySelector('.tl-out').value.includes('[student]')", timeout=20000)
        page.wait_for_selector("button:has-text('حط الاسم')"); page.wait_for_selector(".tl-form ~ * .banner.ok, .main .banner.ok", state="detached"); assert page.locator(".main a:has-text('شارك')").count() == 0, page.locator("a:has-text('شارك')").all_inner_texts()
        page.click(".nav a[data-page=docs]"); wait_docs(page); page.click("a.seg-btn[href='#/tools']"); page.wait_for_selector(".tl-form")
        assert "[student]" in page.input_value(".tl-out")      # what was written stays while visiting another page
        # quick search: Ctrl+K lists recent files and pages, finds a tool by its Arabic name and opens it, and finds a saved file
        page.keyboard.press("Control+k"); page.wait_for_selector(".quick-input"); page.wait_for_selector(".quick-item")
        assert page.locator(".quick-head").count() >= 1; shot("17r_quick")
        page.fill(".quick-input", "Rubric_1"); page.wait_for_selector(".quick-item .quick-kind:text-is('ملف')")
        page.fill(".quick-input", "سؤال نهايه"); page.wait_for_selector(".quick-item .quick-kind:text-is('أداة')"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector(\"select[aria-label='اختار الأداة']\") && document.querySelector(\"select[aria-label='اختار الأداة']\").value === 'exit_ticket'", timeout=10000)
        assert page.locator(".quick-input").count() == 0
        page.click(".quick-btn"); page.wait_for_selector(".quick-input"); page.keyboard.press("Escape"); assert page.locator(".quick-input").count() == 0
        page.click(".nav a[data-page=chat]"); page.wait_for_selector(".chat-log"); page.click(".chat-tool[data-tray=source]"); page.wait_for_selector(".chat-tray .src-pick select >> visible=true")
        page.select_option(".chat-tray .src-pick select", index=1); page.wait_for_selector(".chat-tool.has")
        # marks: full mark for everyone except the absent, saved by itself, kept after a reload; no server login -> a hint instead of the upload button
        page.click(".nav a[data-page=classes]"); page.wait_for_selector(".split"); page.click("a.seg-btn[href='#/grades']"); page.wait_for_selector(".gr-table tbody tr")
        page.locator(".gr-table tbody tr >> nth=1").locator("input[type=checkbox]").check()
        page.click("button:has-text('الدرجة الكاملة للكل')"); page.wait_for_selector("text=اتحفظ", timeout=10000)
        assert page.locator(".gr-table tbody tr >> nth=0").locator("input.gr-in >> nth=0").input_value() == "10"
        assert page.locator(".gr-table tbody tr >> nth=1").locator("input.gr-in >> nth=0").input_value() == ""
        assert page.locator(".gr-table tbody tr >> nth=0").locator("input.gr-in >> nth=4").input_value() == ""       # the quiz part is not filled by default
        page.locator(".gr-table tbody tr >> nth=0").locator("input.gr-in >> nth=4").fill("18"); page.wait_for_selector("text=اتحفظ", timeout=10000); shot("17s_grades")
        page.reload(); page.wait_for_selector(".nav"); page.click(".nav a[data-page=classes]"); page.click("a.seg-btn[href='#/grades']"); page.wait_for_selector(".gr-table tbody tr")
        assert page.locator(".gr-table tbody tr >> nth=0").locator("input.gr-in >> nth=4").input_value() == "18"
        assert page.locator(".gr-table tbody tr >> nth=1").locator("input[type=checkbox]").is_checked()
        page.wait_for_selector("text=سجّل دخول سيرفر المدرسة")
        page.click("a.seg-btn[href='#/insights']"); page.wait_for_selector(".bar-col"); assert "%" in page.inner_text(".kpi-v >> nth=0"); shot("17t_insights")
        assert page.locator("text=غايب 1 أسابيع").count() == 0 and page.locator(".bar-col").count() >= 1
        # school map: add floor + room, name it with a phone, drag, then view it
        page.click(".nav a[data-page=map]"); page.wait_for_selector(".bld3 .bld3-room"); page.locator(".bld3-wrap").screenshot(path=str(SHOTS / "17k_building.png"))
        page.click(".bld3-room:has-text(\"مكتب المدير\")"); page.click("text=تعديل الخريطة")
        page.click(".map-side .btn:has-text('الجناح الشمال')"); page.wait_for_selector(".bld3-room.sel")
        page.fill(".map-side input[type=text] >> nth=1", "Test office"); page.select_option(".map-side select >> nth=0", "admin"); page.fill(".map-side input[dir=ltr]", "0100 555 1234")
        page.click(".map-side >> text=قبل"); page.wait_for_timeout(700); page.click("text=تعديل الخريطة"); page.click(".bld3-room:has-text('Test office')"); page.wait_for_selector("a[href='tel:01005551234']"); shot("17l_map")
        page.reload(); page.wait_for_selector(".nav"); page.click(".nav a[data-page=map]"); page.wait_for_selector(".bld3-room:has-text('Test office')")
        # layout: sidebar fills the window height, and every page scrolls inside itself
        page.set_viewport_size({"width": 1280, "height": 500})
        for name in ("today", "classes", "docs", "scheme", "library", "chat", "map", "tasks", "settings"):
            page.click(f".nav a[data-page={name}]"); page.wait_for_timeout(500)
            m = page.evaluate("(() => { const m = document.querySelector('.main'), s = document.querySelector('.shell'); m.scrollTop = 0; return {side: s.getBoundingClientRect().height, win: innerHeight, sh: m.scrollHeight, ch: m.clientHeight, doc: document.documentElement.scrollHeight} })()")
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
            for tab_ in ("wk", "lp", "quiz", "rv", "sl", "gs", "ct"):
                pick_kind(page, tab_); snap(f"files_{tab_}")
            go("library"); snap("library_files")
            assert page.locator(".wk-group").count() >= 1 and page.locator(".file-note").count() >= 1   # files sit in weeks, each with a note for the students
            page.click("text=الأسابيع >> nth=0"); page.wait_for_selector(".modal select"); page.click(".modal header .btn.icon")
            page.click("details.add-src > summary"); page.fill(".add-src input[type=url]", "https://www.youtube.com/playlist?list=PL1"); page.fill(".add-src input[maxlength='120']", "بلاي ليست")
            page.click("text=ضيف الرابط"); page.wait_for_selector(".file-row:has-text('بلاي ليست') .file-note")   # a link is a file too: note, week, for-students tick
            go("scheme"); page.wait_for_selector(".sw-card"); snap("scheme")
            go("library"); page.wait_for_selector(".banner.info"); snap("library")
            go("docs"); page.click("a.seg-btn[href='#/tools']"); page.wait_for_selector(".tl-form"); snap("tools")
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
        page.click(".panel:has(.alarm-add) >> text=إضافة"); page.wait_for_selector("text=اطبع الكويز"); shot("17d_alarms")
        assert "هيرن بعد" in page.locator(".toast").inner_text() or "عدّى" in page.locator(".toast").inner_text()   # says how long until it rings
        page.wait_for_selector(".toast", state="detached", timeout=15000)
        page.click("tr:has-text('اطبع الكويز') button[aria-label='تعديل']"); page.fill(".alarm-add input[type=text]", "اطبع الكويز الثاني"); page.click("text=احفظ التعديل")
        page.wait_for_selector("text=اطبع الكويز الثاني"); page.wait_for_selector(".toast", state="detached", timeout=15000)
        # no name: it says so instead of doing nothing
        page.fill(".alarm-add input[type=text]", ""); page.click(".panel:has(.alarm-add) >> text=إضافة")
        page.wait_for_selector(".toast.warn:has-text('اسم التنبيه')"); assert page.locator(".alarm-add input.bad").count() == 1
        # a one-time reminder in the past is shown as finished (not ticked), apart from the active ones
        page.evaluate("""async () => { const tok = document.querySelector('meta[name=dlis-token]').content;
          const post = (b) => fetch('/api/alarms', { method: 'POST', headers: { 'X-DLIS-Token': tok, 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
          await post({ text: 'تنبيه قديم', time: '08:00', days: [], date: '2020-01-01' });
          await post({ text: 'تنبيه للحذف', time: '08:00', days: [], date: '2099-01-01' }); }""")
        page.reload(); page.wait_for_selector(".alarm-add")
        assert page.locator(".alarm-row.done:has-text('تنبيه قديم')").count() == 1 and page.locator(".alarm-row.done input:checked").count() == 0
        assert page.locator(".alarm-row.on:has-text('تنبيه للحذف')").count() == 1 and page.locator("text=امسح المنتهية").count() == 1
        # deleting the reminder that is open for editing closes the form
        page.click("tr:has-text('تنبيه للحذف') button[aria-label='تعديل']"); page.wait_for_selector(".alarm-form.editing")
        page.click("tr:has-text('تنبيه للحذف') button[aria-label='حذف']"); page.wait_for_selector("tr:has-text('تنبيه للحذف')", state="detached")
        assert page.locator(".alarm-form.editing").count() == 0 and page.input_value(".alarm-add input[type=text]") == ""

        # students: paste a list
        page.click(".nav a[data-page=classes]"); page.wait_for_selector(".students, .banner.info")
        page.click("text=لصق أو استيراد قائمة"); page.fill(".modal textarea", "الاسم\n1. أحمد علي\n2. سارة محمد\n3. أحمد علي\nOmar Hany")
        page.wait_for_selector(".banner.ok"); shot("10_import"); page.click(".modal footer .btn.primary")
        page.wait_for_selector(".students li"); assert page.locator(".students li").count() == 17, page.locator(".students li").count()  # 14 built-in KG1 A + 3 pasted
        page.wait_for_selector("text=تم الحفظ"); shot("11_students")
        # reload: data persists and the app opens straight to the shell
        page.goto(url); page.wait_for_selector(".shell"); page.click(".nav a[data-page=classes]"); page.wait_for_selector(".students li")
        page.wait_for_function("document.querySelectorAll('.students li').length === 17", timeout=15000)
        assert page.locator(".students li").count() == 17, page.locator(".students li").count()
        # english + unsaved-changes guard
        page.click(".nav a[data-page=settings]"); page.click(".seg-btn[data-tab=me]"); page.wait_for_selector("button[lang=en]"); page.click("button[lang=en]")
        page.wait_for_selector(".tab:has-text('My day')"); assert page.evaluate("document.documentElement.dir") == "ltr"
        page.click(".nav a[data-page=timetable]"); page.wait_for_selector("table.grid")
        page.locator("table.grid tbody select").nth(2).select_option(index=1)
        page.click(".nav a[data-page=today]"); page.wait_for_selector(".overlay"); shot("12_unsaved_guard")
        page.click(".modal footer .btn >> nth=0")  # cancel -> stay
        assert page.locator("table.grid").count() == 1
        page.click(".nav a[data-page=timetable]") if False else None
        page.click("text=Save"); page.wait_for_selector(".toast.ok")
        for name, sel in (("today", ".week-badge"), ("classes", ".split"), ("calendar", ".wk-line")):
            page.click(f".nav a[data-page={name}]"); page.wait_for_selector(sel); page.wait_for_timeout(250); shot(f"13_{name}_en")
        if os.environ.get("SWEEP"):  # English layout check: report anything that sticks out of its box
            JS = """() => { const out = []; for (const el of document.querySelectorAll('#main *, .nav *')) {
              const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue; const cs = getComputedStyle(el);
              const p = el.parentElement; if (!p) continue; const pr = p.getBoundingClientRect(); const pcs = getComputedStyle(p);
              const clipped = el.scrollWidth > el.clientWidth + 2 && cs.overflowX === 'visible' && el.children.length === 0 && !(el instanceof SVGElement) && el.textContent.trim().length > 0;
              const outside = (r.right > pr.right + 2 || r.left < pr.left - 2) && pcs.overflowX === 'visible' && cs.position !== 'absolute' && cs.position !== 'fixed' && pr.width > 0;
              if (clipped || outside) out.push((el.tagName + '.' + el.className).slice(0, 50) + ' | ' + el.textContent.trim().slice(0, 40) + ' | ' + Math.round(r.width) + ' vs ' + Math.round(pr.width) + ' in ' + p.tagName + '.' + p.className + ' ws=' + pcs.whiteSpace + ' disp=' + pcs.display + ' kids=' + [...p.children].map(k => Math.round(k.getBoundingClientRect().width) + '@' + Math.round(k.getBoundingClientRect().left)).join(',') + ' td@' + Math.round(pr.left) + ' pad=' + pcs.paddingLeft + '/' + pcs.paddingRight + ' minw=' + pcs.minWidth); }
              return out.slice(0, 12); }"""
            for route in ("today", "timetable", "calendar", "tasks", "docs", "scheme", "tools", "library", "chat", "classes", "log", "progress", "parentweek", "map", "settings", "help"):
                page.evaluate(f"location.hash = '#/{route}'"); page.wait_for_timeout(700)
                for r in page.evaluate(JS): print("SWEEP", route, "->", r)
                shot(f"14_{route}_en")
        # reminder timing (fake clock, Monday): lesson at 13:40 -> reminder at 13:31; lesson at 11:35 right after the break duty -> none
        import datetime as _dt
        mon = _dt.date(2026, 10, 28); mon -= _dt.timedelta(days=(mon.weekday() - 0) % 7)
        def at(h, m, day=None):
            day = day or mon
            pg = _open_group(ctx.new_page()); pg.clock.install(time=_dt.datetime(day.year, day.month, day.day, h, m, 0)); pg.goto(url)
            pg.wait_for_selector(".shell"); pg.clock.run_for(5000); pg.wait_for_timeout(1500); pg.clock.run_for(25000); pg.wait_for_timeout(1500); return pg
        pg = at(13, 31); assert pg.locator(".reminder").count() >= 1, "expected a reminder before the 13:40 lesson"; assert pg.locator(".reminder:has-text('Prayer')").count() == 1, "expected the prayer-break reminder"; pg.close()
        pg = at(13, 45); pg.click(".nav a[data-page=today]"); pg.wait_for_selector(".slot[data-state=now]"); pg.screenshot(path=str(SHOTS / "08b_today_now.png")); pg.close()
        pg = at(8, 1, _dt.date(2026, 10, 28)); assert pg.locator(".reminder:has-text('اطبع الكويز')").count() == 1, "own reminder should pop up"; pg.close()
        pg = at(13, 5, _dt.date(2026, 11, 1)); assert pg.locator(".reminder:has-text('Cultural Diversity')").count() == 1, "the day before an event a reminder should pop up"; pg.close()
        pg = at(11, 0, _dt.date(2026, 11, 1)); assert pg.locator(".reminder:has-text('Cultural Diversity')").count() == 0, "not before the chosen time"; pg.close()
        pg = at(19, 5, _dt.date(2026, 11, 1)); assert pg.locator(".reminder:has-text('Tomorrow you have')").count() == 1, ("the evening before a school day: prepare-tomorrow alert", pg.evaluate("fetch('/api/tomorrow?date=2026-11-01').then(r => r.text())"), pg.locator(".reminder").all_inner_texts()); shot_ = pg.screenshot(path=str(SHOTS / "08c_tomorrow.png")); pg.close()
        pg = at(18, 0, _dt.date(2026, 11, 1)); assert pg.locator(".reminder:has-text('Tomorrow you have')").count() == 0, "not before the evening time"; pg.close()
        pg = at(11, 27); assert pg.locator(".reminder").count() == 0, "no reminder when coming straight from another duty"; pg.close()
        # phone width
        page.set_viewport_size({"width": 400, "height": 800}); page.click(".nav a[data-page=today]"); page.wait_for_timeout(300); shot("14_phone")
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        print("horizontal overflow on phone width:", overflow)
        b.close()
except Exception:
    try:
        why_stuck(page)
    except Exception as e:
        print('no diagnostics:', e)
    raise
finally:
    proc.terminate()
print("data files:", sorted(x.name for x in data.glob("*")))
print("\n".join(errors) or "no console errors")
