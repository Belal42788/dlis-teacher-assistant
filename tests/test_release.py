"""Releasing a new version: the numbers agree, teachers get a "What is new" window once, and the GitHub files are sane."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_release
import write_latest
from app.core import paths


class TestReleaseChecks(unittest.TestCase):
    def test_this_version_is_ready_to_release(self):
        self.assertEqual(check_release.problems(f"v{paths.VERSION}"), [])

    def test_wrong_names_are_caught(self):
        self.assertTrue(check_release.problems("1.0.0"))            # no "v"
        self.assertTrue(check_release.problems("v1.0"))
        bad = check_release.problems("v9.9.9")                        # the app and installer still say another number
        self.assertGreaterEqual(len(bad), 3)

    def test_whats_new_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("app/core/paths.py", "installer/dlis.iss", "portal/latest.json"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            (root / "resources").mkdir()
            self.assertEqual(len(check_release.problems(f"v{paths.VERSION}", root)), 1)   # only the missing notes
            (root / "resources/whats_new.json").write_text(json.dumps({paths.VERSION: {"ar": ["x"], "en": []}}), encoding="utf-8")
            self.assertEqual(len(check_release.problems(f"v{paths.VERSION}", root)), 1)   # both languages needed
            (root / "resources/whats_new.json").write_text(json.dumps({paths.VERSION: {"ar": ["x"], "en": ["x"]}}), encoding="utf-8")
            self.assertEqual(check_release.problems(f"v{paths.VERSION}", root), [])


class TestLatestFile(unittest.TestCase):
    def test_writes_what_the_app_reads(self):
        from app.server.update_service import is_newer
        with tempfile.TemporaryDirectory() as d:
            out = write_latest.write("v1.2.3", "https://github.com/a/b/releases/tag/v1.2.3", "## New\n* **Seating** chart\n* [docs](https://x.y) fixed", Path(d))
            self.assertEqual(json.loads((Path(d) / "portal/latest.json").read_text(encoding="utf-8")), out)
        self.assertEqual(out["version"], "1.2.3")
        self.assertEqual(out["notes"], "New Seating chart docs fixed")
        self.assertTrue(is_newer(out["version"], "1.0.0"))
        self.assertFalse(is_newer(out["version"], "1.2.3"))

    def test_notes_are_short_and_bad_input_is_refused(self):
        self.assertLessEqual(len(write_latest.clean_notes("word " * 200)), 300)
        with self.assertRaises(ValueError):
            write_latest.write("1.2.3", "https://x", "", Path(tempfile.gettempdir()))
        with self.assertRaises(ValueError):
            write_latest.write("v1.2.3", "http://x", "", Path(tempfile.gettempdir()))


class TestWhatsNew(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self._old = os.environ.get("DLIS_APP_HOME")
        os.environ["DLIS_APP_HOME"] = self.home.name
        from app.server.service import Service
        self.svc = Service()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DLIS_APP_HOME", None)
        else:
            os.environ["DLIS_APP_HOME"] = self._old
        self.home.cleanup()

    def test_every_release_note_is_complete_in_both_languages(self):
        notes = json.loads((ROOT / "resources/whats_new.json").read_text(encoding="utf-8"))
        self.assertIn(paths.VERSION, notes)          # a release without notes cannot be made
        for v, e in notes.items():
            self.assertRegex(v, r"^\d+\.\d+\.\d+$")
            self.assertEqual(len(e["ar"]), len(e["en"]), v)
            self.assertTrue(e["ar"] and all(isinstance(x, str) and x.strip() for x in e["ar"] + e["en"]), v)
            self.assertLessEqual(len(e["ar"]), 8, "a short list is read; a long one is skipped")

    def test_a_new_install_sees_nothing(self):
        self.svc.bootstrap()                                   # first start: no folder yet
        self.assertEqual(paths.read_prefs().get("seen_version"), paths.VERSION)
        paths.write_prefs(data_folder=self.home.name)          # then the teacher picks a folder
        self.assertEqual(self.svc.whats_new()["entries"], [])

    def test_an_update_shows_once(self):
        paths.write_prefs(data_folder=self.home.name, seen_version="0.9.0")
        r = self.svc.whats_new()["entries"]
        self.assertEqual([e["version"] for e in r], [paths.VERSION])
        self.assertTrue(r[0]["ar"] and r[0]["en"])
        self.svc.mark_whats_new_seen()
        self.assertEqual(self.svc.whats_new()["entries"], [])
        self.assertEqual([e["version"] for e in self.svc.whats_new(everything=True)["entries"]][:1], [paths.VERSION])   # the Settings button

    def test_folders_from_before_this_feature_see_it_once(self):
        paths.write_prefs(data_folder=self.home.name)           # old install: a folder, never stamped
        self.svc.stamp_first_run()
        self.assertTrue(self.svc.whats_new()["entries"])

    def test_notes_for_a_newer_version_are_not_shown_early(self):
        from unittest import mock
        paths.write_prefs(data_folder=self.home.name, seen_version="0.1.0")
        with mock.patch.object(paths, "VERSION", "0.5.0"):                  # this app is older than the 1.0.0 notes
            self.assertEqual(self.svc.whats_new()["entries"], [])


class TestGitHubFiles(unittest.TestCase):
    def setUp(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        self.yaml = yaml

    def load(self, rel):
        return self.yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))

    def test_every_workflow_is_valid_yaml_with_jobs(self):
        files = sorted((ROOT / ".github/workflows").glob("*.yml"))
        self.assertGreaterEqual(len(files), 6)
        for f in files:
            d = self.yaml.safe_load(f.read_text(encoding="utf-8"))
            self.assertTrue(d.get("jobs"), f.name)
            self.assertTrue(d.get(True) or d.get("on"), f.name)   # PyYAML reads the word "on" as True

    def test_release_builds_then_attaches_then_announces(self):
        rel = self.load(".github/workflows/release.yml")
        on = rel.get(True) or rel.get("on")
        self.assertEqual(on["release"]["types"], ["published"])
        jobs = rel["jobs"]
        self.assertEqual(list(jobs), ["verify", "build", "publish"])
        self.assertEqual(jobs["build"]["needs"], "verify")
        self.assertEqual(jobs["publish"]["needs"], "build")
        called = ROOT / jobs["build"]["uses"]
        self.assertTrue(called.is_file())
        called_on = self.yaml.safe_load(called.read_text(encoding="utf-8")); called_on = called_on.get(True) or called_on.get("on")
        self.assertIn("workflow_call", called_on)                      # the build can be called, not only started by hand
        self.assertNotIn("push", called_on)                            # and a tag alone no longer builds it twice
        text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        for need in ("scripts/check_release.py", "scripts/write_latest.py", "portal/latest.json", "gh release upload", "pages.yml"):
            self.assertIn(need, text)
        self.assertEqual(rel["permissions"]["contents"], "write")
        for script in re.findall(r"scripts/\w+\.py", text):
            self.assertTrue((ROOT / script).is_file(), script)
        pages = self.load(".github/workflows/pages.yml")
        self.assertIn("workflow_dispatch", pages.get(True) or pages.get("on"))   # the release starts it, a push by the robot would not

    def test_no_untrusted_text_inside_shell_commands(self):
        """A release name or description goes through env: variables, never straight into a command line."""
        for f in (ROOT / ".github/workflows").glob("*.yml"):
            d = self.yaml.safe_load(f.read_text(encoding="utf-8"))
            for job in d["jobs"].values():
                for step in job.get("steps", []):
                    run = step.get("run", "")
                    self.assertNotRegex(run, r"\$\{\{\s*github\.event\.(release|issue|pull_request|head_commit)", f"{f.name}: {step.get('name')}")

    def test_dependabot_and_security_check(self):
        d = self.load(".github/dependabot.yml")
        self.assertEqual({u["package-ecosystem"] for u in d["updates"]}, {"pip", "github-actions"})
        self.assertTrue(all(u["schedule"]["interval"] == "weekly" for u in d["updates"]))
        sec = self.load(".github/workflows/security.yml")
        on = sec.get(True) or sec.get("on")
        self.assertIn("schedule", on); self.assertIn("workflow_dispatch", on)
        self.assertIn("pip-audit", (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
