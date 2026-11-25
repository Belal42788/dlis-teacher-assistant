"""The Messages page in a real browser (desktop and phone) with the school server answered by canned replies:
a teacher starts a conversation, writes, sees the unread dot; the administration reviews, hides a message and closes a report."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp(); os.environ["DLIS_NO_KEYCHAIN"] = "1"
os.environ["DLIS_SCHOOL_DATA"] = os.path.join(root, "tests", "fixtures", "school_data")
sys.path.insert(0, root)
import urllib.request

from playwright.sync_api import sync_playwright

from app.server.http import AppServer

s = AppServer(); s.start_in_thread()
base = f"http://127.0.0.1:{s.port_number}"


def call(m, p, b=None):
    r = urllib.request.Request(base + p, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"X-DLIS-Token": s.token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r).read() or b"null")


call("POST", "/api/data-folder", {"path": tempfile.mkdtemp() + "/data"})
call("PUT", "/api/prefs", {"language": "en"})
call("PUT", "/api/settings", {"teacher_name": "Bilal", "subject": "ICT", "setup_done": True})
call("POST", "/api/whats-new/seen", {})
TH, TH2 = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"
state = {"role": "teacher", "sent": [], "hidden": [], "closed": [], "started": [], "read": [], "msgs": [
    {"id": "m1", "sender_id": "p9", "sender_role": "parent", "sender_name": "Ali's father", "body": "Hello teacher", "hidden": False, "created_at": "2026-11-20T10:00:00Z", "mine": False}]}


def threads():
    ths = [{"id": TH, "kind": "parent_teacher", "student_code": "s1", "student_name": "Ali", "class_id": "g4-a", "class_name": "Grade 4 A", "teacher_name": "Mr T", "mine": state["role"] != "admin", "last_at": "2026-11-20T10:00:00Z", "last_body": "Hello teacher", "last_role": "parent", "unread": TH not in state["read"] and state["role"] != "admin"}]
    return {"connected": True, "role": state["role"], "uid": "u1", "threads": ths, "unread": sum(1 for t in ths if t["unread"])}


def route(r):
    req = r.request; path = req.url.split(base)[1].split("?")[0]; body = json.loads(req.post_data or "{}") if req.method == "POST" else {}
    out = {}
    if path == "/api/cloud": out = {"signed_in": True, "role": state["role"], "url": "x", "email": "t@x"}
    elif path == "/api/messages": out = threads()
    elif path == "/api/messages/unread": out = {"unread": threads()["unread"]}
    elif path == "/api/messages/students": out = {"classes": [{"class_id": "g4-a", "name": "Grade 4 A", "students": [{"code": "s1", "name": "Ali", "student_login": True}]}, {"class_id": "kg1-a", "name": "KG1 A", "students": [{"code": "k1", "name": "Kid", "student_login": False}]}]}
    elif path == "/api/messages/reports": out = {"open": 0 if state["closed"] else 1, "reports": [{"id": "r1", "message_id": "m1", "reason": "rude", "status": "done" if state["closed"] else "open", "body": "Hello teacher", "sender_role": "parent", "sender_name": "Ali's father", "hidden": bool(state["hidden"]), "thread_id": TH, "kind": "parent_teacher", "student_name": "Ali", "created_at": "2026-11-21T10:00:00Z"}]}
    elif path == "/api/messages/start": state["started"].append(body); out = {"id": TH2, "existing": False}
    elif path == "/api/messages/send":
        m = {"id": f"s{len(state['sent'])}", "sender_id": "u1", "sender_role": "teacher", "sender_name": "Mr T", "body": body["body"], "hidden": False, "created_at": "2026-11-25T09:00:00Z", "mine": True}
        state["sent"].append(body); state["msgs"].append(m); out = {"message": m}
    elif path == "/api/messages/read": state["read"].append(body["thread_id"]); out = {"ok": True}
    elif re.fullmatch(r"/api/messages/[0-9a-f-]{36}", path): out = {"messages": [dict(m, hidden=m["id"] in state["hidden"] or m["hidden"], mine=m["mine"] and state["role"] != "admin") for m in state["msgs"]]}
    elif path.endswith("/hide"): state["hidden"].append(path.split("/")[3]); out = {"ok": True}
    elif path.endswith("/done"): state["closed"].append(path.split("/")[3]); out = {"ok": True}
    else: return r.continue_()
    r.fulfill(status=200, content_type="application/json", body=json.dumps(out))


def check(cond, msg):
    if not cond:
        print("FAILED:", msg); s.shutdown(); sys.exit(1)


errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (1200, 390):
        state.update(role="teacher", read=[], sent=[], hidden=[], closed=[], started=[])
        pg = b.new_page(viewport={"width": width, "height": 800}, bypass_csp=True); pg.add_init_script("localStorage.setItem('dlis.lang','en')")
        pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.route("**/api/**", route)
        pg.goto(base + "/"); pg.wait_for_timeout(900)
        pg.evaluate("location.hash='#/messages'"); pg.wait_for_selector(".ms-item")
        check(pg.locator(".ms-item.unread").count() == 1, "the new message must show as unread")
        pg.wait_for_function("document.querySelector('.nav-dot') && !document.querySelector('.nav-dot').hidden")
        pg.click(".ms-item"); pg.wait_for_selector(".ms-bubble")
        check("Hello teacher" in pg.inner_text(".ms-log"), "the parent's message must show")
        pg.wait_for_function("document.querySelector('.nav-dot').hidden")
        check(TH in state["read"], "opening the conversation marks it read")
        pg.fill(".ms-compose textarea", "Thanks, noted"); pg.press(".ms-compose textarea", "Enter")
        pg.wait_for_selector(".ms-bubble.mine"); check(state["sent"] and state["sent"][0]["body"] == "Thanks, noted", "Enter sends")
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / f"ms_chat_{width}.png"))
        # a new conversation: the student choice is off for a KG child
        if width < 700: pg.click(".ms-back")
        pg.click("text=New message")
        pg.select_option(".ms-pane select >> nth=0", "kg1-a")
        check(pg.locator(".ms-for-card").nth(0).is_disabled(), "KG child: «Student» must be disabled")
        pg.select_option(".ms-pane select >> nth=0", "g4-a")
        pg.locator(".ms-for-card").nth(0).click(); pg.click("text=Start conversation")
        pg.wait_for_function("window.__x = 1") ; pg.wait_for_timeout(400)
        check(state["started"] and state["started"][0] == {"student_code": "s1", "kind": "student_teacher"}, f"start payload: {state['started']}")
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / f"ms_new_{width}.png"))
        # the administration
        state["role"] = "admin"; pg.reload(); pg.wait_for_timeout(900)
        pg.evaluate("location.hash='#/messages'"); pg.wait_for_selector(".ms-item")
        check(pg.locator("text=New message").count() == 0, "the administration does not start conversations")
        pg.click(".ms-item"); pg.wait_for_selector(".ms-bubble")
        check(pg.locator(".ms-compose").count() == 0, "the administration cannot write in a conversation")
        pg.click(".ms-bubble >> nth=0 >> text=Hide"); pg.wait_for_selector(".ms-bubble.hidden-msg")
        check(state["hidden"] == ["m1"], "hide must reach the server")
        if width < 700: pg.click(".ms-back")
        pg.click(".seg-btn >> nth=1"); pg.wait_for_selector(".ms-rep")
        pg.click("text=Fine, keep the message"); pg.wait_for_selector(".ms-rep.done")
        check(state["closed"] == ["r1"], "closing the report must reach the server")
        pg.screenshot(path=str(Path(tempfile.gettempdir()) / f"ms_reports_{width}.png"))
        check(pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"horizontal overflow at {width}px")
        pg.close()
    b.close()
real = [e for e in errors if "Failed to load resource" not in e]
check(not real, f"browser errors: {real[:3]}")
s.shutdown()
print("messages ok")
