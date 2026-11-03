"""Opens the parents' portal in a real browser against a fake Supabase and checks: sign up with a code, children, grades, files, announcements."""
import functools, http.server, json, threading
from playwright.sync_api import sync_playwright

ROWS = {
    "parent_students": [{"student_code": "s1"}],
    "students": [{"code": "s1", "class_id": "g4-a", "display_name": "علي حسن"}],
    "grades": [{"trimester": 0, "week": 0, "subject": "ICT", "item": "Quiz Score", "score": 17, "max_score": 20}],
    "publications": [{"id": "p1", "kind": "link", "title": "Video lesson", "url": "https://youtu.be/x", "file_path": "", "created_at": "2026-10-30"}],
    "week_plans": [{"trimester": 0, "week": 8, "homework": ["Page 12"], "material": [{"title": "Site", "url": "https://x.org"}], "quiz_alerts": []}],
    "announcements": [{"title": "Trip", "body": "Bring food", "starts_on": "2026-10-30", "image_path": ""}],
}
seen = []

class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, out, code=200):
        raw = json.dumps(out).encode(); self.send_response(code)
        for k, v in {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*", "Content-Type": "application/json", "Content-Length": str(len(raw))}.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)
    def do_OPTIONS(self): self._send({})
    def do_GET(self):
        seen.append(("GET", self.path)); name = self.path.split("/rest/v1/")[1].split("?")[0]; self._send(ROWS.get(name, []))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}"); seen.append(("POST", self.path, body))
        if "/auth/v1/signup" in self.path or "grant_type" in self.path: return self._send({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        self._send("s1")

fake = http.server.HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory="portal"))
site.RequestHandlerClass.log_message = lambda *a: None
threading.Thread(target=site.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 800}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/config.js", lambda r: r.fulfill(body=f'window.PORTAL={{url:"http://127.0.0.1:{fake.server_port}",key:"K"}};', content_type="text/javascript"))
    pg.goto(f"http://127.0.0.1:{site.server_port}/index.html")
    pg.click("text=أول مرة"); pg.fill("input[type=email]", "p@x.com"); pg.fill("input[type=password]", "password1"); pg.fill("input[placeholder='XXXX-XXXX']", "K7M2-9QX4"); pg.click(".btn")
    pg.wait_for_selector("text=علي حسن"); pg.wait_for_selector("text=Quiz Score"); pg.wait_for_selector("text=17 / 20")
    assert any(s[0] == "POST" and "claim_student" in s[1] and s[2] == {"p_code": "K7M2-9QX4"} for s in seen), seen
    pg.click(".tabs:nth-of-type(2) >> text=الملفات"); pg.wait_for_selector("a[href='https://youtu.be/x']")
    pg.click(".tabs:nth-of-type(2) >> text=الأسبوع"); pg.wait_for_selector("text=Page 12")
    pg.click(".tabs:nth-of-type(2) >> text=الإعلانات"); pg.wait_for_selector("text=Bring food")
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal overflow"
    pg.click("#lang"); pg.wait_for_selector("text=Announcements"); pg.screenshot(path="/tmp/shots/portal.png")
    pg.click("#out"); pg.wait_for_selector("text=Sign in")
    b.close()
assert not errs, errs
print("portal ok")
