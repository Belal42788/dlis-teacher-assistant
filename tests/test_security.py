"""Safety checks: files are believed only when they are what their name says, zip bombs and huge pictures are refused,
and the page may only run and load our own files."""
import io
import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nonet

nonet.install()
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()

from app.core import upload_check as U
from app.core.errors import AppError
from app.server.http import AppServer

ROOT = Path(__file__).resolve().parents[1]


def zipped(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return out.getvalue()


class UploadChecks(unittest.TestCase):
    def code(self, name, raw):
        with self.assertRaises(AppError) as c:
            U.check_document(name, raw)
        return c.exception.code

    def test_a_file_must_be_what_its_name_says(self):
        self.assertEqual(self.code("report.docx", b"MZ\x90\x00 a program"), "file_suspicious")
        self.assertEqual(self.code("slides.pdf", b"<html>not a pdf</html>"), "file_suspicious")
        self.assertEqual(self.code("names.txt", b"hello\x00\x00world"), "file_suspicious")
        self.assertEqual(self.code("old.doc", b"PK\x03\x04"), "file_suspicious")
        self.assertEqual(self.code("broken.docx", b"PK\x03\x04 but not really a zip"), "file_unreadable")

    def test_real_files_pass(self):
        U.check_document("a.docx", zipped({"word/document.xml": "<x/>"}))
        U.check_document("a.pdf", b"%PDF-1.7\n...")
        U.check_document("a.txt", "اسم الطالب".encode())
        U.check_document("a.csv", b"name,grade\nx,1\n")
        U.check_document("a.png", b"\x89PNG")              # kinds we have no rule for are left to the code that reads them

    def test_a_zip_bomb_is_refused(self):
        bomb = zipped({"word/document.xml": b"0" * 200_000})
        with mock.patch.object(U, "MAX_UNPACKED", 100_000):
            self.assertEqual(self.code("bomb.docx", bomb), "file_suspicious")
        with mock.patch.object(U, "MAX_ENTRIES", 3):
            self.assertEqual(self.code("many.xlsx", zipped({f"f{i}": "x" for i in range(5)})), "file_suspicious")

    def test_a_zip_part_cannot_point_outside(self):
        self.assertEqual(self.code("evil.pptx", zipped({"../../evil.dll": "x"})), "file_suspicious")
        self.assertEqual(self.code("evil2.pptx", zipped({"/etc/passwd": "x"})), "file_suspicious")

    def test_a_huge_picture_is_refused(self):
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (40, 40)).save(buf, "PNG")
        U.check_picture(buf.getvalue())
        with mock.patch.object(U, "MAX_PIXELS", 100):
            with self.assertRaises(AppError) as c:
                U.check_picture(buf.getvalue())
        self.assertEqual(c.exception.code, "image_too_big")
        with self.assertRaises(AppError) as c:
            U.check_picture(b"not a picture")
        self.assertEqual(c.exception.code, "image_unreadable")


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = AppServer()
        cls.server.start_in_thread()
        cls.base = f"http://127.0.0.1:{cls.server.port_number}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_the_page_may_only_run_our_own_files(self):
        with urllib.request.urlopen(self.base + "/") as r:
            csp = r.headers["Content-Security-Policy"]
            self.assertEqual(r.headers["X-Frame-Options"], "DENY")
            html = r.read().decode()
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("script-src 'self' 'unsafe", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)")          # no script written inside the page

    def test_no_code_is_built_from_text_in_the_browser(self):
        bad = []
        for f in (ROOT / "app/web/js").rglob("*.js"):
            src = f.read_text(encoding="utf-8")
            for word in ("eval(", "new Function(", "document.write(", "insertAdjacentHTML("):
                if word in src:
                    bad.append(f"{f.name}: {word}")
        self.assertEqual(bad, [])


class FakeSafe:
    """Stands in for the computer's keychain so the logic can be tested anywhere."""
    def __init__(self):
        self.items = {}

    def save(self, n, v):
        self.items[n] = v
        return True

    def load(self, n):
        return self.items.get(n)

    def delete(self, n):
        self.items.pop(n, None)


