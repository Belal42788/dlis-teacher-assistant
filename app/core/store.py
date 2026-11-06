"""The data folder: plain JSON/CSV files, written safely, backed up, easy to sync."""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .errors import AppError
from .models import (Calendar, Settings, Structure, Timetable, SCHEMA_VERSION, is_safe_id)

KEEP_BACKUPS = 5
CONFLICT_MARKERS = ("(conflict)", "conflicted copy", "copy of ")

# The version of the whole data folder (one small file, data_version.json). Raise it ONLY when a new app version changes how the
# files look, and add the step that brings an old folder along:  MIGRATIONS[old_version] = function(store)  -> folder is now old_version + 1.
# The app copies the whole folder to _backup/before_upgrade first, and a folder written by a NEWER app is opened read-only.
DATA_VERSION = 1
MIGRATIONS: dict[int, Callable[["DataStore"], None]] = {}


# ---------------------------------------------------------------- migrations
# Files written by the first version of the app have no schema_version; we read them
# and quietly bring them to the current shape.

def _migrate_calendar(data: dict) -> dict:
    data = dict(data or {})
    holidays = []
    for h in data.get("holidays", []):
        if isinstance(h, str):
            holidays.append({"start": h, "end": "", "name": ""})
        elif isinstance(h, dict):
            holidays.append(h)
    data["holidays"] = holidays
    legacy_w1 = data.pop("week1_start", "")
    tris = [dict(t) for t in data.get("trimesters", [])]
    if legacy_w1 and tris and not tris[0].get("week1_start"):
        tris[0]["week1_start"] = legacy_w1
    data["trimesters"] = tris
    return data


def _migrate_timetable(data: dict) -> dict:
    data = dict(data or {})
    periods = []
    for p in data.get("periods", []):
        if isinstance(p, dict):
            periods.append({"name": str(p.get("name", "")), "start": p.get("start", p.get("start_time", "")) or "",
                            "end": p.get("end", p.get("end_time", "")) or ""})
    data["periods"] = periods
    grid = {}
    for day, row in (data.get("grid") or {}).items():
        grid[day] = {str(k): (v or "") for k, v in (row or {}).items()}
    data["grid"] = grid
    return data


def _migrate_structure(data: dict) -> dict:
    """Old files stored students inside structure.json and repeated entities. Drop both here."""
    data = dict(data or {})
    drop = {"stages": ("grades",), "grades": ("rooms",), "rooms": ("students",)}
    for key, unwanted in drop.items():
        seen, items = set(), []
        for item in data.get(key, []):
            if isinstance(item, dict) and item.get("id") not in seen:
                seen.add(item.get("id"))
                items.append({k: v for k, v in item.items() if k not in unwanted})
        data[key] = items
    return data


