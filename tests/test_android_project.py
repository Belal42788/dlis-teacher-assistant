"""The Android family app is generated from the portal by a GitHub workflow; this keeps its small hand-written parts consistent."""
import json
import unittest
from pathlib import Path

import helpers  # noqa: F401  (the tests never reach the real internet)
import yaml

ROOT = Path(__file__).resolve().parent.parent


class TestAndroidProject(unittest.TestCase):
    def test_the_app_wraps_the_portal(self):
        cfg = json.loads((ROOT / "android_app/capacitor.config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["appId"], "com.dlis.family")
        self.assertEqual(cfg["webDir"], "www")
        pkg = json.loads((ROOT / "android_app/package.json").read_text(encoding="utf-8"))
        for need in ("@capacitor/core", "@capacitor/android", "@capacitor/cli"):
            self.assertIn(need, pkg["dependencies"])
        self.assertEqual(cfg["android"]["adjustMarginsForEdgeToEdge"], "force", "the page must not slide under the phone's status bar")
        for f in ("icon-only", "icon-foreground", "icon-background", "splash", "splash-dark"):
            self.assertTrue((ROOT / f"android_app/assets/{f}.png").is_file(), f)

    def test_the_workflow_builds_an_apk_from_the_portal_folder(self):
        wf = yaml.safe_load((ROOT / ".github/workflows/android.yml").read_text(encoding="utf-8"))
        steps = wf["jobs"]["apk"]["steps"]
        runs = "\n".join(s.get("run", "") for s in steps)
        self.assertIn("../portal", runs)
        self.assertIn("assembleDebug", runs)
        self.assertIn("setTextZoom(100)", runs, "the phone's font size must not change the page's text size")
        self.assertIn("--splashBackgroundColor", runs)
        self.assertTrue(any(s.get("uses", "").startswith("actions/upload-artifact") for s in steps))

    def test_nothing_generated_is_committed(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for p in ("android_app/node_modules/", "android_app/www/", "android_app/android/"):
            self.assertIn(p, ignore)


if __name__ == "__main__":
    unittest.main()
