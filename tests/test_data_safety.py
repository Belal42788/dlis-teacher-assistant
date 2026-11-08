import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import tmp, AiCase   # sets the import path and blocks the real internet
from app.core.errors import AppError
from app.core.models import Settings
from app.core.store import DataStore


class TestRobustness(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp(); os.environ["DLIS_NO_OPEN"] = "1"
        from app.server.service import Service
        from app.core.store import DataStore
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"]}); self.svc.put_calendar(self.svc.school_calendar())

    def tearDown(self):
        self.svc.wait_for_backup()      # the weekly copy runs in the background; Windows cannot delete a folder while it writes
        self.d.cleanup()

    def test_damaged_file_is_restored_from_backup_and_kept_aside(self):
        store = self.svc.store
        self.svc.put_settings({"teacher_name": "Second", "subject": "ICT"})  # now a backup exists
        store.config_path().write_text("{broken", encoding="utf-8")
        self.assertEqual(self.svc.get_settings()["teacher_name"], "T")  # the backup is the version before the last save
        self.assertEqual(store.problems, [{"file": "config.json", "restored": True}])
        self.assertTrue(list((store.backup_root() / "_damaged").glob("config.json.*.damaged")))
        self.assertEqual(json.loads(store.config_path().read_text(encoding="utf-8"))["teacher_name"], "T")  # healthy file is back
        self.assertEqual(self.svc.bootstrap()["problems"][0]["file"], "config.json")

    def test_wrong_shape_and_no_backup_never_crashes(self):
        import shutil
        store = self.svc.store
        shutil.rmtree(store.backup_root(), ignore_errors=True)
        store.schedule_path().write_text('{"grid": 5}', encoding="utf-8")
        self.assertEqual(self.svc.get_timetable()["grid"], {})
        (store.root / "tasks.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(self.svc.list_tasks()["tasks"], [])
        (store.root / "lesson_log.json").write_text('{"entries": [1]}', encoding="utf-8")
        self.assertEqual(self.svc.log_last()["last"], {})
        self.assertFalse(any(p["restored"] for p in store.problems))

    def test_missing_data_folder_is_reported_not_silently_restarted(self):
        from app.core import paths
        from app.server.service import Service
        paths.write_prefs(data_folder="/no/such/folder/DLIS")
        b = Service().bootstrap()
        self.assertEqual((b["data_folder"], b["folder_missing"]), ("", "/no/such/folder/DLIS"))

    def test_strange_text_cannot_crash_word_files(self):
        bad = "Hello\x00\x01 world \u202e"
        r = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": bad, "objectives": ["a", "b"], "sunday": 5}})
        self.assertTrue(Path(r["path"]).is_file())
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": "not a dict"})
        r = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": f"1. {bad}?\na) x\nb) y\nAnswer: a"})
        self.assertEqual(r["questions"], 1)

    def test_only_documents_can_be_opened(self):
        (Path(self.svc.store.root) / "run.exe").write_text("x")
        with self.assertRaises(AppError):
            self.svc.open_file(str(Path(self.svc.store.root) / "run.exe"))
        with self.assertRaises(AppError):
            self.svc.open_file("/etc/passwd")
        self.assertTrue(self.svc.open_file(str(self.svc.store.root), True))


class TestServerBackup(AiCase):
    def test_backup_zip_admin_only(self):
        import json
        import zipfile
        from unittest import mock
        class Fake:
            def select(self, table, q): return [{"id": 1, "name": "x"}]
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "admin"}), mock.patch.object(self.svc, "_cloud_client", return_value=Fake()):
            r = self.svc.cloud_backup()
        self.assertEqual(r["counts"]["students"], 1)
        with zipfile.ZipFile(r["path"]) as z:
            self.assertEqual(json.loads(z.read("grades.json"))[0]["name"], "x")
        with mock.patch.object(self.svc, "_cloud_cfg", return_value={"role": "teacher"}):
            with self.assertRaises(AppError):
                self.svc.cloud_backup()


