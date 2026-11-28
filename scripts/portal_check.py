"""Opens the family portal in a real browser against a fake Supabase and checks both kinds of account:
a parent (sign up with a code, children, grades, files by week, week plan, announcements, messages) and a student (sees the same, talks as the student)."""
import functools, http.server, json, os, threading, urllib.parse
from playwright.sync_api import sync_playwright

SHOTS = os.environ.get("SHOTS", "")
PARENT, STUDENT, TEACHER = "u-parent", "u-student", "u-teacher"
ROLE = {"v": "parent"}
DB = {
    "students": [{"code": "s1", "class_id": "g4-a", "grade_id": "g4", "display_name": "علي حسن"}],
    "grades": [{"trimester": 0, "week": w, "subject": "ICT", "item": it, "score": sc, "max_score": mx} for w, rows in ((8, (("Behavior", 5, 5), ("Homework", 4, 5), ("Quiz", 17, 20), ("Total", 26, 30))), (7, (("Behavior", 5, 5), ("Homework", 5, 5), ("Total", 10, 10)))) for it, sc, mx in rows]
              + [{"trimester": 0, "week": 8, "subject": "Math", "item": "Total", "score": 9, "max_score": 10}],
    "publications": [
        {"id": "p1", "kind": "link", "title": "Video lesson", "url": "https://youtu.be/x", "file_path": "", "created_at": "2026-11-28T08:00:00Z", "note": "Watch before class", "trimester": 0, "week": 8, "body": ""},
        {"id": "p2", "kind": "presentation", "title": "Fractions slides", "url": "", "file_path": "t1/fractions.pptx", "created_at": "2026-10-29T08:00:00Z", "note": "", "trimester": 0, "week": 8, "body": ""},
        {"id": "p3", "kind": "quiz", "title": "Quiz 3", "url": "", "file_path": "t1/q3.pdf", "created_at": "2026-10-20T08:00:00Z", "note": "", "trimester": 0, "week": 6, "body": ""},
        {"id": "p4", "kind": "other", "title": "Term books list", "url": "https://x.org/books", "file_path": "", "created_at": "2026-09-01T08:00:00Z", "note": "", "trimester": None, "week": None, "body": ""}],
    "week_plans": [{"trimester": 0, "week": 8, "subject": "ICT", "homework": ["Page 12", "Exercise 4"], "material": [{"title": "Site", "url": "https://x.org"}], "quiz_alerts": ["Quiz on Sunday"]}],
    "announcements": [{"title": "School trip", "body": "Bring food", "starts_on": "2026-11-28", "image_path": "", "created_at": "2026-11-28T07:00:00Z"}],
    "teacher_classes": [{"teacher_id": TEACHER, "subject": "ICT", "teacher_name": "Mr Ahmed"}, {"teacher_id": "u-t2", "subject": "Math", "teacher_name": "Ms Mona"}],
    "threads": [{"id": "th1", "kind": "parent_teacher", "teacher_id": TEACHER, "student_code": "s1", "last_at": "2026-11-20T10:00:00Z"}],
    "messages": [{"id": "m1", "thread_id": "th1", "sender_id": TEACHER, "sender_role": "teacher", "sender_name": "Mr Ahmed", "body": "Ali did well today", "created_at": "2026-11-20T10:00:00Z"}],
    "thread_reads": [],
}
seen = []
UID = lambda: PARENT if ROLE["v"] == "parent" else STUDENT

