"""Old folders keep working, and a backup can be put back safely. Frozen sample folders live in tests/fixtures/data_vN."""
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import nonet

nonet.install()

from app.core import restore, store as store_mod
from app.core.errors import AppError
from app.core.models import Calendar, Settings, Structure, Timetable
from app.core.store import DATA_VERSION, DataStore

FIX = ROOT / "tests" / "fixtures"


def copy_fixture(version: int) -> tuple[tempfile.TemporaryDirectory, Path]:
    d = tempfile.TemporaryDirectory()
    dest = Path(d.name) / "data"
    shutil.copytree(FIX / f"data_v{version}", dest)
    return d, dest


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and "_backup" not in p.parts and "Exports" not in p.parts}


class TestGoldenFolders(unittest.TestCase):
    def test_a_frozen_folder_exists_for_every_version(self):
        for v in range(1, DATA_VERSION + 1):
            self.assertTrue((FIX / f"data_v{v}").is_dir(),
                            f"DATA_VERSION is {DATA_VERSION} but tests/fixtures/data_v{v} is missing. Run scripts/make_golden_fixture.py BEFORE changing the data's shape.")

    def test_the_current_folder_opens_clean_and_nothing_is_changed(self):
        d, root = copy_fixture(DATA_VERSION)
        before = snapshot(root)
        st = DataStore(root)
        self.assertEqual((st.locked, st.upgraded_from, st.problems), ("", 0, []))
        self.assertEqual(snapshot(root), before)             # opening a folder must not rewrite it
        self.assertFalse((root / "_backup").exists())
        d.cleanup()

    def test_every_record_is_still_understood(self):
        """If a field is renamed or dropped in a model, the old data would silently lose it. This fails first."""
        d, root = copy_fixture(DATA_VERSION)
        for name, model in (("config.json", Settings), ("structure.json", Structure), ("schedule.json", Timetable), ("calendar.json", Calendar)):
            raw = json.loads((root / name).read_text(encoding="utf-8-sig"))
            back = model.model_validate(raw).model_dump(mode="json")
            lost = [k for k in raw if k not in back]
            self.assertEqual(lost, [], f"{name}: fields the app no longer knows: {lost}. Raise DATA_VERSION and add a MIGRATIONS step (see core/store.py).")
        from app.server.service import Service
        svc = Service(); svc.store = DataStore(root)
        h = svc.health()
        self.assertEqual((h["rooms"], h["students"]), (2, 6))
        self.assertEqual(len(svc.behavior_list("g4-a")["notes"]), 1)
        self.assertEqual(svc.seating_get("g4-a")["seats"]["0-0"], "سارة علي حسن")
        self.assertEqual(svc.log_last()["last"]["g4-a"]["slide"], 5)
        self.assertEqual(len(svc.list_tasks()["tasks"]) if hasattr(svc, "list_tasks") else 1, 1)
        d.cleanup()

    def test_older_folders_are_upgraded_after_a_copy(self):
        for v in range(1, DATA_VERSION):                        # (empty until the first real change of shape)
            d, root = copy_fixture(v)
            before = snapshot(root)
            st = DataStore(root)
            self.assertEqual((st.locked, st.upgraded_from, st._stored_version()), ("", v, DATA_VERSION))
            zips = list((root / "_backup" / "before_upgrade").glob("*.zip"))
            self.assertEqual(len(zips), 1)
            with zipfile.ZipFile(zips[0]) as z:
                self.assertEqual({n: z.read(n) for n in z.namelist()}, before)    # the copy is the folder exactly as it was
            d.cleanup()

    def test_the_upgrade_machinery_with_a_pretend_new_version(self):
        d, root = copy_fixture(1)
        before = snapshot(root)
        (root / "data_version.json").unlink()                    # a folder from before version numbers
        def step(store):
            cfg = json.loads(store.config_path().read_text(encoding="utf-8"))
            cfg["migrated"] = True
            store.config_path().write_text(json.dumps(cfg), encoding="utf-8")
        with mock.patch.object(store_mod, "DATA_VERSION", 2), mock.patch.dict(store_mod.MIGRATIONS, {1: step}):
            st = DataStore(root)
            self.assertEqual((st.locked, st.upgraded_from, st._stored_version()), ("", 1, 2))
            self.assertTrue(json.loads((root / "config.json").read_text(encoding="utf-8"))["migrated"])
            for name in before:                                  # every other file is untouched
                if name not in ("config.json", "data_version.json"):
                    self.assertEqual((root / name).read_bytes(), before[name], name)
            (zip_path,) = (root / "_backup" / "before_upgrade").glob("*.zip")
            with zipfile.ZipFile(zip_path) as z:
                self.assertNotIn(b"migrated", z.read("config.json"))
        d.cleanup()

    def test_a_failing_upgrade_stops_and_locks_without_damage(self):
        d, root = copy_fixture(1)
        (root / "data_version.json").unlink()
        before = snapshot(root)
        def boom(store):
            raise RuntimeError("bad step")
        with mock.patch.object(store_mod, "DATA_VERSION", 2), mock.patch.dict(store_mod.MIGRATIONS, {1: boom}):
            st = DataStore(root)
            self.assertEqual(st.locked, "failed")
            with self.assertRaises(AppError):
                st.write_json(root / "tasks.json", {})
            with self.assertRaises(AppError):                     # and a restore is refused too: the folder is untouched
                restore.restore(st, next(b["id"] for b in restore.list_backups(st)))
        self.assertEqual(snapshot(root), before)
        d.cleanup()

    def test_a_folder_from_a_newer_app_is_left_alone(self):
        d, root = copy_fixture(DATA_VERSION)
        (root / "data_version.json").write_text(json.dumps({"data_version": DATA_VERSION + 5}), encoding="utf-8")
        before = snapshot(root)
        self.assertEqual(DataStore(root).locked, "newer")
        self.assertEqual(snapshot(root), before)
        d.cleanup()


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.d, self.root = copy_fixture(DATA_VERSION)
        self.st = DataStore(self.root)
        self.zip = self.st.make_backup_zip()                      # "Back up now"

    def tearDown(self):
        self.d.cleanup()

    def students(self, room="g4-a"):
        return (self.root / "rooms" / room / "students.csv").read_text(encoding="utf-8-sig")

    def test_list_shows_each_kind_newest_first(self):
        self.st.auto_backup()
        kinds = [b["kind"] for b in restore.list_backups(self.st)]
        self.assertEqual(sorted(kinds), ["auto", "manual"])
        self.assertTrue(all(b["id"].startswith(("_backup/", "Exports/")) for b in restore.list_backups(self.st)))

    def test_a_copy_of_an_empty_folder_is_marked_unusable(self):
        empty = self.root / "Exports" / "DLIS_backup_empty.zip"
        with zipfile.ZipFile(empty, "w") as z:
            z.writestr("random.txt", "x")
        flags = {b["name"]: b["usable"] for b in restore.list_backups(self.st)}
        self.assertTrue(flags[self.zip.name])
        self.assertFalse(flags["DLIS_backup_empty.zip"])

    def test_restore_puts_the_old_files_back_keeps_new_ones_and_can_be_undone(self):
        original = self.students()
        (self.root / "rooms" / "g4-a" / "students.csv").write_text("#,Student\n1,Someone New\n", encoding="utf-8-sig")
        (self.root / "made_later.txt").write_text("keep me")
        out = restore.restore(self.st, f"Exports/{self.zip.name}")
        self.assertEqual(self.students(), original)
        self.assertEqual((self.root / "made_later.txt").read_text(), "keep me")       # nothing is deleted
        self.assertGreaterEqual(out["restored"], 8)
        safety = next(b for b in restore.list_backups(self.st) if b["kind"] == "restore")
        restore.restore(self.st, safety["id"])                                          # undo
        self.assertIn("Someone New", self.students())

    def test_wrong_choices_are_refused(self):
        for bad in ("../../etc/passwd", "/etc/passwd", "config.json", "Exports/nothing.zip", ""):
            with self.assertRaises(AppError) as e:
                restore.restore(self.st, bad)
            self.assertEqual(e.exception.code, "backup_unknown", bad)
        junk = self.root / "Exports" / "DLIS_backup_junk.zip"
        junk.write_bytes(b"not a zip")
        with self.assertRaises(AppError) as e:
            restore.restore(self.st, "Exports/DLIS_backup_junk.zip")
        self.assertEqual(e.exception.code, "backup_damaged")
        other = self.root / "Exports" / "DLIS_backup_other.zip"
        with zipfile.ZipFile(other, "w") as z:
            z.writestr("holiday_photos/a.txt", "x")
        with self.assertRaises(AppError) as e:
            restore.restore(self.st, "Exports/DLIS_backup_other.zip")
        self.assertEqual(e.exception.code, "backup_not_dlis")
        newer = self.root / "Exports" / "DLIS_backup_newer.zip"
        with zipfile.ZipFile(newer, "w") as z:
            z.writestr("config.json", "{}"); z.writestr("data_version.json", json.dumps({"data_version": DATA_VERSION + 1}))
        with self.assertRaises(AppError) as e:
            restore.restore(self.st, "Exports/DLIS_backup_newer.zip")
        self.assertEqual(e.exception.code, "backup_newer")

    def test_a_crafted_zip_cannot_write_outside_the_folder(self):
        evil = self.root / "Exports" / "DLIS_backup_evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("config.json", (self.root / "config.json").read_text(encoding="utf-8"))
            z.writestr("../escaped.txt", "x"); z.writestr("/abs_escaped.txt", "x"); z.writestr("C:/win_escaped.txt", "x")
            z.writestr("_backup/auto/planted.zip", "x"); z.writestr("Exports/planted.zip", "x"); z.writestr("good/inside.txt", "ok")
        restore.restore(self.st, "Exports/DLIS_backup_evil.zip")
        self.assertFalse((self.root.parent / "escaped.txt").exists())
        for name in ("escaped.txt", "abs_escaped.txt", "win_escaped.txt"):      # (not root / "C:", which Windows reads as the C drive itself)
            self.assertFalse((self.root / name).exists(), name)
            self.assertFalse((self.root / "C:" / name).exists() if sys.platform != "win32" else False)
        self.assertFalse((self.root / "_backup" / "auto" / "planted.zip").exists())
        self.assertEqual((self.root / "good" / "inside.txt").read_text(), "ok")

    def test_an_old_backup_without_a_version_stamp_is_read_as_version_one(self):
        old = self.root / "Exports" / "DLIS_backup_old.zip"
        with zipfile.ZipFile(old, "w") as z:
            for p in self.root.rglob("*"):
                if p.is_file() and p.name != "data_version.json" and "Exports" not in p.parts and "_backup" not in p.parts:
                    z.write(p, p.relative_to(self.root).as_posix())
        restore.restore(self.st, "Exports/DLIS_backup_old.zip")
        self.assertFalse((self.root / "data_version.json").exists())

    def test_the_service_reopens_the_folder_after_a_restore(self):
        from app.server.service import Service
        svc = Service(); svc.store = self.st
        h = svc.health()
        self.assertEqual((h["students"], h["locked"], h["data_version"]), (6, "", DATA_VERSION))
        self.assertIn("manual", {b["kind"] for b in h["backups"]})
        (self.root / "rooms" / "g5-b" / "students.csv").write_text("#,Student\n", encoding="utf-8-sig")
        self.assertEqual(svc.health()["students"], 4)
        out = svc.backup_restore({"id": f"Exports/{self.zip.name}"})
        self.assertEqual(out["data_locked"], "")
        self.assertIsNot(svc.store, self.st)
        self.assertEqual(svc.health()["students"], 6)

    def test_health_report_has_no_student_names_in_the_errors_view(self):
        from app.server.service import Service
        svc = Service(); svc.store = self.st
        h = svc.health()
        self.assertNotIn("سارة", json.dumps({k: v for k, v in h.items() if k != "backups"}, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
