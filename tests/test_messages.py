"""The teacher's side of the conversations with the families, against a fake school server that keeps its rows in memory."""
import json
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import helpers  # noqa: F401  (sets the import path and blocks the real internet)
from app.core.errors import AppError
from app.core.store import DataStore

TH1, TH2, M1, M2, REP = ("00000000-0000-0000-0000-00000000000%d" % i for i in (1, 2, 3, 4, 5))
ROLE = {"v": "teacher"}


def make_db():
    return {
        "threads": [{"id": TH1, "kind": "parent_teacher", "teacher_id": "u1", "student_code": "s1", "last_at": "2026-11-20T10:00:00Z"}],
        "messages": [{"id": M1, "thread_id": TH1, "sender_id": "p9", "sender_role": "parent", "sender_name": "", "body": "Hello teacher", "hidden": False, "created_at": "2026-11-20T10:00:00Z"}],
        "students": [{"code": "s1", "display_name": "Ali", "class_id": "g4-a", "grade_id": "g4"}, {"code": "s2", "display_name": "Mona", "class_id": "g4-a", "grade_id": "g4"},
                     {"code": "k1", "display_name": "Kid", "class_id": "kg1-a", "grade_id": "kg1"}],
        "teacher_classes": [{"teacher_id": "u1", "class_id": "g4-a", "subject": "ICT", "teacher_name": "Mr T"}, {"teacher_id": "u1", "class_id": "kg1-a", "subject": "ICT", "teacher_name": "Mr T"}],
        "thread_reads": [], "message_reports": [{"id": REP, "message_id": M1, "reporter_id": "p9", "reason": "rude", "status": "open", "created_at": "2026-11-21T10:00:00Z"}],
    }


