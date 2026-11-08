"""Makes tests/fixtures/data_vN: a small but complete teacher folder as THIS version of the app writes it.
Run it ONLY when DATA_VERSION is raised, BEFORE you change the data's shape, so the old shape is frozen as a test folder:
    python scripts/make_golden_fixture.py
The tests then prove that every old folder still opens, is upgraded after a copy is saved, and loses nothing."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DLIS_APP_HOME"] = tempfile.mkdtemp()
os.environ["DLIS_NO_OPEN"] = "1"

from app.core.store import DATA_VERSION, DataStore
from app.server.service import Service

NAMES = ["سارة علي حسن", "عمر سامي", "ليلى إبراهيم", "يوسف عبدالله"]


def build(dest: Path) -> None:
    svc = Service()
    svc.store = DataStore(dest)
    svc.put_settings({"teacher_name": "Mr Sample", "subject": "ICT", "setup_done": True})
    svc.build_structure({"g4": ["A"], "g5": ["B"]})
    svc.put_students("g4-a", NAMES)
    svc.put_students("g5-b", NAMES[:2])
    svc.put_calendar(svc.school_calendar())
    svc.put_timetable({"grid": {"Sunday": {"1": "g4-a", "3": "g5-b"}, "Tuesday": {"2": "g4-a"}}, "duties": {"Monday": ["break"]}})
    svc.add_task({"title": "Print quizzes", "importance": "high", "deadline": "2026-10-26"})
    svc.log_save({"room_id": "g4-a", "date": "2026-10-18", "period": "1", "topic": "Input devices", "slide": 5, "total": 12, "next_note": "Bring mice"})
    svc.behavior_save({"room_id": "g4-a", "student": NAMES[0], "kind": "good", "note": "Helped a classmate"})
    svc.seating_save({"room_id": "g4-a", "rows": 3, "cols": 4, "seats": {"0-0": NAMES[0], "1-2": NAMES[1]}})
    svc.put_reminders({"minutes": 15})


if __name__ == "__main__":
    out = ROOT / "tests" / "fixtures" / f"data_v{DATA_VERSION}"
    if out.exists():
        sys.exit(f"{out} already exists: it is frozen on purpose. Delete it yourself only if you are sure.")
    work = Path(tempfile.mkdtemp()) / "data"
    build(work)
    shutil.rmtree(work / "_backup", ignore_errors=True)
    shutil.rmtree(work / "Exports", ignore_errors=True)
    shutil.copytree(work, out)
    print(f"made {out} ({sum(1 for p in out.rglob('*') if p.is_file())} files)")