class KeysInTheSafe(unittest.TestCase):
    def setUp(self):
        import json
        from app.server import ai_service
        from app.server.ai_service import AiMixin
        self.json, self.ai_service = json, ai_service
        self.tmp = Path(tempfile.mkdtemp())
        self.safe = FakeSafe()

        class Svc(AiMixin):
            def _ai_path(s):
                return self.tmp / "ai.json"
        self.svc = Svc()
        AiMixin._secret_cache.clear()
        self.patches = [mock.patch.object(ai_service.secret_store, "save", self.safe.save), mock.patch.object(ai_service.secret_store, "load", self.safe.load),
                        mock.patch.object(ai_service.secret_store, "delete", self.safe.delete), mock.patch.object(ai_service.secret_store, "backend", lambda: "fake")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def on_disk(self):
        return (self.tmp / "ai.json").read_text(encoding="utf-8")

    def test_a_key_goes_to_the_safe_and_not_to_the_file(self):
        self.svc._ai_write({"provider": "groq", "providers": {"groq": {"api_key": "gsk_SECRET123", "model": "m"}}, "image": {"hf_token": "hf_SECRET"}})
        self.assertNotIn("SECRET", self.on_disk())
        self.assertEqual(set(self.safe.items.values()), {"gsk_SECRET123", "hf_SECRET"})
        d = self.svc._ai_data()                                    # the program still sees the keys
        self.assertEqual(d["providers"]["groq"]["api_key"], "gsk_SECRET123")
        self.assertEqual(d["image"]["hf_token"], "hf_SECRET")
        self.assertEqual(d["providers"]["groq"]["model"], "m")

    def test_a_key_from_an_older_file_moves_into_the_safe(self):
        (self.tmp / "ai.json").write_text(self.json.dumps({"providers": {"groq": {"api_key": "gsk_OLD"}}}), encoding="utf-8")
        self.assertEqual(self.svc._ai_data()["providers"]["groq"]["api_key"], "gsk_OLD")
        self.assertNotIn("gsk_OLD", self.on_disk())
        self.assertIn("gsk_OLD", self.safe.items.values())

    def test_a_cleared_key_leaves_the_safe(self):
        self.svc._ai_write({"providers": {"groq": {"api_key": "gsk_X"}}})
        d = self.svc._ai_data()
        d["providers"]["groq"].pop("api_key")
        self.svc._ai_write(d)
        self.assertEqual(self.safe.items, {})
        self.assertNotIn("api_key", self.svc._ai_data()["providers"]["groq"])

    def test_without_a_safe_the_key_stays_in_the_file(self):
        with mock.patch.object(self.ai_service.secret_store, "save", lambda n, v: False), mock.patch.object(self.ai_service.secret_store, "backend", lambda: ""):
            self.svc._ai_write({"providers": {"groq": {"api_key": "gsk_PLAIN"}}})
            self.assertIn("gsk_PLAIN", self.on_disk())
            self.assertEqual(self.svc._ai_data()["providers"]["groq"]["api_key"], "gsk_PLAIN")

    def test_a_key_the_safe_lost_is_asked_for_again(self):
        self.svc._ai_write({"providers": {"groq": {"api_key": "gsk_X"}}})
        self.safe.items.clear(); self.ai_service.AiMixin._secret_cache.clear()
        self.assertNotIn("api_key", self.svc._ai_data()["providers"]["groq"])


class RealSafe(unittest.TestCase):
    """The real keychain of this computer (Windows Credential Manager / macOS Keychain). Windows must work; elsewhere it may be missing."""
    def test_round_trip(self):
        from app.core import secret_store as S
        saved = {k: os.environ.pop(k, None) for k in ("DLIS_NO_KEYCHAIN",)}
        os.environ["DLIS_KEYCHAIN_SERVICE"] = "DLIS Teacher Assistant TEST"
        try:
            b = S.backend()
            ok = S.save("test/key", "abc-\u0634\u0643\u0631\u0627-123")
            print(f"\nkeychain backend={b!r} works={ok}", file=sys.stderr)
            if sys.platform == "win32":
                self.assertTrue(ok, "Windows Credential Manager must work")
            if not ok:
                self.skipTest(f"no keychain here ({b!r})")
            self.assertEqual(S.load("test/key"), "abc-\u0634\u0643\u0631\u0627-123")
            S.delete("test/key")
            self.assertIsNone(S.load("test/key"))
        finally:
            S.delete("test/key")
            os.environ.pop("DLIS_KEYCHAIN_SERVICE", None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
