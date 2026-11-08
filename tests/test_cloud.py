import json
import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets the import path and blocks the real internet)
from app.core.errors import AppError
from app.core.store import DataStore


class TestCloud(unittest.TestCase):
    def test_sign_in_role_and_test_against_a_fake_server(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _go(self, body=None):
                seen.append((self.command, self.path, self.headers.get("apikey"), self.headers.get("Authorization")))
                if self.path.startswith("/auth/v1/token?grant_type=password"):
                    if body.get("password") != "good":
                        out, code = {"error_description": "Invalid login"}, 400
                    else:
                        out, code = {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"id": "u1"}}, 200
                elif self.path.startswith("/auth/v1/token?grant_type=refresh_token"):
                    out, code = {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600}, 200
                elif self.path.startswith("/rest/v1/profiles"):
                    out, code = [{"role": "teacher", "full_name": "T"}], 200
                else:
                    out, code = [], 200
                raw = json.dumps(out).encode()
                self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self): self._go()
            def do_POST(self): self._go(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"))

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                self.assertEqual(svc.get_cloud(), {"url": "", "configured": False, "school": "", "key_set": False, "email": "", "signed_in": False, "role": "", "mode": ""})
                with self.assertRaises(AppError):
                    svc.put_cloud({"url": "not a url"})
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "ANON"})
                with self.assertRaises(AppError) as cm:
                    svc.cloud_login({"email": "a@b.c", "password": "bad"})
                self.assertEqual(cm.exception.code, "cloud_bad_login")
                out = svc.cloud_login({"email": "a@b.c", "password": "good"})
                self.assertEqual((out["signed_in"], out["role"], out["mode"]), (True, "teacher", "online"))
                self.assertNotIn("good", (svc._cloud_path()).read_text())            # the password is never saved
                self.assertEqual(svc.get_cloud()["url"], "")                          # a teacher never sees the server's address
                with self.assertRaises(AppError):
                    svc.cloud_code_make()
                self.assertTrue(svc.cloud_test()["ok"])
                self.assertIn(("GET", "/rest/v1/profiles?select=role,full_name&limit=1", "ANON", "Bearer AT"), seen)
                svc2 = Service(); svc2.store = DataStore(d)                           # a new start stays signed in through the refresh token
                self.assertTrue(svc2.cloud_test()["ok"])
                self.assertTrue(any("refresh_token" in p for _m, p, _k, _a in seen))
                svc.cloud_logout(); self.assertFalse(svc.get_cloud()["signed_in"])
        finally:
            srv.shutdown()

    def test_school_code_round_trip(self):
        from app.server.service import Service
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            adm = Service(); adm.store = DataStore(a)
            adm.put_cloud({"url": "https://abc.supabase.co", "key": "ANONKEY", "school": "DLIS"})
            cfg = adm._cloud_cfg(); cfg["role"] = "admin"; adm._cloud_save(cfg)
            code = adm.cloud_code_make()["code"]
            self.assertTrue(code.startswith("DLIS-"))
            tch = Service(); tch.store = DataStore(b)
            r = tch.cloud_join({"code": " " + code[:20] + "\n" + code[20:]})        # spaces and line breaks from copy/paste are fine
            self.assertEqual((r["configured"], r["school"], r["url"]), (True, "DLIS", ""))
            self.assertEqual(tch._cloud_cfg()["key"], "ANONKEY")
            with self.assertRaises(AppError):
                tch.cloud_join({"code": "DLIS-nonsense"})
            self.assertFalse(tch.cloud_forget_school()["configured"])

    def test_announcements_admin_posts_teacher_cannot(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        role = {"v": "admin"}; rows = []; sent = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out, code=200):
                raw = json.dumps(out).encode(); self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def _body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            def do_GET(self):
                if self.path.startswith("/rest/v1/profiles"): return self._out([{"role": role["v"]}])
                if self.path.startswith("/rest/v1/announcements"): return self._out(rows)
                self._out([])
            def do_POST(self):
                b = self._body()
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                sent.append(b); rows.extend({"id": "11111111-1111-1111-1111-111111111111", "starts_on": "2020-01-01", "ends_on": None, **r} for r in b); self._out(b)
            def do_DELETE(self):
                sent.append(self.path); rows.clear(); self._out([])

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                self.assertFalse(svc.list_announcements()["connected"])
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"})
                svc.cloud_login({"email": "a@b.c", "password": "x"})
                with self.assertRaises(AppError):
                    svc.post_announcement({"title": "", "audience": "all"})
                with self.assertRaises(AppError):
                    svc.post_announcement({"title": "Hi", "audience": "nobody"})
                out = svc.post_announcement({"title": "  Trip   day ", "body": "Bring food", "audience": "parents", "starts_on": "2020-01-01", "ends_on": ""})
                self.assertEqual(sent[0][0]["title"], "Trip day"); self.assertNotIn("ends_on", sent[0][0])
                self.assertTrue(out["connected"] and len(out["items"]) == 1 and out["items"][0]["active"])
                svc.delete_announcement("11111111-1111-1111-1111-111111111111")
                self.assertEqual(sent[-1], "/rest/v1/announcements?id=eq.11111111-1111-1111-1111-111111111111")
                role["v"] = "teacher"; svc.cloud_login({"email": "a@b.c", "password": "x"})
                with self.assertRaises(AppError) as cm:
                    svc.post_announcement({"title": "x", "audience": "all"})
                self.assertEqual(cm.exception.code, "cloud_admin_only")
        finally:
            srv.shutdown()

    def test_publications_need_approval_and_pictures_are_shrunk(self):
        import base64, io, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from PIL import Image
        from app.server.service import Service
        log = []; rows = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out, code=200):
                raw = json.dumps(out).encode(); self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def _raw(self): return self.rfile.read(int(self.headers.get("Content-Length", 0)))
            def do_GET(self):
                self._out([{"role": "teacher"}] if "/profiles" in self.path else (rows if "/publications" in self.path else []))
            def do_POST(self):
                raw = self._raw()
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                if "/storage/" in self.path: log.append(("up", self.path, len(raw))); return self._out({})
                b = json.loads(raw); log.append(("ins", b)); rows.extend({"id": "22222222-2222-2222-2222-222222222222", **r} for r in b); self._out(b)
            def do_PATCH(self): log.append(("patch", self.path, json.loads(self._raw()))); self._out({})

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"}); svc.cloud_login({"email": "t@b.c", "password": "x"})
                with self.assertRaises(AppError) as cm:
                    svc.add_publication({"class_id": "g4-a", "kind": "quiz", "title": "Q1", "url": "https://x.com/q"})
                self.assertEqual(cm.exception.code, "quiz_needs_date")
                with self.assertRaises(AppError):
                    svc.add_publication({"class_id": "g4-a", "kind": "link", "title": "Video", "url": "javascript:alert(1)"})
                svc.add_publication({"class_id": "g4-a", "kind": "link", "title": "Video", "url": "https://youtu.be/x"})
                ins = [x for x in log if x[0] == "ins"][-1][1][0]
                self.assertEqual((ins["approved"], ins["class_id"]), (False, "g4-a"))   # never visible before the teacher approves
                svc.add_publication({"class_id": "g4-a", "kind": "quiz", "title": "Q1", "url": "https://x.com/q", "visible_from": "2026-11-05"})
                self.assertTrue([x for x in log if x[0] == "ins"][-1][1][0]["visible_from"].startswith("2026-11-05T00:00:00"))
                svc.add_publication({"class_id": "g4-a", "kind": "presentation", "title": "Slides", "file": {"filename": "a b.pptx", "data_b64": base64.b64encode(b"x" * 100).decode()}})
                self.assertTrue(any(x[0] == "up" and "/object/files/g4-a/" in x[1] for x in log))
                svc.set_publication("22222222-2222-2222-2222-222222222222", {"approved": True})
                self.assertEqual([x for x in log if x[0] == "patch"][-1][2], {"approved": True})
                # announcement picture: big photo becomes a small jpeg
                im = Image.new("RGB", (4000, 3000), (200, 30, 30)); buf = io.BytesIO(); im.save(buf, "PNG")
                from app.server.cloud_service import _small_jpeg
                out = Image.open(io.BytesIO(_small_jpeg(base64.b64encode(buf.getvalue()).decode())))
                self.assertEqual((out.format, max(out.size)), ("JPEG", 1280))
                with self.assertRaises(AppError):
                    _small_jpeg(base64.b64encode(b"not a picture").decode())
        finally:
            srv.shutdown()

    def test_parents_are_blocked_and_codes_are_made_once(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from app.server.service import Service
        role = {"v": "parent"}; posted = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, out):
                raw = json.dumps(out).encode(); self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self): self._out([{"role": role["v"]}] if "/profiles" in self.path else [])
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if "grant_type" in self.path: return self._out({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
                posted.append((self.path.split("?")[0], body)); self._out(body)

        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                svc = Service(); svc.store = DataStore(d)
                svc.put_cloud({"url": f"http://127.0.0.1:{srv.server_port}", "key": "K"})
                with self.assertRaises(AppError) as cm:
                    svc.cloud_login({"email": "p@b.c", "password": "x"})
                self.assertEqual(cm.exception.code, "cloud_parent_blocked")
                self.assertFalse(svc.get_cloud()["signed_in"])                       # a parent never stays signed in to the teachers' program
                role["v"] = "admin"; svc.cloud_login({"email": "a@b.c", "password": "x"})
                svc.build_structure({"kg1": ["A"], "g4": ["A"]}); svc.put_students("g4-a", ["Ali Hassan", "Sara Omar"])
                r1 = svc.prepare_codes()
                codes1 = [row for path, rows in posted if path.endswith("/activation_codes") for row in rows]
                n1 = len(codes1)
                self.assertGreaterEqual(n1, 2)
                self.assertTrue(all(len(c["code"]) == 8 for c in codes1) and len({c["code"] for c in codes1}) == n1)
                self.assertTrue(r1["path"].endswith("Parent_Codes.docx"))
                svc.prepare_codes()                                                   # running it again changes nothing for old students
                self.assertEqual(len([row for path, rows in posted if path.endswith("/activation_codes") for row in rows]), n1)
                role["v"] = "teacher"; svc.cloud_login({"email": "t@b.c", "password": "x"})
                with self.assertRaises(AppError):
                    svc.prepare_codes()
        finally:
            srv.shutdown()


class TestUsageNotes(unittest.TestCase):
    def test_usage_counts_and_notes_stay_local(self):
        from app.server.service import Service
        old = os.environ.get("DLIS_APP_HOME")
        self.addCleanup(lambda: os.environ.pop("DLIS_APP_HOME", None) if old is None else os.environ.__setitem__("DLIS_APP_HOME", old))
        with tempfile.TemporaryDirectory() as d:
            os.environ["DLIS_APP_HOME"] = d
            svc = Service(); svc.store = DataStore(d + "/data")
            for pg in ("today", "today", "docs", "evil"):
                svc.record_usage(pg)
            svc.add_feedback({"page": "docs", "text": "  The quiz tab is hard to find "})
            with self.assertRaises(AppError):
                svc.add_feedback({"text": " "})
            out = svc.export_feedback()
            txt = open(out["path"], encoding="utf-8").read()
            self.assertIn("today: 2", txt); self.assertIn("docs: 1", txt); self.assertNotIn("evil", txt)
            self.assertIn("The quiz tab is hard to find", txt)


if __name__ == "__main__":
    unittest.main()
