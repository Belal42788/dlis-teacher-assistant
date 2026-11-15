"""Opening the program fast: only the first screen's scripts are preloaded, the other pages load when opened, text files are sent compressed."""
import gzip
import os
import re
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nonet

nonet.install()
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()

from app.server.http import AppServer, Handler

ROOT = Path(__file__).resolve().parents[1]


class SpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = AppServer()
        cls.server.start_in_thread()
        cls.base = f"http://127.0.0.1:{cls.server.port_number}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def get(self, path, gz=False):
        req = urllib.request.Request(self.base + path, headers={"Accept-Encoding": "gzip"} if gz else {})
        with urllib.request.urlopen(req) as r:
            return r.read(), r.headers

    def test_only_the_first_screen_is_preloaded(self):
        first = set(Handler._first_screen_scripts())
        self.assertIn("main.js", first)
        self.assertIn("pages/today.js", first)
        every = {p.relative_to(ROOT / "app/web/js").as_posix() for p in (ROOT / "app/web/js").rglob("*.js")}
        self.assertLess(len(first), len(every) * 0.7, "the first screen should need clearly fewer scripts than the whole program")
        for lazy in ("pages/bank.js", "pages/map.js", "pages/library.js"):
            self.assertNotIn(lazy, first)
        html, _ = self.get("/")
        hrefs = set(re.findall(r'rel="modulepreload" href="/js/([^"]+)"', html.decode()))
        self.assertEqual(hrefs, first)

    def test_every_page_is_loaded_by_name_when_opened(self):
        main = (ROOT / "app/web/js/main.js").read_text(encoding="utf-8")
        for f in re.findall(r'import\("\./pages/(\w+)\.js"\)', main):
            self.assertTrue((ROOT / f"app/web/js/pages/{f}.js").is_file(), f)
        self.assertGreaterEqual(len(re.findall(r'load: \(\) => import\(', main)), 18)

    def test_only_the_language_in_use_is_loaded(self):
        i18n = (ROOT / "app/web/js/i18n.js").read_text(encoding="utf-8")
        self.assertLess(len(i18n), 5000)                       # the lookup only: the words are in the two language files
        first = self.get("/")[0].decode()
        self.assertNotIn("i18n_ar.js", first); self.assertNotIn("i18n_en.js", first)   # neither is fetched before the language is known
        for code in ("ar", "en"):
            self.assertTrue((ROOT / f"app/web/js/i18n_{code}.js").is_file())

    def test_text_files_are_compressed_only_when_asked(self):
        plain, h1 = self.get("/js/i18n_ar.js")
        self.assertIsNone(h1.get("Content-Encoding"))
        packed, h2 = self.get("/js/i18n_ar.js", gz=True)
        self.assertEqual(h2.get("Content-Encoding"), "gzip")
        self.assertEqual(gzip.decompress(packed), plain)
        self.assertLess(len(packed), len(plain) * 0.5)
        self.assertEqual(h2.get("Vary"), "Accept-Encoding")
        pic, h3 = self.get("/resources/logo-mark.png", gz=True)       # pictures are already small: sent as they are
        self.assertIsNone(h3.get("Content-Encoding"))
        self.assertTrue(pic.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