class TestAutoBackup(unittest.TestCase):
    def test_weekly_copy_keeps_last_five_and_skips_exports(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            s = DataStore(d)
            (Path(d) / "Documents").mkdir()
            (Path(d) / "Documents" / "plan.docx").write_text("x")
            s.exports_dir().mkdir(parents=True, exist_ok=True)
            (s.exports_dir() / "big.zip").write_text("y")
            first = s.auto_backup()
            self.assertTrue(first and first.exists())
            with zipfile.ZipFile(first) as z:
                names = z.namelist()
            self.assertIn("Documents/plan.docx", names)
            self.assertFalse([n for n in names if n.startswith(("Exports", "_backup"))])
            self.assertIsNone(s.auto_backup())   # still recent: nothing new
            folder = s.backup_root() / "auto"
            for i in range(1, 8):   # seven older copies exist; only the newest five remain
                (folder / f"DLIS_auto_2026-01-0{i}.zip").write_bytes(b"")
            (folder / first.name).rename(folder / "DLIS_auto_2026-02-01.zip")
            made = s.auto_backup(every_days=7)
            self.assertIsNotNone(made)
            self.assertEqual(len(list(folder.glob("DLIS_auto_*.zip"))), 5)



class TestDataVersion(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        import app.core.store as store_mod
        self.mod, self.mock = store_mod, mock

    def test_fresh_folder_is_stamped_on_first_save_only(self):
        d = Path(tmp())
        s = DataStore(d)
        self.assertFalse((d / "data_version.json").exists())   # opening an empty folder writes nothing
        s.save_settings(Settings())
        self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], self.mod.DATA_VERSION)

    def test_old_folder_without_a_version_file_counts_as_version_1(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        s = DataStore(d)
        self.assertEqual(s.locked, "")
        self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], 1)

    def test_newer_folder_is_never_changed(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        (d / "data_version.json").write_text(json.dumps({"data_version": 99}), encoding="utf-8")
        before = (d / "config.json").read_text(encoding="utf-8")
        s = DataStore(d)
        self.assertEqual(s.locked, "newer")
        with self.assertRaises(AppError) as cm:
            s.save_settings(Settings(teacher_name="changed"))
        self.assertEqual(cm.exception.code, "data_locked")
        self.assertEqual((d / "config.json").read_text(encoding="utf-8"), before)
        self.assertEqual(s.load_settings().teacher_name, "x")   # reading still works

    def test_upgrade_copies_first_then_runs_each_step_in_order(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")
        ran = []

        def to2(store):
            ran.append(2)
            self.assertTrue(list((store.backup_root() / "before_upgrade").glob("DLIS_before_v1_*.zip")))   # the copy exists BEFORE any change
            store.write_json(store.tasks_path(), {"tasks": ["moved"]})

        def to3(store): ran.append(3)
        with self.mock.patch.object(self.mod, "DATA_VERSION", 3), self.mock.patch.object(self.mod, "MIGRATIONS", {1: to2, 2: to3}):
            s = DataStore(d)
            self.assertEqual((s.locked, s.upgraded_from, ran), ("", 1, [2, 3]))
            self.assertEqual(json.loads((d / "data_version.json").read_text())["data_version"], 3)
            DataStore(d)   # opened again: nothing runs twice
            self.assertEqual(ran, [2, 3])
        import zipfile
        z = next((d / "_backup" / "before_upgrade").glob("*.zip"))
        self.assertIn("config.json", zipfile.ZipFile(z).namelist())

    def test_failed_upgrade_locks_the_folder_and_keeps_the_copy(self):
        d = Path(tmp())
        (d / "config.json").write_text(json.dumps({"teacher_name": "x"}), encoding="utf-8")

        def boom(store): raise RuntimeError("bad step")
        with self.mock.patch.object(self.mod, "DATA_VERSION", 2), self.mock.patch.object(self.mod, "MIGRATIONS", {1: boom}):
            s = DataStore(d)
            self.assertEqual(s.locked, "failed")
            self.assertTrue(list((d / "_backup" / "before_upgrade").glob("*.zip")))
            self.assertFalse((d / "data_version.json").exists())   # still version 1: the next start tries again
            with self.assertRaises(AppError):
                s.save_settings(Settings())


class TestUpdateNotice(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from app.core import paths
        from app.server.update_service import UpdateMixin
        self.paths, self.mock = paths, mock
        env = mock.patch.dict(os.environ, {"DLIS_APP_HOME": tmp()})
        env.start(); self.addCleanup(env.stop)

        class Svc(UpdateMixin):
            calls = 0
            src = {"update_url": "https://example.org/latest.json"}
            answer = {"version": "9.9.9", "url": "https://example.org/get", "notes": "n"}

            def _update_sources(self): return self.src

            def _fetch_update(self, src):
                Svc.calls += 1
                if isinstance(self.answer, Exception): raise self.answer
                return self.answer
        self.Svc = Svc
        self.svc = Svc()

    def test_version_compare(self):
        from app.server.update_service import is_newer
        self.assertTrue(is_newer("1.0.1", "1.0.0")); self.assertTrue(is_newer("v1.10.0", "1.9.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0")); self.assertFalse(is_newer("0.9", "1.0.0")); self.assertFalse(is_newer("", "1.0.0"))

    def test_shows_once_checked_daily_and_can_be_dismissed(self):
        r = self.svc.check_update()
        self.assertEqual((r["available"], r["version"], r["url"]), (True, "9.9.9", "https://example.org/get"))
        self.svc.check_update()
        self.assertEqual(self.Svc.calls, 1)   # asked once, then the saved answer is used for a day
        self.svc.dismiss_update("9.9.9")
        self.assertFalse(self.svc.check_update()["available"])

    def test_silent_when_off_unset_failing_or_not_newer(self):
        self.svc.set_update_check(False)
        self.assertEqual(self.svc.check_update(), {"available": False, "enabled": False})
        self.assertEqual(self.Svc.calls, 0)
        self.svc.set_update_check(True)
        self.Svc.src = {}
        self.assertFalse(self.svc.check_update()["available"])
        self.Svc.src = {"update_url": "https://example.org/latest.json"}
        self.Svc.answer = OSError("offline")
        self.assertFalse(self.svc.check_update()["available"])   # a failure is silent, and is not retried at once
        self.paths.write_prefs(update={})
        self.Svc.answer = {"version": self.paths.VERSION, "url": "https://example.org/get", "notes": ""}
        self.assertFalse(self.svc.check_update()["available"])

    def test_only_https_and_known_shapes_are_read(self):
        from app.server.update_service import UpdateMixin
        class Raw(UpdateMixin): pass
        self.assertIsNone(Raw()._fetch_update({"update_url": "http://example.org/x.json"}))
        self.assertIsNone(Raw()._fetch_update({"update_repo": "not a repo"}))


class TestPackaging(unittest.TestCase):
    def test_installer_version_matches_app(self):
        from app.core import paths
        iss = (Path(__file__).resolve().parents[1] / "installer" / "dlis.iss").read_text(encoding="utf-8")
        self.assertIn(f'#define AppVersion "{paths.VERSION}"', iss)

    def test_help_content_is_complete_in_both_languages(self):
        f = Path(__file__).resolve().parents[1] / "app" / "web" / "js" / "help_content.json"
        h = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in h["ar"]], [s["id"] for s in h["en"]])
        for lang in ("ar", "en"):
            for s in h[lang]:
                self.assertTrue(s["title"] and s["steps"], (lang, s["id"]))


if __name__ == "__main__":
    unittest.main()