class DataStore:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.problems: list[dict] = []   # files that were damaged: {"file", "restored"} (shown to the teacher once)
        self.locked = ""                 # "" | "newer" (made by a newer app) | "failed" (the upgrade stopped): nothing is saved then
        self.upgraded_from = 0           # the old data version, when this start upgraded the folder
        self._stamped = False
        self._upgrade()

    # ------------------------------------------------------------ paths
    def config_path(self) -> Path: return self.root / "config.json"
    def structure_path(self) -> Path: return self.root / "structure.json"
    def schedule_path(self) -> Path: return self.root / "schedule.json"
    def calendar_path(self) -> Path: return self.root / "calendar.json"
    def tasks_path(self) -> Path: return self.root / "tasks.json"
    def backup_root(self) -> Path: return self.root / "_backup"
    def version_path(self) -> Path: return self.root / "data_version.json"
    def exports_dir(self) -> Path: return self.root / "Exports"

    def room_dir(self, room_id: str) -> Path:
        if not is_safe_id(room_id):
            raise AppError("bad_id", f"Unsafe room id: {room_id!r}")
        return self.root / "rooms" / room_id

    def students_path(self, room_id: str) -> Path:
        return self.room_dir(room_id) / "students.csv"

    def grade_dir(self, grade_id: str) -> Path:
        if not is_safe_id(grade_id):
            raise AppError("bad_id", f"Unsafe grade id: {grade_id!r}")
        return self.root / "grades" / grade_id

    # ------------------------------------------------------------ data version
    def _stored_version(self) -> int:
        try:
            v = json.loads(self.version_path().read_text(encoding="utf-8-sig")).get("data_version")
            return v if isinstance(v, int) and v >= 1 else 0
        except (OSError, ValueError, AttributeError):
            return 0

    def _stamp(self, version: int | None = None) -> None:
        self._stamped = True
        from .paths import VERSION
        self._write_bytes(self.version_path(), json.dumps({"data_version": version or DATA_VERSION, "app_version": VERSION}, indent=2).encode("utf-8"))

    def _upgrade(self) -> None:
        """Bring an older folder up to date (after a copy of it), and refuse to touch a folder from a newer app."""
        found = self._stored_version()
        if not found:
            found = 1 if self.has_data() else DATA_VERSION   # a folder from before data_version existed is version 1
        if found > DATA_VERSION:
            self.locked = "newer"
            self._stamped = True
            return
        if found < DATA_VERSION:
            try:
                dest = self.backup_root() / "before_upgrade" / f"DLIS_before_v{found}_{datetime.now():%Y%m%d_%H%M%S}.zip"
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._zip_to(dest)
                for v in range(found, DATA_VERSION):
                    step = MIGRATIONS.get(v)
                    if step:
                        step(self)
                self.upgraded_from = found
            except Exception as e:
                from . import paths
                paths.log_error(f"data upgrade from v{found} failed: {e}")
                self.locked = "failed"
                self._stamped = True
                return
            self._stamp()
        elif self.has_data() and not self.version_path().exists():
            self._stamp()

    def _zip_to(self, dest: Path) -> None:
        tmp = dest.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in self.root.rglob("*"):
                if not p.is_file() or self.backup_root() in p.parents or self.exports_dir() in p.parents or p.name.endswith(".tmp"):
                    continue
                try:
                    if p.stat().st_size > 100 * 1024 * 1024:
                        continue   # a huge file (a video, say) is not worth filling the disk for
                    z.write(p, p.relative_to(self.root).as_posix())
                except OSError:
                    continue   # a file that changes or is locked right now must not stop the copy
        tmp.replace(dest)

    # ------------------------------------------------------------ safe writing
    def _backup(self, path: Path) -> None:
        rel = path.relative_to(self.root)
        folder = self.backup_root() / rel.parent
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = folder / f"{path.name}.{stamp}.bak"
        dest.write_bytes(path.read_bytes())
        old = sorted(folder.glob(f"{path.name}.*.bak"))  # exact file name prefix: no cross-matching
        for stale in old[:-KEEP_BACKUPS]:
            stale.unlink(missing_ok=True)

    def _replace(self, tmp: Path, path: Path) -> None:
        """os.replace can fail for a moment on Windows when OneDrive, an antivirus or Word holds the file."""
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 7:
                    tmp.unlink(missing_ok=True)
                    raise AppError("file_busy", f"Another program is using {path.name}. Try again in a moment.", status=409)
                time.sleep(0.25 * (attempt + 1))

    def _write_bytes(self, path: Path, content: bytes) -> None:
        if self.locked:
            raise AppError("data_locked", "This data folder cannot be changed by this version of the app.", status=409, why=self.locked)
        with self._lock:
            if not self._stamped and path != self.version_path():
                self._stamp()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            if path.exists():
                try:
                    self._backup(path)
                except OSError:
                    pass  # a missing backup must never stop the teacher's save
            self._replace(tmp, path)

    def write_json(self, path: Path, data: Any) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        json.loads(text)  # make sure it round-trips before touching the real file
        self._write_bytes(path, text.encode("utf-8"))

    def read_json(self, path: Path, default: Any = None, check=None) -> Any:
        """The file if it is fine; otherwise the newest good backup; otherwise `default` (the damaged file is kept aside).
        `check(data)` may raise if the content has the wrong shape."""
        if not path.exists():
            return default
        for attempt in range(6):  # OneDrive / antivirus may hold the file for a moment: wait, never treat that as damage
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    text = f.read()
                break
            except OSError:
                if attempt == 5:
                    raise AppError("file_busy", f"Another program is using {path.name}. Try again in a moment.", status=409)
                time.sleep(0.2 * (attempt + 1))
        try:
            data = json.loads(text)
            if check:
                check(data)
            return data
        except (ValueError, TypeError, AttributeError, KeyError):
            return self._recover(path, default, check)
        except Exception as e:  # pydantic's ValidationError
            if type(e).__name__ != "ValidationError":
                raise
            return self._recover(path, default, check)

    def _recover(self, path: Path, default: Any, check=None) -> Any:
        rel = path.relative_to(self.root)
        with self._lock:
            restored = False
            result = default
            folder = self.backup_root() / rel.parent
            for b in sorted(folder.glob(f"{path.name}.*.bak"), reverse=True):
                try:
                    data = json.loads(b.read_text(encoding="utf-8-sig"))
                    if check:
                        check(data)
                    result, restored = data, True
                    break
                except Exception:
                    continue
            # keep the damaged file aside (never delete a teacher's data), and put the good copy back
            try:
                aside = self.backup_root() / "_damaged"
                aside.mkdir(parents=True, exist_ok=True)
                os.replace(path, aside / f"{path.name}.{datetime.now():%Y%m%d_%H%M%S}.damaged")
                if restored:
                    self._write_bytes(path, json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
            except OSError:
                pass
            self.problems.append({"file": str(rel), "restored": restored})
            return result

    def write_csv(self, path: Path, header: list[str], rows: list[list[str]]) -> None:
        buf = io.StringIO(newline="")
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        self._write_bytes(path, buf.getvalue().encode("utf-8-sig"))  # BOM so Excel shows Arabic correctly

    def read_csv(self, path: Path) -> list[list[str]]:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [row for row in csv.reader(f)]

    # ------------------------------------------------------------ typed documents
    def load_settings(self) -> Settings:
        data = self.read_json(self.config_path(), {}, check=lambda d: Settings.model_validate(dict(d))) or {}
        return Settings.model_validate({k: v for k, v in data.items()})

    def save_settings(self, settings: Settings) -> None:
        self.write_json(self.config_path(), settings.model_dump(mode="json"))

    def has_data(self) -> bool:
        return self.config_path().exists() or self.structure_path().exists()

    def load_structure(self) -> Structure:
        raw = self.read_json(self.structure_path(), {}, check=lambda d: Structure.model_validate(_migrate_structure(d))) or {}
        return Structure.model_validate(_migrate_structure(raw))

    def save_structure(self, s: Structure) -> None:
        self.write_json(self.structure_path(), s.model_dump(mode="json"))

    def load_timetable(self) -> Timetable:
        raw = self.read_json(self.schedule_path(), {}, check=lambda d: Timetable.model_validate(_migrate_timetable(d))) or {}
        return Timetable.model_validate(_migrate_timetable(raw))

    def save_timetable(self, t: Timetable) -> None:
        self.write_json(self.schedule_path(), t.model_dump(mode="json"))

    def load_calendar(self) -> Calendar:
        raw = self.read_json(self.calendar_path(), {}, check=lambda d: Calendar.model_validate(_migrate_calendar(d))) or {}
        return Calendar.model_validate(_migrate_calendar(raw))

    def save_calendar(self, c: Calendar) -> None:
        self.write_json(self.calendar_path(), c.model_dump(mode="json"))

    # ------------------------------------------------------------ students (CSV is the only copy)
    def load_students_full(self, room_id: str) -> list[dict]:
        """[{name, english}]; `english` is blank when the teacher has not written one (the app can spell it itself)."""
        rows = self.read_csv(self.students_path(room_id))
        out = []
        for r in rows[1:]:
            if r and r[0].strip():
                out.append({"name": r[0].strip(), "english": r[1].strip() if len(r) > 1 else ""})
        return out

    def load_students(self, room_id: str) -> list[str]:
        return [s["name"] for s in self.load_students_full(room_id)]

    def save_students_full(self, room_id: str, students: list[dict]) -> None:
        clean = [(s["name"].strip(), (s.get("english") or "").strip()) for s in students if s.get("name") and s["name"].strip()]
        self.write_csv(self.students_path(room_id), ["Name", "English"], [[n, e] for n, e in clean])

    def save_students(self, room_id: str, names: list[str]) -> None:
        old = {s["name"]: s["english"] for s in self.load_students_full(room_id)}
        self.save_students_full(room_id, [{"name": n, "english": old.get(n.strip(), "")} for n in names if n and n.strip()])

    # ------------------------------------------------------------ housekeeping
    def detect_conflicts(self) -> list[str]:
        found = []
        backup = self.backup_root()
        for p in self.root.rglob("*"):
            if not p.is_file() or backup in p.parents:
                continue
            low = p.name.lower()
            if low.startswith("~$") or any(m in low for m in CONFLICT_MARKERS):
                found.append(str(p.relative_to(self.root)))
        return found

    def make_backup_zip(self) -> Path:
        self.exports_dir().mkdir(parents=True, exist_ok=True)
        dest = self.exports_dir() / f"DLIS_backup_{datetime.now():%Y-%m-%d_%H%M%S}.zip"
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for p in self.root.rglob("*"):
                if p.is_file() and self.backup_root() not in p.parents and self.exports_dir() not in p.parents \
                        and not p.name.endswith(".tmp"):
                    z.write(p, p.relative_to(self.root).as_posix())
        return dest

    def auto_backup(self, every_days: int = 7, keep: int = 5) -> Path | None:
        """A quiet copy of the teacher's folder once a week, kept in the hidden _backup/auto folder (last `keep` copies).
        Returns the new file, or None when the last copy is still recent."""
        folder = self.backup_root() / "auto"
        folder.mkdir(parents=True, exist_ok=True)
        old = sorted(folder.glob("DLIS_auto_*.zip"))
        if old:
            try:
                if (date.today() - date.fromisoformat(old[-1].stem[-10:])).days < every_days:
                    return None
            except ValueError:
                pass
        dest = folder / f"DLIS_auto_{date.today():%Y-%m-%d}.zip"
        self._zip_to(dest)
        for extra in sorted(folder.glob("DLIS_auto_*.zip"))[:-keep]:
            try:
                extra.unlink()
            except OSError:
                pass
        return dest


__all__ = ["DataStore", "SCHEMA_VERSION"]