class Fake(BaseHTTPRequestHandler):
    db: dict = {}
    seen: list = []

    def log_message(self, *a): pass

    def _send(self, out, code=200):
        raw = json.dumps(out).encode(); self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _rows(self, table, qs):
        rows = list(self.db.get(table, []))
        for col, vals in qs.items():
            v = vals[0]
            if v.startswith("eq."): rows = [r for r in rows if str(r.get(col)) == v[3:]]
            elif v.startswith("in."): rows = [r for r in rows if str(r.get(col)) in v[4:-1].split(",")]
            elif v.startswith("neq."): rows = [r for r in rows if str(r.get(col)) != v[4:]]
        return rows

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); qs = urllib.parse.parse_qs(u.query); self.seen.append(("GET", self.path))
        if u.path == "/rest/v1/profiles": return self._send([{"role": ROLE["v"], "full_name": ""}])
        rows = self._rows(u.path.split("/rest/v1/")[1], qs)
        if "order" in qs and qs["order"][0].startswith("created_at"):
            rows.sort(key=lambda r: r["created_at"], reverse=qs["order"][0].endswith("desc"))
        self._send(rows)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"); self.seen.append(("POST", self.path, body))
        if "grant_type=password" in self.path: return self._send({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "user": {"id": "u1"}})
        if not body: return self._send([], 201)
        table = self.path.split("/rest/v1/")[1].split("?")[0]; row = dict(body[0])
        if table == "threads": row.update(id=TH2, last_at="2026-11-24T09:00:00Z")
        if table == "messages": row.update(id="00000000-0000-0000-0000-0000000000aa", sender_id="u1", sender_role="teacher", sender_name="Mr T", hidden=False, created_at="2026-11-24T09:05:00Z")
        if table == "thread_reads": self.db["thread_reads"] = [r for r in self.db["thread_reads"] if r["thread_id"] != row["thread_id"]]
        self.db.setdefault(table, []).append(row); self._send([row], 201)

    def do_PATCH(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"); self.seen.append(("PATCH", self.path, body))
        u = urllib.parse.urlparse(self.path)
        for r in self._rows(u.path.split("/rest/v1/")[1], urllib.parse.parse_qs(u.query)): r.update(body)
        self._send({})


class TestMessages(unittest.TestCase):
    def setUp(self):
        from app.server.service import Service
        Fake.db, Fake.seen = make_db(), []
        self.srv = HTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory(); self.svc = Service(); self.svc.store = DataStore(self.tmp.name)
        ROLE["v"] = "teacher"; self.svc.put_cloud({"url": f"http://127.0.0.1:{self.srv.server_port}", "key": "ANON"}); self.svc.cloud_login({"email": "t@x.com", "password": "pw"})

    def tearDown(self):
        self.srv.shutdown(); self.tmp.cleanup()

    def test_inbox_unread_and_reading(self):
        d = self.svc.msg_threads()
        self.assertEqual((d["connected"], d["unread"], len(d["threads"])), (True, 1, 1))
        th = d["threads"][0]
        self.assertEqual((th["student_name"], th["kind"], th["last_body"], th["unread"]), ("Ali", "parent_teacher", "Hello teacher", True))
        self.assertEqual(self.svc.msg_thread(TH1)["messages"][0]["mine"], False)
        self.svc.msg_read({"thread_id": TH1})
        self.assertEqual(self.svc.msg_unread(), {"unread": 0})                        # answered or read: no longer waiting
        self.svc.msg_send({"thread_id": TH1, "body": "  Thank you  "})
        sent = [s for s in Fake.seen if s[0] == "POST" and "/messages" in s[1]][0][2]
        self.assertEqual(sent, [{"thread_id": TH1, "body": "Thank you"}])               # trimmed, and nothing else (the server stamps who wrote it)
        self.assertTrue(self.svc.msg_thread(TH1)["messages"][-1]["mine"])

    def test_send_is_checked_before_it_leaves(self):
        for bad in ({"thread_id": TH1, "body": "   "}, {"thread_id": TH1, "body": "x" * 1001}, {"thread_id": "not-an-id", "body": "hi"}, {"thread_id": "1; drop", "body": "hi"}):
            with self.assertRaises(AppError):
                self.svc.msg_send(bad)
        self.assertFalse([s for s in Fake.seen if s[0] == "POST" and "/messages" in s[1]])

    def test_start_a_conversation_for_the_student_or_the_parents(self):
        d = self.svc.msg_students()
        cls = {c["class_id"]: c for c in d["classes"]}
        self.assertEqual([s["name"] for s in cls["g4-a"]["students"]], ["Ali", "Mona"])
        self.assertTrue(cls["g4-a"]["students"][0]["student_login"])
        self.assertFalse(cls["kg1-a"]["students"][0]["student_login"])                # KG children have no login of their own
        self.assertEqual(self.svc.msg_start({"student_code": "s1", "kind": "parent_teacher"}), {"id": TH1, "existing": True})
        made = self.svc.msg_start({"student_code": "s1", "kind": "student_teacher"})
        self.assertEqual(made["existing"], False)
        self.assertEqual(len(self.svc.msg_threads()["threads"]), 2)
        with self.assertRaises(AppError):
            self.svc.msg_start({"student_code": "s1", "kind": "everyone"})

    def test_only_the_administration_sees_reports(self):
        with self.assertRaises(AppError) as cm:
            self.svc.msg_reports()
        self.assertEqual(cm.exception.code, "cloud_admin_only")
        ROLE["v"] = "admin"; self.svc.cloud_login({"email": "a@x.com", "password": "pw"})
        r = self.svc.msg_reports()
        self.assertEqual((r["open"], r["reports"][0]["body"], r["reports"][0]["student_name"], r["reports"][0]["kind"]), (1, "Hello teacher", "Ali", "parent_teacher"))
        self.svc.msg_report_done(REP, {"hide": True})
        self.assertEqual((Fake.db["messages"][0]["hidden"], Fake.db["message_reports"][0]["status"]), (True, "done"))
        self.svc.msg_hide(M1, {"hidden": False}); self.assertFalse(Fake.db["messages"][0]["hidden"])
        self.assertEqual(self.svc.msg_reports()["open"], 0)

    def test_signed_out_gets_an_empty_inbox(self):
        self.svc.cloud_logout()
        self.assertEqual(self.svc.msg_threads(), {"connected": False, "role": "", "threads": [], "unread": 0})
        with self.assertRaises(AppError):
            self.svc.msg_send({"thread_id": TH1, "body": "hi"})


if __name__ == "__main__":
    unittest.main()