class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, out, code=200):
        raw = json.dumps(out).encode(); self.send_response(code)
        for k, v in {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*", "Content-Type": "application/json", "Content-Length": str(len(raw))}.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)
    def do_OPTIONS(self): self._send({})
    def do_PUT(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}"); seen.append(("PUT", self.path, body)); self._send({"id": UID()})
    def do_GET(self):
        seen.append(("GET", self.path)); url = urllib.parse.urlparse(self.path); name = url.path.split("/rest/v1/")[1]; qs = urllib.parse.parse_qs(url.query)
        if name == "profiles": return self._send([{"role": ROLE["v"]}])
        if name == "parent_students": return self._send([{"student_code": "s1"}] if ROLE["v"] == "parent" and not ROLE.get("nokids") else [])
        if name == "student_accounts": return self._send([{"student_code": "s1"}] if ROLE["v"] == "student" else [])
        rows = list(DB.get(name, []))
        for col in ("thread_id", "student_code"):
            if col in qs and qs[col][0].startswith("eq."): rows = [r for r in rows if col not in r or r.get(col) == qs[col][0][3:]]
            elif col in qs and qs[col][0].startswith("in."): rows = [r for r in rows if col not in r or r.get(col) in qs[col][0][4:-1].split(",")]
        if "created_at" in qs and qs["created_at"][0].startswith("gt."): rows = [r for r in rows if r["created_at"] > qs["created_at"][0][3:]]
        if name == "messages": rows.sort(key=lambda r: r["created_at"], reverse="order=created_at.desc" in url.query)
        self._send(rows)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}"); seen.append(("POST", self.path, body))
        if "/auth/v1/signup" in self.path or "grant_type" in self.path: return self._send({"access_token": "e30." + __import__("base64").urlsafe_b64encode(json.dumps({"sub": UID()}).encode()).decode().rstrip("=") + ".x", "refresh_token": "RT", "expires_in": 3600, "user": {"email": "p@x.com"}})
        if "/rpc/claim_student" in self.path: return self._send("!locked" if body.get("p_code") == "LOCK-0000" else "!bad" if body.get("p_code") == "WRONG-000" else "s1")
        if "/storage/v1/object/sign/" in self.path: return self._send({"signedURL": "/object/sign/files/x?token=1"})
        if "/rest/v1/threads" in self.path:
            row = {"id": "th-new", "kind": body["kind"], "teacher_id": body["teacher_id"], "student_code": body["student_code"], "last_at": "2026-11-24T09:00:00Z"}; DB["threads"].append(row); return self._send([row], 201)
        if "/rest/v1/messages" in self.path:
            row = {"id": f"m{len(DB['messages']) + 1}", "thread_id": body["thread_id"], "sender_id": UID(), "sender_role": ROLE["v"], "sender_name": "", "body": body["body"], "created_at": "2026-11-24T09:05:00Z"}; DB["messages"].append(row); return self._send([row], 201)
        if "/rest/v1/thread_reads" in self.path or "/rest/v1/message_reports" in self.path: return self._send({}, 201)
        self._send({})

fake = http.server.HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory="portal"))
site.RequestHandlerClass.log_message = lambda *a: None
threading.Thread(target=site.serve_forever, daemon=True).start()

def shot(pg, name):
    if SHOTS: os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=f"{SHOTS}/{name}.png")

def fresh(b, width):
    ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=1); ctx.clock.set_fixed_time("2026-11-30T10:00:00"); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.route("**/config.js", lambda r: r.fulfill(body=f'window.PORTAL={{url:"http://127.0.0.1:{fake.server_port}",key:"K"}};', content_type="text/javascript"))
    pg.goto(f"http://127.0.0.1:{site.server_port}/index.html"); return pg, errs

def nav(pg, tab): pg.click(f".tabs >> text={tab}")
def sub(pg, name): pg.click(f".sub >> text={name}")

