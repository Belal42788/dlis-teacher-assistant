"""A tiny local web server. Only this computer can talk to it, and only with the secret token."""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ..core import paths
from ..core.errors import AppError
from .service import Service

MAX_BODY = 40 * 1024 * 1024
# Windows can map .js to text/plain, which breaks ES modules, so we state the types ourselves.
_TYPES = {".js": "application/javascript", ".mjs": "application/javascript", ".css": "text/css",
          ".html": "text/html", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png",
          ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}


_SLOW = re.compile(r"/api/ai/(chat|test|models|lesson|quiz|trimester|revision)|/api/slides/(source|plan|image|image-test)|/api/sources/(import|url|[0-9a-f]+/(read|digest))")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, service: Service | None = None, port: int = 0):
        super().__init__(("127.0.0.1", port), Handler)
        self.service = service or Service()
        self.token = secrets.token_urlsafe(24)
        self.last_ping = time.time()
        self.write_lock = threading.RLock()  # one change to the data at a time (the AI calls are slow and stay outside)
        self.seen_ping = False
        self.allowed_hosts = set()
        self.port_number = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{self.port_number}", f"localhost:{self.port_number}"}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port_number}/"

    def start_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t


class Handler(BaseHTTPRequestHandler):
    server: AppServer
    protocol_version = "HTTP/1.1"
    timeout = 60  # a half-sent request must not hold a thread forever

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ------------------------------------------------------------ plumbing
    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "") in self.server.allowed_hosts

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise AppError("too_big", "File is too large.", status=413)
        if n == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise AppError("bad_json", "The request was not valid JSON.") from e
        return data if isinstance(data, dict) else {"_": data}

    # ------------------------------------------------------------ verbs
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def _dispatch(self, method: str):
        try:
            if not self._host_ok():
                return self._json(403, {"error": "bad_host"})
            url = urlparse(self.path)
            path = unquote(url.path)
            if path.startswith("/api/"):
                if self.headers.get("X-DLIS-Token") != self.server.token:
                    return self._json(403, {"error": "bad_token"})
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                return self._api(method, path, query)
            if method != "GET":
                return self._json(405, {"error": "method_not_allowed"})
            return self._static(path)
        except AppError as e:
            self._json(e.status, e.to_dict())
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as e:  # a request with strange values
            paths.log_error(traceback.format_exc())
            try:
                self._json(400, {"error": "bad_request", "message": f"{type(e).__name__}: {e}"})
            except OSError:
                pass
        except Exception as e:  # never show a stack trace to a teacher; keep it in the console
            paths.log_error(traceback.format_exc())
            try:
                self._json(500, {"error": "internal", "message": str(e)})
            except OSError:
                pass

    # ------------------------------------------------------------ static files
    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        if path in ("/resources/logo.svg", "/resources/logo-mark.svg", "/resources/logo-white.svg", "/resources/logo.png", "/resources/logo-mark.png"):
            f = paths.resources_dir() / path.rsplit("/", 1)[1]
        else:
            root = paths.web_dir().resolve()
            f = (root / path.lstrip("/")).resolve()
            if root not in f.parents and f != root:
                return self._json(404, {"error": "not_found"})
        if not f.is_file():
            return self._json(404, {"error": "not_found"})
        data = f.read_bytes()
        ctype = _TYPES.get(f.suffix.lower()) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if f.name == "index.html":
            data = data.replace(b"__TOKEN__", self.server.token.encode())
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml", "application/json"):
            ctype += "; charset=utf-8"
        etag = f'"{f.stat().st_mtime_ns:x}-{len(data):x}"' if f.name != "index.html" else ""
        if etag and self.headers.get("If-None-Match") == etag:
            return self._send(304, b"", ctype, {"ETag": etag, "Cache-Control": "no-cache"})
        self._send(200, data, ctype, {"ETag": etag, "Cache-Control": "no-cache"} if etag else None)

    # ------------------------------------------------------------ API
    def _api(self, method: str, path: str, q: dict):
        svc = self.server.service
        b = self._body() if method in ("POST", "PUT") else {}
        routes = [
            ("GET", r"/api/ping", lambda m, b: self._ping()),
            ("GET", r"/api/bootstrap", lambda m, b: svc.bootstrap()),
            ("PUT", r"/api/prefs", lambda m, b: svc.set_language(b.get("language", ""))),
            ("POST", r"/api/data-folder", lambda m, b: svc.set_data_folder(b.get("path", ""))),
            ("GET", r"/api/reminders", lambda m, b: svc.get_reminders()),
            ("GET", r"/api/sources", lambda m, b: svc.list_sources()),
            ("POST", r"/api/sources/import", lambda m, b: svc.import_source(b)),
            ("POST", r"/api/sources/url", lambda m, b: svc.import_url(b)),
            ("GET", r"/api/sources/([0-9a-f]{10})", lambda m, b: svc.get_source(m.group(1))),
            ("POST", r"/api/sources/([0-9a-f]{10})/read", lambda m, b: svc.read_source(m.group(1))),
            ("POST", r"/api/sources/([0-9a-f]{10})/digest", lambda m, b: svc.digest_source(m.group(1))),
            ("POST", r"/api/sources/([0-9a-f]{10})/delete", lambda m, b: svc.delete_source(m.group(1))),
            ("GET", r"/api/weekly", lambda m, b: svc.get_weekly(int(q.get("tri", 0)), int(q.get("week", 1)))),
            ("PUT", r"/api/weekly", lambda m, b: svc.set_weekly(b)),
            ("GET", r"/api/map", lambda m, b: svc.get_map()),
            ("PUT", r"/api/map", lambda m, b: svc.put_map(b)),
            ("PUT", r"/api/reminders", lambda m, b: svc.put_reminders(b)),
            ("GET", r"/api/background", lambda m, b: svc.get_background()),
            ("PUT", r"/api/background", lambda m, b: svc.put_background(b)),
            ("GET", r"/api/alarms", lambda m, b: svc.list_alarms()),
            ("POST", r"/api/alarms", lambda m, b: svc.add_alarm(b)),
            ("POST", r"/api/alarms/([a-z0-9_-]+)/update", lambda m, b: svc.update_alarm(m.group(1), b)),
            ("POST", r"/api/alarms/([a-z0-9_-]+)/delete", lambda m, b: svc.delete_alarm(m.group(1))),
            ("GET", r"/api/school-calendar", lambda m, b: svc.school_calendar()),
            ("POST", r"/api/fs/native", lambda m, b: svc.pick_folder_native(b.get("start", ""))),
            ("GET", r"/api/fs/list", lambda m, b: svc.fs_list(q.get("path", ""))),
            ("POST", r"/api/fs/mkdir", lambda m, b: svc.fs_mkdir(b.get("parent", ""), b.get("name", ""))),
            ("GET", r"/api/settings", lambda m, b: svc.get_settings()),
            ("PUT", r"/api/settings", lambda m, b: svc.put_settings(b)),
            ("POST", r"/api/setup/finish", lambda m, b: svc.finish_setup()),
            ("GET", r"/api/structure", lambda m, b: svc.get_structure()),
            ("PUT", r"/api/structure", lambda m, b: svc.put_structure(b)),
            ("POST", r"/api/structure/build", lambda m, b: svc.build_structure(b.get("selection", {}))),
            ("GET", r"/api/rooms/([a-z0-9_-]+)/students", lambda m, b: svc.get_students(m.group(1))),
            ("PUT", r"/api/rooms/([a-z0-9_-]+)/students", lambda m, b: svc.put_students(m.group(1), b.get("names", []), b.get("english"))),
            ("POST", r"/api/students/parse", lambda m, b: svc.parse_students(b)),
            ("GET", r"/api/timetable", lambda m, b: svc.get_timetable()),
            ("PUT", r"/api/timetable", lambda m, b: svc.put_timetable(b)),
            ("GET", r"/api/calendar", lambda m, b: svc.get_calendar()),
            ("PUT", r"/api/calendar", lambda m, b: svc.put_calendar(b)),
            ("POST", r"/api/today/change", lambda m, b: svc.change_today(b)),
            ("GET", r"/api/log/last", lambda m, b: svc.log_last()),
            ("GET", r"/api/log", lambda m, b: svc.log_list(q.get("room", ""), q.get("date", ""))),
            ("POST", r"/api/log", lambda m, b: svc.log_save(b)),
            ("POST", r"/api/log/([a-z0-9_-]+)/delete", lambda m, b: svc.log_delete(m.group(1))),
            ("GET", r"/api/overview", lambda m, b: svc.overview()),
            ("GET", r"/api/today", lambda m, b: svc.today(q.get("date", ""))),
            ("POST", r"/api/import/legacy", lambda m, b: svc.import_old(b.get("path", ""), b.get("dry_run", False))),
            ("POST", r"/api/backup", lambda m, b: svc.backup()),
            ("GET", r"/api/docs/context", lambda m, b: svc.docs_context(q.get("room", ""), int(q.get("tri", 0)), int(q.get("week", 1)))),
            ("POST", r"/api/docs/lesson-plan", lambda m, b: svc.make_lesson_plan(b)),
            ("POST", r"/api/docs/trimester-plan", lambda m, b: svc.make_trimester_plan(b)),
            ("POST", r"/api/docs/quiz", lambda m, b: svc.make_quiz(b)),
            ("POST", r"/api/docs/revision", lambda m, b: svc.make_revision(b)),
            ("POST", r"/api/docs/cover-sheet", lambda m, b: svc.make_cover_sheet(b)),
            ("POST", r"/api/docs/grading-sheet", lambda m, b: svc.make_grading_sheet(b)),
            ("POST", r"/api/open", lambda m, b: svc.open_file(b.get("path", ""), bool(b.get("folder")))),
            ("GET", r"/api/ai", lambda m, b: svc.ai_state()),
            ("POST", r"/api/ai/save", lambda m, b: svc.ai_save(b)),
            ("POST", r"/api/ai/off", lambda m, b: svc.ai_off()),
            ("POST", r"/api/ai/test", lambda m, b: svc.ai_test(b)),
            ("POST", r"/api/ai/models", lambda m, b: svc.ai_models(b)),
            ("GET", r"/api/ai/prompts", lambda m, b: svc.ai_prompts_get()),
            ("PUT", r"/api/ai/prompts", lambda m, b: svc.ai_prompts_put(b)),
            ("POST", r"/api/ai/chat", lambda m, b: svc.ai_chat(b)),
            ("GET", r"/api/chats", lambda m, b: svc.chats_list()),
            ("POST", r"/api/chats", lambda m, b: svc.chat_save("", b)),
            ("GET", r"/api/chats/([a-z0-9]+)", lambda m, b: svc.chat_get(m.group(1))),
            ("PUT", r"/api/chats/([a-z0-9]+)", lambda m, b: svc.chat_save(m.group(1), b)),
            ("POST", r"/api/chats/([a-z0-9]+)/delete", lambda m, b: svc.chat_delete(m.group(1))),
            ("GET", r"/api/slides/topics", lambda m, b: svc.slide_topics(q.get("grade", ""), int(q.get("tri", 0)))),
            ("POST", r"/api/slides/notebooklm", lambda m, b: svc.notebooklm_prompt(b)),
            ("GET", r"/api/slides/image-config", lambda m, b: svc.image_state()),
            ("PUT", r"/api/slides/image-config", lambda m, b: svc.image_save(b)),
            ("POST", r"/api/slides/image-test", lambda m, b: svc.image_test(b)),
            ("POST", r"/api/slides/image", lambda m, b: svc.slide_image(b)),
            ("POST", r"/api/slides/plan", lambda m, b: svc.slide_plan(b)),
            ("POST", r"/api/slides/build", lambda m, b: svc.slide_build(b)),
            ("POST", r"/api/slides/source", lambda m, b: svc.notebooklm_source(b)),
            ("POST", r"/api/ai/lesson", lambda m, b: svc.ai_generate_lesson(b)),
            ("POST", r"/api/ai/quiz", lambda m, b: svc.ai_generate_quiz(b)),
            ("POST", r"/api/ai/revision", lambda m, b: svc.ai_generate_revision(b)),
            ("POST", r"/api/ai/trimester", lambda m, b: svc.ai_generate_trimester(b)),
            ("POST", r"/api/open-url", lambda m, b: svc.open_url(b.get("url", ""))),
            ("GET", r"/api/tasks", lambda m, b: svc.list_tasks()),
            ("POST", r"/api/tasks", lambda m, b: svc.add_task(b)),
            ("POST", r"/api/tasks/([a-z0-9_:-]+)/update", lambda m, b: svc.update_task(m.group(1), b)),
            ("POST", r"/api/tasks/([a-z0-9_:-]+)/delete", lambda m, b: svc.delete_task(m.group(1))),
            ("POST", r"/api/tasks/dismiss", lambda m, b: svc.dismiss_task(b.get("id", ""))),
        ]
        path_found = False
        for verb, pattern, fn in routes:
            m = re.fullmatch(pattern, path)
            if m:
                path_found = True
                if verb == method:
                    if method != "GET" and not _SLOW.match(path):
                        with self.server.write_lock:
                            return self._json(200, fn(m, b))
                    return self._json(200, fn(m, b))
        return self._json(405 if path_found else 404, {"error": "not_found"})

    def _ping(self):
        self.server.last_ping = time.time()
        self.server.seen_ping = True
        return {"ok": True}
