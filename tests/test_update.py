import hashlib
import io
import json
import os
import time
import unittest
from unittest import mock

from helpers import tmp   # sets the import path and blocks the real internet
from app.core import paths
from app.core.errors import AppError
from app.server import update_service as U

PAYLOAD = b"MZ installer bytes " * 1000
URL = "https://github.com/me/school-app/releases/download/v9.9.9/DLIS_Teacher_Assistant_Setup.exe"


def _asset(payload=PAYLOAD, url=URL):
    return {"url": url, "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}


class TestUpdateInstall(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"DLIS_APP_HOME": tmp()}); env.start(); self.addCleanup(env.stop)
        for p in (mock.patch.object(U, "_frozen", lambda: True), mock.patch.object(U, "_platform", lambda: "windows")):
            p.start(); self.addCleanup(p.stop)
        paths.write_prefs(update={"at": time.time(), "ok": True, "version": "9.9.9", "url": "https://github.com/me/school-app/releases/tag/v9.9.9", "notes": "", "windows": _asset()})

        class Svc(U.UpdateMixin):
            _upd_job = {"state": "idle", "done": 0, "total": 0, "error": ""}
            def _update_sources(self): return {"update_url": "https://example.org/latest.json"}
            def _open_download(self, url): return io.BytesIO(self.body)
        self.Svc, self.svc = Svc, Svc()
        self.svc.body = PAYLOAD

    def _wait(self):
        for _ in range(200):
            if self.svc.update_progress()["state"] != "downloading":
                return self.svc.update_progress()
            time.sleep(0.02)
        self.fail("the download never finished")

    def test_the_notice_offers_install_only_in_an_installed_program_with_a_checkable_file(self):
        self.assertTrue(self.svc.check_update()["install"])
        with mock.patch.object(U, "_frozen", lambda: False):
            self.assertFalse(self.svc.check_update()["install"])   # run from the source folder: only the download page
        paths.write_prefs(update={"at": time.time(), "ok": True, "version": "9.9.9", "url": "https://example.org/get", "windows": {**_asset(), "sha256": ""}})
        self.assertFalse(self.svc.check_update()["install"])        # no sha256, so the download could not be checked

    def test_download_is_checked_then_launched_and_the_program_closes(self):
        self.svc.update_install()
        self.assertEqual(self._wait()["state"], "ready")
        self.assertNotIn("path", self.svc.update_progress())
        with mock.patch.object(U.subprocess, "Popen") as popen, mock.patch.object(U.threading, "Timer") as timer:
            self.assertEqual(self.svc.update_launch(), {"ok": True, "quits": True})
        cmd = popen.call_args[0][0]
        self.assertTrue(cmd[0].endswith("DLIS_Teacher_Assistant_Setup.exe") and "/SILENT" in cmd)
        self.assertTrue(timer.return_value.start.called)
        self.assertEqual(sorted(os.listdir(paths.app_support_dir() / "update")), ["DLIS_Teacher_Assistant_Setup.exe"])

    def test_a_wrong_file_is_thrown_away_and_never_run(self):
        self.svc.body = b"something else entirely"
        self.svc.update_install()
        self.assertEqual(self._wait()["error"], "update_bad_file")
        self.assertEqual(os.listdir(paths.app_support_dir() / "update"), [])
        with self.assertRaises(AppError):
            self.svc.update_launch()
        self.svc.body = PAYLOAD + b"more"   # bigger than announced
        self.svc.update_install()
        self.assertEqual(self._wait()["error"], "update_bad_file")

    def test_offline_and_unsupported(self):
        self.svc._open_download = lambda url: (_ for _ in ()).throw(OSError("offline"))
        self.svc.update_install()
        self.assertEqual(self._wait()["error"], "update_download_failed")
        with mock.patch.object(U, "_frozen", lambda: False), self.assertRaises(AppError) as e:
            self.svc.update_install()
        self.assertEqual(e.exception.code, "update_unsupported")

    def test_only_github_release_files_with_a_sha256_are_accepted(self):
        self.assertIsNotNone(U.clean_asset(_asset()))
        for bad in ({**_asset(), "url": "http://github.com/me/x/releases/download/v1/a.exe"}, {**_asset(), "url": "https://evil.example/a.exe"},
                    {**_asset(), "url": "https://github.com/me/x/archive/main.zip"}, {**_asset(), "sha256": "abc"}, {**_asset(), "size": 0},
                    {**_asset(), "size": U.MAX_INSTALLER + 1}, None, "x"):
            self.assertIsNone(U.clean_asset(bad), bad)
        self.assertIsNotNone(U.clean_asset({**_asset(), "sha256": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()}))   # GitHub writes it with a prefix

    def test_the_files_are_read_from_latest_json_and_from_a_github_release(self):
        class R:
            def __init__(self, d): self.b = json.dumps(d).encode()
            def read(self, n): return self.b
            def __enter__(self): return self
            def __exit__(self, *a): return False
        mine = U.UpdateMixin()
        with mock.patch.object(U.urllib.request, "urlopen", lambda *a, **k: R({"version": "9.9.9", "url": "https://x.org/r", "windows": _asset()})):
            self.assertEqual(mine._fetch_update({"update_url": "https://x.org/latest.json"})["windows"], _asset())
        rel = {"tag_name": "v9.9.9", "html_url": "https://github.com/me/school-app/releases/tag/v9.9.9",
               "assets": [{"name": "DLIS_Teacher_Assistant_Setup.exe", "browser_download_url": URL, "size": len(PAYLOAD), "digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()},
                          {"name": "notes.txt", "browser_download_url": "https://github.com/me/x/releases/download/v1/n.txt", "size": 3}]}
        with mock.patch.object(U.urllib.request, "urlopen", lambda *a, **k: R(rel)):
            got = mine._fetch_update({"update_repo": "me/school-app"})
        self.assertEqual(got["windows"], _asset())
        self.assertNotIn("mac", got)


if __name__ == "__main__":
    unittest.main()