with sync_playwright() as p:
    b = p.chromium.launch()
    # ------------------------------------------------ a parent, on a computer
    ROLE["v"] = "parent"; pg, errs = fresh(b, 1280)
    shot(pg, "01-login")
    pg.click("text=أول مرة"); pg.fill("input[type=email]", "p@x.com"); pg.fill("input[type=password]", "password1"); pg.fill("#cd", "K7M2-9QX4"); pg.click("button[type=submit]")
    pg.wait_for_selector("text=أهلًا، علي حسن"); assert pg.is_visible(".top img[src='img/logo-mark.png']"), "logo missing"
    assert any(s[0] == "POST" and "claim_student" in s[1] and s[2] == {"p_code": "K7M2-9QX4"} for s in seen), seen
    assert pg.inner_text(".pill.role").strip() == "ولي الأمر", "the account must say it is a parent"
    shot(pg, "02-home")
    pg.wait_for_selector(".tabs [data-n=study]:not([hidden])"); assert pg.inner_text(".tabs [data-n=study]").strip() == "1", "the Study tab must say one new file"
    assert pg.is_visible(".card:has(h2:has-text('قريبًا في المدرسة'))"), "the home page must show what is coming up at school"
    nav(pg, "الدراسة"); pg.wait_for_selector("text=Page 12"); pg.wait_for_selector("text=Quiz on Sunday"); shot(pg, "03-week")
    sub(pg, "الملفات"); pg.wait_for_selector("a[href='https://youtu.be/x']"); assert pg.is_visible(".tree .count"); shot(pg, "04-files")
    assert pg.is_visible(".chip.new"), "a file published after the last visit must say New"
    pg.wait_for_selector(".sub [data-n=files][hidden]", state="attached"); assert not pg.is_visible(".tabs [data-n=study]"), "after opening Files nothing is new any more"
    pg.click(".tree >> text=الأسبوع 6"); pg.wait_for_selector("text=Quiz 3"); assert not pg.is_visible("text=Video lesson")
    pg.click(".tree >> text=ملفات عامة"); pg.wait_for_selector("text=Term books list")
    sub(pg, "الدرجات"); pg.wait_for_selector("text=17"); pg.wait_for_selector("h2:has-text('Math')"); shot(pg, "05-grades")
    sub(pg, "التقويم"); pg.wait_for_selector("text=الفصل الدراسي 2 · الأسبوع 1"); pg.wait_for_selector("text=إجازة الشتاء"); pg.wait_for_selector("text=KG – G5")
    assert not pg.is_visible("text=(G6 – G8)") and not pg.is_visible("text=Staff"), "events of other grades and staff days must not show"; shot(pg, "05b-calendar")
    nav(pg, "التواصل"); pg.wait_for_selector(".thread"); pg.click(".thread"); pg.wait_for_selector("text=Ali did well today")
    assert "المدرس" in pg.inner_text(".bubble .who"), "the teacher's message must be labelled"; shot(pg, "06-chat")
    pg.fill(".compose textarea", "Thank you, teacher"); pg.click(".compose .btn.primary"); pg.wait_for_selector(".bubble.mine >> text=Thank you, teacher")
    assert "ولي الأمر" in pg.inner_text(".bubble.mine .who"), "my message must say parent"
    assert any(s[0] == "POST" and "/messages" in s[1] and s[2] == {"thread_id": "th1", "body": "Thank you, teacher"} for s in seen), "message not sent"
    DB["messages"].append({"id": "m9", "thread_id": "th1", "sender_id": TEACHER, "sender_role": "teacher", "sender_name": "Mr Ahmed", "body": "See you tomorrow", "created_at": "2026-11-24T09:10:00Z"})
    pg.wait_for_selector("text=See you tomorrow", timeout=6000)                                     # the chat refreshes by itself
    pg.click(".bubble:not(.mine) .meta button >> nth=0"); pg.fill(".report-box input >> visible=true", "rude"); pg.click("text=إرسال البلاغ")
    pg.wait_for_selector("text=وصل البلاغ للإدارة"); assert any(s[0] == "POST" and "message_reports" in s[1] for s in seen)
    pg.click("text=رسالة جديدة"); pg.wait_for_selector("text=Ms Mona"); shot(pg, "07-new-message")
    pg.click(".pick .row >> text=Ms Mona"); pg.wait_for_selector(".compose")
    assert any(s[0] == "POST" and s[1].startswith("/rest/v1/threads") and s[2]["kind"] == "parent_teacher" and s[2]["teacher_id"] == "u-t2" for s in seen), "a parent talk must be the parents' kind"
    nav(pg, "التواصل"); sub(pg, "الإعلانات"); pg.wait_for_selector("text=Bring food")
    pg.click(".pill.role"); pg.wait_for_selector("text=حساب ولي الأمر"); shot(pg, "08-account")
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal overflow"
    pg.click("#lang"); pg.wait_for_selector("text=Family portal"); shot(pg, "09-english")
    pg.click("text=Sign out"); pg.wait_for_selector("text=Sign in")
    assert not errs, errs; pg.context.close()
    # ------------------------------------------------ the same family on a phone
    ROLE["v"] = "parent"; DB["threads"] = DB["threads"][:1]
    pg, errs = fresh(b, 390); pg.fill("#em", "p@x.com"); pg.fill("#pw", "password1"); pg.click("button[type=submit]"); pg.wait_for_selector("text=أهلًا، علي حسن")
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "overflow on the phone (home)"; shot(pg, "10-phone-home")
    nav(pg, "الدراسة"); sub(pg, "الملفات"); pg.wait_for_selector("text=Video lesson"); assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "overflow on the phone (files)"; shot(pg, "11-phone-files")
    sub(pg, "الدرجات"); pg.wait_for_selector("text=17"); assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "overflow on the phone (grades)"
    nav(pg, "التواصل"); pg.wait_for_selector(".thread"); pg.click(".thread"); pg.wait_for_selector(".compose"); assert not pg.is_visible(".threads"); shot(pg, "12-phone-chat")
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "overflow on the phone (chat)"
    assert not errs, errs; pg.context.close()
    # ------------------------------------------------ the student: the same things, but talks as the student
    ROLE["v"] = "student"; seen.clear(); DB["threads"] = DB["threads"][:1]
    pg, errs = fresh(b, 1280); pg.fill("#em", "s@x.com"); pg.fill("#pw", "password1"); pg.click("button[type=submit]"); pg.wait_for_selector("text=أهلًا، علي حسن")
    assert pg.inner_text(".pill.role").strip() == "الطالب", "the account must say it is a student"
    nav(pg, "الدراسة"); sub(pg, "الدرجات"); pg.wait_for_selector("text=17"); sub(pg, "الملفات"); pg.wait_for_selector("text=Video lesson")
    nav(pg, "التواصل"); pg.click(".thread"); pg.wait_for_selector("text=Ali did well today")
    assert pg.is_visible("text=تقدر تقراها بس") and not pg.is_visible(".compose"), "a parents' talk is read-only for the student"; shot(pg, "13-student-readonly")
    pg.click("text=رسالة جديدة"); pg.click(".pick .row >> text=Mr Ahmed"); pg.wait_for_selector(".compose")
    assert any(s[0] == "POST" and s[1].startswith("/rest/v1/threads") and s[2]["kind"] == "student_teacher" for s in seen), "a student talk must be the student's kind"
    pg.fill(".compose textarea", "May I ask something?"); pg.click(".compose .btn.primary"); pg.wait_for_selector(".bubble.mine >> text=May I ask something?"); assert "الطالب" in pg.inner_text(".bubble.mine .who")
    assert not errs, errs; pg.context.close()
    # ------------------------------------------------ the link in the "forgot password" email: a new password screen, then straight in
    ROLE["v"] = "parent"; seen.clear(); pg, errs = fresh(b, 1280)
    pg.goto(f"http://127.0.0.1:{site.server_port}/index.html#access_token=e30.e30.x&refresh_token=RT&expires_in=3600&type=recovery")
    pg.reload(); pg.wait_for_selector("text=اكتب كلمة سر جديدة"); assert "access_token" not in pg.url, "the token must not stay in the address"; shot(pg, "14-new-password")
    pg.fill("#np1", "short"); pg.fill("#np2", "short"); pg.click("button[type=submit]"); pg.wait_for_selector("text=8 حروف")
    pg.fill("#np1", "longenough1"); pg.fill("#np2", "different11"); pg.click("button[type=submit]"); pg.wait_for_selector("text=مش زي بعض")
    pg.fill("#np2", "longenough1"); pg.click("button[type=submit]"); pg.wait_for_selector("text=أهلًا، علي حسن")
    assert any(x[0] == "PUT" and x[2] == {"password": "longenough1"} for x in seen), "the new password was not sent"
    pg.goto(f"http://127.0.0.1:{site.server_port}/index.html#error=access_denied&error_code=otp_expired"); pg.reload(); pg.wait_for_selector("text=رابط الاستعادة انتهى")
    assert not errs, errs; pg.context.close()
    # ------------------------------------------------ a teacher account is turned away
    ROLE["v"] = "teacher"; pg, errs = fresh(b, 1280); pg.fill("#em", "t@x.com"); pg.fill("#pw", "password1"); pg.click("button[type=submit]"); pg.wait_for_selector("text=حساب مدرس")
    # ------------------------------------------------ wrong codes: told plainly, and a locked account is told to ask the school
    ROLE.update(v="parent", nokids=True); pg, errs = fresh(b, 390)
    pg.click("text=أول مرة"); pg.fill("input[type=email]", "n@x.com"); pg.fill("input[type=password]", "password1"); pg.fill("#cd", "WRONG-000"); pg.click("button[type=submit]")
    pg.wait_for_selector("text=الكود مش صح")
    pg.fill(".card input[dir=ltr]", "LOCK-0000"); pg.click("text=إضافة"); pg.wait_for_selector("text=اتقفل")
    b.close()
print("portal ok")
