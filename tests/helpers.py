import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nonet   # the tests never reach the real internet (same answer here, on GitHub, anywhere)
nonet.install()

ZIP_DATA = Path(os.environ.get("DLIS_LEGACY_SAMPLE", "/home/claude/proj/DLIS_Data"))


def tmp():
    return tempfile.mkdtemp()


class AiCase(unittest.TestCase):
    """A Service on a temp folder with one class, a timetable and a fake AI server (self.reply is what it answers)."""
    def setUp(self):
        import os, tempfile
        os.environ["DLIS_NO_OPEN"] = "1"
        self.home = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("DLIS_APP_HOME")   # put it back afterwards: other test files set their own at import time
        os.environ["DLIS_APP_HOME"] = self.home.name
        from app.server.service import Service
        from app.core.store import DataStore
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "T", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"]})
        self.svc.put_students("g4-a", ["Sara Ali Hassan", "Omar Samy"])
        self.svc.put_timetable({"grid": {"Sunday": {"1": "g4-a"}, "Monday": {"2": "g4-a"}}})
        self.svc.put_calendar(self.svc.school_calendar())
        self.sent = []
        from app.core import ai_client
        self.ai_client = ai_client
        self._orig = ai_client._http
        def fake(method, url, headers, body=None, timeout=0):
            self.sent.append((method, url, headers, body))
            if url.endswith("/models"):
                return {"data": [{"id": "models/m1"}, {"id": "m2"}]}
            if url.endswith("/v1/messages"):
                return {"content": [{"type": "text", "text": self.reply}]}
            return {"choices": [{"message": {"content": self.reply}}]}
        ai_client._http = fake
        self.reply = "ready"

    def tearDown(self):
        import os
        self.ai_client._http = self._orig
        if self._old_home is None:
            os.environ.pop("DLIS_APP_HOME", None)
        else:
            os.environ["DLIS_APP_HOME"] = self._old_home
        self.d.cleanup(); self.home.cleanup()
