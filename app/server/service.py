"""What the screens can ask for. No HTTP in here, so it is easy to test."""
from __future__ import annotations

import re
import base64
import os
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from ..core import paths
from ..core.academic import AcademicCalendar
from ..core.errors import AppError
from ..core.legacy import import_legacy
from ..core.models import WEEKDAYS, Calendar, Holiday, Period, Settings, Structure, Timetable, is_safe_id
from ..core.presets import COMMON_SUBJECTS
from ..core.store import DataStore
from ..core.structure_service import build_from_selection, normalize, preset_payload, sort_structure
from ..core.students import parse_file, parse_text
from ..core.timetable import cancelled_on, scrub_timetable, sessions_on
from .ai_chat_service import AiChatMixin
from .ai_service import AiMixin
from .alarms_service import AlarmsMixin
from .chats_service import ChatsMixin
from .parent_week_service import ParentWeekMixin
from .coverage_service import CoverageMixin
from .update_service import UpdateMixin
from .cloud_service import CloudMixin
from .changes_service import ChangesMixin
from .docs_service import DocsMixin
from .library_service import LibraryMixin
from .log_service import LogMixin
from .behavior_service import BehaviorMixin
from .seating_service import SeatingMixin
from .map_service import MapMixin
from .revision_service import RevisionMixin
from .scheme_service import SchemeMixin
from .tools_service import ToolsMixin
from .grades_service import GradesMixin, InsightsMixin
from .slides_service import SlidesMixin
from .source_service import SourceMixin
from .week_service import WeekMixin
from .weekly_service import WeeklyMixin

LANGS = ("ar", "en")


def _validate(model, data):
    try:
        return model.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", ()))
        raise AppError("invalid_data", f"{where}: {first.get('msg', 'invalid')}", field=where) from e


class Service(SeatingMixin, BehaviorMixin, UpdateMixin, InsightsMixin, GradesMixin, ToolsMixin, SchemeMixin, LibraryMixin, ParentWeekMixin, CoverageMixin, CloudMixin, DocsMixin, AiMixin, AiChatMixin, ChatsMixin, AlarmsMixin, ChangesMixin, LogMixin, SlidesMixin, RevisionMixin, MapMixin, SourceMixin, WeekMixin, WeeklyMixin):
    def __init__(self):
        self.store: Optional[DataStore] = None
        folder = paths.read_prefs().get("data_folder")
        if folder and Path(folder).is_dir():
            try:
                self.store = DataStore(folder)
            except OSError:
                self.store = None

    # ------------------------------------------------------------ helpers
    def _need_store(self) -> DataStore:
        if not self.store:
            raise AppError("no_data_folder", "Choose a data folder first.", status=409)
        return self.store

    # ------------------------------------------------------------ start up
    def bootstrap(self) -> dict:
        prefs = paths.read_prefs()
        out = {
            "version": paths.VERSION,
            "frameless": bool(getattr(self, "frameless", False)),
            "native_dialog": bool(getattr(self, "native_folder_dialog", None)),
            "platform": sys.platform,
            "language": prefs.get("language") if prefs.get("language") in LANGS else "",
            "data_folder": str(self.store.root) if self.store else "",
            "suggested_folder": str(paths.default_data_folder()),
            "folder_missing": "" if self.store else (prefs.get("data_folder") or ""),
            "has_data": False, "setup_done": False, "settings": None, "conflicts": [], "data_locked": "", "upgraded_from": 0,
            "subjects": [{"en": e, "ar": a} for e, a in COMMON_SUBJECTS],
        }
        if self.store:
            settings = self.store.load_settings()
            out["problems"] = list(self.store.problems)
            out["data_locked"] = self.store.locked
            out["upgraded_from"] = self.store.upgraded_from
            out.update(has_data=self.store.has_data(), setup_done=settings.setup_done,
                       settings=settings.model_dump(mode="json"), conflicts=self.store.detect_conflicts())
            self._start_auto_backup()
            from ..core.translit import to_arabic, to_english
            # the greeting uses the language of the app: Arabic letters in Arabic, Latin letters in English
            out["teacher_name_ar"] = to_arabic(settings.teacher_name or "")
            out["teacher_name_en"] = to_english(settings.teacher_name or "")
        return out

    def _start_auto_backup(self) -> None:
        """Once per run, in the background: a weekly copy of the data folder (see DataStore.auto_backup)."""
        if getattr(self, "_auto_backup_started", False) or not self.store:
            return
        self._auto_backup_started = True
        store = self.store

        def run() -> None:
            try:
                store.auto_backup()
            except Exception as e:   # a failed copy must never disturb the teacher
                paths.log_error(f"auto backup failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    def set_language(self, lang: str) -> dict:
        if lang not in LANGS:
            raise AppError("bad_language")
        paths.write_prefs(language=lang)
        return {"language": lang}

    # ------------------------------------------------------------ how the app is used (stays on this computer: page counts and the teacher's own notes, no names)
    PAGE_IDS = ("today", "timetable", "calendar", "tasks", "reminders", "log", "docs", "slides", "sources", "chat", "classes", "publish", "announcements", "map", "settings", "help")

    def record_usage(self, page: str) -> dict:
        if page in self.PAGE_IDS:
            u = paths.read_prefs().get("usage") or {}
            pages = u.get("pages") if isinstance(u.get("pages"), dict) else {}
            pages[page] = int(pages.get(page, 0)) + 1
            paths.write_prefs(usage={"since": u.get("since") or date.today().isoformat(), "pages": pages})
        return {"ok": True}

    def add_feedback(self, b: dict) -> dict:
        text = str(b.get("text", "")).strip()[:1500]
        if not text:
            raise AppError("bad_value", "Write your note first.", status=400)
        page = str(b.get("page", ""))[:30]
        notes = list(paths.read_prefs().get("feedback") or [])[-199:]
        notes.append({"date": date.today().isoformat(), "page": page, "text": text})
        paths.write_prefs(feedback=notes)
        return {"count": len(notes)}

    def export_feedback(self) -> dict:
        prefs = paths.read_prefs()
        u = prefs.get("usage") or {}
        lines = [f"DLIS Teacher Assistant v{paths.VERSION}", f"System: {sys.platform}", f"Usage since {u.get('since', '-')}", "", "Page opens:"]
        lines += [f"  {k}: {v}" for k, v in sorted((u.get("pages") or {}).items(), key=lambda kv: -kv[1])]
        lines += ["", "Notes:"] + [f"  [{n['date']}] ({n['page']}) {n['text']}" for n in (prefs.get("feedback") or [])]
        try:   # the last lines of the error log help to find a problem without guessing
            log = paths.app_support_dir() / "error.log"
            if log.exists():
                lines += ["", "Last errors:"] + ["  " + x for x in log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]]
        except OSError:
            pass
        out = self._need_store().root / "Documents" / "DLIS_Feedback.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self._result(out)

    REMINDER_DEFAULTS = {"enabled": True, "minutes": 10, "skip_back_to_back": True, "sound": True, "ring_seconds": 60, "muted_date": "", "events_eve": True, "events_time": "13:00", "prayer": True, "tomorrow": True, "tomorrow_time": "19:00"}

    def get_reminders(self) -> dict:
        saved = paths.read_prefs().get("reminders")
        return {**self.REMINDER_DEFAULTS, **(saved if isinstance(saved, dict) else {})}

    def put_reminders(self, b: dict) -> dict:
        cur = self.get_reminders()
        if "enabled" in b:
            cur["enabled"] = bool(b["enabled"])
        if "skip_back_to_back" in b:
            cur["skip_back_to_back"] = bool(b["skip_back_to_back"])
        if "sound" in b:
            cur["sound"] = bool(b["sound"])
        if "minutes" in b:
            m = int(b["minutes"] or 10)
            if m not in (5, 10, 15, 20, 30):
                raise AppError("invalid_data", "Choose 5, 10, 15, 20 or 30 minutes.")
            cur["minutes"] = m
        if "ring_seconds" in b:
            r = int(b["ring_seconds"] or 0)
            if r not in (15, 30, 60, 120, 300, 0):  # 0 = keep ringing until answered
                raise AppError("invalid_data", "Choose how long the alarm rings.")
            cur["ring_seconds"] = r
        if "events_eve" in b:
            cur["events_eve"] = bool(b["events_eve"])
        if "prayer" in b:
            cur["prayer"] = bool(b["prayer"])
        if "tomorrow" in b:
            cur["tomorrow"] = bool(b["tomorrow"])
        if "tomorrow_time" in b:
            tm = str(b["tomorrow_time"] or "")
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", tm):
                raise AppError("invalid_data", "Choose a time.")
            cur["tomorrow_time"] = tm
        if "events_time" in b:
            tm = str(b["events_time"] or "")
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", tm):
                raise AppError("invalid_data", "Choose a time.")
            cur["events_time"] = tm
        if "muted_date" in b:
            cur["muted_date"] = str(b["muted_date"] or "")[:10]
        paths.write_prefs(reminders=cur)
        return cur

    # ---- keep running in the background (Windows tray); the launcher fills in what this computer can do
    background_support = {"tray": False, "autostart": False}
    apply_background = None  # set by the launcher: called with the new settings

    def get_background(self) -> dict:
        saved = paths.read_prefs().get("background")
        cur = {"keep_running": False, "autostart": False, **(saved if isinstance(saved, dict) else {})}
        return {**cur, "support": self.background_support}

    def put_background(self, b: dict) -> dict:
        cur = self.get_background()
        for k in ("keep_running", "autostart"):
            if k in b:
                cur[k] = bool(b[k]) and bool(self.background_support.get("tray" if k == "keep_running" else "autostart"))
        if cur["autostart"]:
            cur["keep_running"] = True  # starting with Windows only makes sense with the tray icon
        paths.write_prefs(background={"keep_running": cur["keep_running"], "autostart": cur["autostart"]})
        if self.apply_background:
            self.apply_background(cur)
        return self.get_background()

    def set_data_folder(self, path: str) -> dict:
        path = (path or "").strip()
        if not path:
            raise AppError("empty_path", "Choose a folder.")
        p = Path(path).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".dlis_write_test"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            raise AppError("folder_not_writable", f"Cannot save files in this folder: {e}") from e
        self.store = DataStore(p)
        paths.write_prefs(data_folder=str(self.store.root))
        return self.bootstrap()

    # ------------------------------------------------------------ folder browser (for non-technical users)
    def fs_list(self, path: str = "") -> dict:
        home = Path.home()
        shortcuts = []
        for kind, p in (("documents", home / "Documents"), ("desktop", home / "Desktop"), ("home", home)):
            if p.is_dir():
                shortcuts.append({"kind": kind, "label": kind.title(), "path": str(p)})
        try:
            for child in sorted(home.iterdir()):
                low = child.name.lower()
                if child.is_dir() and any(k in low for k in ("onedrive", "google drive", "dropbox", "icloud", "my drive")):
                    shortcuts.append({"label": child.name, "path": str(child), "cloud": True})
            if sys.platform == "darwin":
                cs = home / "Library" / "CloudStorage"
                if cs.is_dir():
                    for child in sorted(cs.iterdir()):
                        if child.is_dir():
                            shortcuts.append({"label": child.name, "path": str(child), "cloud": True})
        except OSError:
            pass
        if sys.platform == "win32":
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                if os.path.exists(f"{letter}:\\"):
                    shortcuts.append({"label": f"{letter}:", "path": f"{letter}:\\", "drive": True})
        cur = Path(path).expanduser() if path else (home / "Documents" if (home / "Documents").is_dir() else home)
        try:
            cur = cur.resolve()
            if not cur.is_dir():
                cur = home
            dirs = sorted((c.name for c in cur.iterdir() if c.is_dir() and not c.name.startswith(".")), key=str.casefold)
        except OSError:
            dirs = []
        parent = str(cur.parent) if cur.parent != cur else ""
        return {"path": str(cur), "parent": parent, "dirs": dirs, "shortcuts": shortcuts}

    def fs_mkdir(self, parent: str, name: str) -> dict:
        name = (name or "").strip()
        if not name or any(c in name for c in '\\/:*?"<>|'):
            raise AppError("bad_folder_name", "Folder name has characters that are not allowed.")
        target = Path(parent).expanduser() / name
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise AppError("folder_not_writable", str(e)) from e
        return self.fs_list(str(target))

    # ------------------------------------------------------------ documents
    def get_settings(self) -> dict:
        return self._need_store().load_settings().model_dump(mode="json")

    def put_settings(self, data: dict) -> dict:
        store = self._need_store()
        current = store.load_settings().model_dump(mode="json")
        current.update({k: v for k, v in (data or {}).items() if k in current})
        s = _validate(Settings, current)
        store.save_settings(s)
        return s.model_dump(mode="json")

    def finish_setup(self) -> dict:
        return self.put_settings({"setup_done": True})

    def _seed_roster(self, store, structure) -> None:
        """Classes the school already knows (resources/school_roster.json) start with their students.
        Only fills a class that has no student list yet, so a teacher's own edits are never overwritten."""
        import json
        f = paths.resources_dir() / "school_roster.json"
        if not f.is_file():
            return
        roster = json.loads(f.read_text(encoding="utf-8"))
        for room in structure.rooms:
            names = roster.get(room.id)
            if names and not store.students_path(room.id).exists():
                store.save_students(room.id, names)

    def get_structure(self) -> dict:
        store = self._need_store()
        self._seed_timetable(store)
        self._seed_roster(store, store.load_structure())
        s = sort_structure(store.load_structure())
        out = s.model_dump(mode="json")
        counts = {r.id: len(store.load_students(r.id)) for r in s.rooms}
        for r in out["rooms"]:
            r["student_count"] = counts.get(r["id"], 0)
        out["presets"] = preset_payload()
        return out

    def put_structure(self, data: dict) -> dict:
        store = self._need_store()
        s = normalize(_validate(Structure, data))
        store.save_structure(s)
        tt = scrub_timetable(store.load_timetable(), s)
        store.save_timetable(tt)
        return self.get_structure()

    def build_structure(self, selection: dict) -> dict:
        store = self._need_store()
        if not isinstance(selection, dict):
            raise AppError("invalid_data", "selection must be an object")
        s = build_from_selection({k: list(v) for k, v in selection.items()}, store.load_structure())
        store.save_structure(s)
        return self.get_structure()

    def get_students(self, room_id: str) -> dict:
        from ..core.translit import to_english, to_arabic, _AR
        _has_ar = lambda v: bool(_AR.search(v))
        store = self._need_store()
        self._room(room_id)
        full = store.load_students_full(room_id)
        fixed = False
        for x in full:  # English-only name -> keep it as the English spelling and fill an Arabic one
            if x["name"] and not _has_ar(x["name"]):
                x["english"], x["name"], fixed = x["name"], to_arabic(x["name"]), True
        if fixed:
            store.save_students_full(room_id, full)
        return {"room_id": room_id, "names": [x["name"] for x in full], "english": [x["english"] for x in full],
                "auto": [to_english(x["name"]) for x in full]}

    def put_students(self, room_id: str, names: list, english: Optional[list] = None) -> dict:
        from ..core.translit import to_english, to_arabic, _AR
        store = self._need_store()
        self._room(room_id)
        if not isinstance(names, list):
            raise AppError("invalid_data", "names must be a list")
        old = {x["name"]: x["english"] for x in store.load_students_full(room_id)}
        english = english if isinstance(english, list) else []
        seen, clean = set(), []
        for i, n in enumerate(names):
            n = " ".join(str(n).split())
            typed_en = ""
            if n and not _AR.search(n):  # typed in English only: keep as the English spelling, make the Arabic one
                typed_en, n = n, to_arabic(n)
            if n and n.casefold() not in seen:
                seen.add(n.casefold())
                en = " ".join(str(english[i]).split()) if i < len(english) and english[i] is not None else old.get(n, "")
                en = en or typed_en
                clean.append({"name": n, "english": "" if en == to_english(n) else en})  # only keep what the teacher changed
        store.save_students_full(room_id, clean)
        return {"room_id": room_id, "names": [c["name"] for c in clean], "english": [c["english"] for c in clean],
                "auto": [to_english(c["name"]) for c in clean]}

    def _room(self, room_id: str):
        if not is_safe_id(room_id):
            raise AppError("bad_id")
        room = next((r for r in self._need_store().load_structure().rooms if r.id == room_id), None)
        if not room:
            raise AppError("room_not_found", status=404)
        return room

    def parse_students(self, body: dict) -> dict:
        if body.get("data_b64"):
            try:
                raw = base64.b64decode(body["data_b64"])
            except ValueError as e:
                raise AppError("file_unreadable") from e
            return parse_file(body.get("filename", ""), raw)
        return parse_text(body.get("text", ""))

    def _fixed(self, tt: Timetable) -> dict:
        """Period times and the number of periods belong to the school, not to the teacher."""
        bell = paths.bell_schedule()
        tt.periods = [Period(**p) for p in bell["periods"]]
        tt.duties = {d: [k for k in v if k in ("break", "late")] for d, v in tt.duties.items() if d in WEEKDAYS and v}
        out = tt.model_dump(mode="json")
        out["bell"] = {k: bell[k] for k in ("breakfast", "break", "prayer", "late") if k in bell}
        return out

    def _seed_timetable(self, store) -> None:
        """Teachers whose timetable the school already has (resources/teacher_timetables.json) get it once.
        Their own later edits are kept: the same ready-made timetable is never applied twice."""
        import json
        import re
        f = paths.resources_dir() / "teacher_timetables.json"
        name = re.sub(r"\s+", "", store.load_settings().teacher_name).casefold()
        if not f.is_file() or not name:
            return
        for entry in json.loads(f.read_text(encoding="utf-8")):
            if not any(name.startswith(re.sub(r"\s+", "", m).casefold()) for m in entry["match"]):
                continue
            tt = store.load_timetable()
            if tt.seeded == entry["id"]:
                return
            sel: dict = {}
            for row in entry["grid"].values():
                for rid in row.values():
                    gid, letter = rid.rsplit("-", 1)
                    sel.setdefault(gid, [])
                    if letter.upper() not in sel[gid]:
                        sel[gid].append(letter.upper())
            store.save_structure(build_from_selection(sel, store.load_structure()))
            tt.grid, tt.duties, tt.seeded = entry["grid"], entry["duties"], entry["id"]
            store.save_timetable(tt)
            return

    def get_timetable(self) -> dict:
        store = self._need_store()
        self._seed_timetable(store)
        return self._fixed(scrub_timetable(self._with_fixed(store.load_timetable()), store.load_structure()))

    def _with_fixed(self, tt: Timetable) -> Timetable:
        tt.periods = [Period(**p) for p in paths.bell_schedule()["periods"]]
        return tt

    def put_timetable(self, data: dict) -> dict:
        store = self._need_store()
        data = dict(data or {})
        data.pop("periods", None)
        data.pop("bell", None)
        tt = self._with_fixed(_validate(Timetable, data))
        old = store.load_timetable()
        tt.seeded = old.seeded
        tt.overrides = old.overrides  # one-day changes are made from the Today page only
        tt = scrub_timetable(tt, store.load_structure())
        store.save_timetable(tt)
        return self._fixed(tt)

    def school_calendar(self) -> dict:
        """The official DLIS calendar that ships with the app (same for every teacher)."""
        import json
        f = paths.resources_dir() / "school_calendar.json"
        return json.loads(f.read_text(encoding="utf-8"))

    def pick_folder_native(self, start: str = "") -> dict:
        """The computer's own folder window (Windows Explorer / Finder), when the app window can show one."""
        fn = getattr(self, "native_folder_dialog", None)
        if not fn:
            raise AppError("no_native_dialog", "Not available here.", status=501)
        return {"path": fn(start) or ""}

    def _without_weekend_holidays(self, cal: Calendar) -> Calendar:
        """Tidy the holiday list: name unnamed ones from the official DLIS calendar, join consecutive days of the
        same holiday into one line, and drop 'holidays' that only fall on Fridays/Saturdays (already off every week)."""
        from datetime import timedelta
        working = {WEEKDAYS.index(d) for d in self._need_store().load_settings().working_days}
        official = [(date.fromisoformat(h["start"]), date.fromisoformat(h["end"] or h["start"]), h["name"])
                    for h in self.school_calendar()["holidays"]]

        official_events = [(date.fromisoformat(e["date"]), e["name"]) for e in self.school_calendar().get("events", []) if e.get("date")]

        def span(h):
            a = date.fromisoformat(h.start)
            b = date.fromisoformat(h.end) if h.end else a
            return a, max(a, b)  # an end date before the start (typo) counts as a single day

        ev_names = {n.split(" / ")[0].strip().lower() for _d, n in official_events} | {n.strip().lower() for _d, n in official_events}
        if cal.academic_year == self.school_calendar().get("academic_year"):
            # the school's own year: every official holiday must be there (orange cells of the school calendar)
            for x, y, n in official:
                if not any(date.fromisoformat(h.start) <= x and (date.fromisoformat(h.end or h.start) >= y) for h in cal.holidays if h.start):
                    cal.holidays.append(Holiday(start=x.isoformat(), end=y.isoformat() if y != x else "", name=n))

        rows, keep = [], []
        for h in cal.holidays:
            try:
                a, b = span(h)
            except ValueError:
                keep.append(h)  # incomplete row: leave it for the teacher to fix
                continue
            if cal.academic_year == self.school_calendar().get("academic_year") and h.name.strip().lower() in ev_names \
                    and not any(x <= b and a <= y for x, y, _n in official):
                continue  # a school event saved as a holiday by mistake: it is a normal school day
            if not h.name.strip():
                h.name = next((n for x, y, n in official if x <= a <= y), "")
                if not h.name and any(a <= d0 <= b for d0, _n in official_events):
                    continue  # a school event (revision, exams, parents' meeting...), not a holiday: a normal day with lessons
            if any(((a + timedelta(days=i)).weekday() in working) for i in range(min((b - a).days, 400) + 1)):
                rows.append(h)
        rows.sort(key=lambda h: h.start)
        merged = []
        for h in rows:
            a, b = span(h)
            if merged and merged[-1].name == h.name:
                pa, pb = span(merged[-1])
                if a <= pb + timedelta(days=1):
                    end = max(b, pb)
                    merged[-1].end = end.isoformat() if end != pa else ""
                    continue
            merged.append(h)
        cal.holidays = merged + keep
        return cal

    def get_calendar(self) -> dict:
        return self._without_weekend_holidays(self._need_store().load_calendar()).model_dump(mode="json")

    def put_calendar(self, data: dict) -> dict:
        store = self._need_store()
        cal = _validate(Calendar, data)
        for t in cal.trimesters:
            if t.start and t.end and t.start > t.end:
                raise AppError("trimester_dates", f"{t.name}: the end date is before the start date.")
        cal = self._without_weekend_holidays(cal)
        store.save_calendar(cal)
        return cal.model_dump(mode="json")

    # ------------------------------------------------------------ computed views
    def _calendar_service(self) -> AcademicCalendar:
        store = self._need_store()
        # the tidy list (names filled in, joined days) is what every page should see, not the raw saved one
        return AcademicCalendar(self._without_weekend_holidays(store.load_calendar()), store.load_settings().working_days)

    def overview(self, today: Optional[date] = None) -> dict:
        today = today or date.today()
        cal = self._calendar_service()
        return {
            "today": today.isoformat(),
            "position": cal.position(today),
            "trimesters": [{"index": i, "name": t.name, "start": t.start, "end": t.end,
                            "weeks": cal.trimester_weeks(i)} for i, t in enumerate(cal.cal.trimesters)],
        }

    def today(self, day: str = "") -> dict:
        store = self._need_store()
        try:
            d = date.fromisoformat(day) if day else date.today()
        except ValueError as e:
            raise AppError("invalid_data", "bad date") from e
        cal = self._calendar_service()
        self._seed_timetable(store)
        tt = self._with_fixed(store.load_timetable())
        sessions = sessions_on(d, tt, cal, store.load_structure())
        bell = paths.bell_schedule()
        duties, cancelled_duties = [], []
        if cal.is_school_day(d):
            off = set((tt.overrides.get(d.isoformat(), {}) or {}).get("cancel_duties", []))
            for kind in tt.duties.get(d.strftime("%A"), []):
                if kind in ("break", "late"):
                    item = {"kind": kind, "start": bell[kind]["start"], "end": bell[kind]["end"]}
                    (cancelled_duties if kind in off else duties).append(item)
        sessions = [{**x, "plan": self._plan_for(x["grade_id"], d)} for x in sessions]
        holiday = cal.holiday_on(d)
        nxt = cal.next_school_day(d)
        return {
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "position": cal.position(d),
            "school_day": cal.is_school_day(d),
            "weekend": not cal.is_working_weekday(d),
            "holiday": holiday.model_dump() if holiday else None,
            "events": cal.events_on(d),
            "sessions": sessions,
            "cancelled": cancelled_on(d, tt, store.load_structure()) if cal.is_school_day(d) else [],
            "changed": bool(tt.overrides.get(d.isoformat())),
            "periods": [p.model_dump() for p in tt.periods],
            "duties": duties,
            "cancelled_duties": cancelled_duties,
            "next_school_day": nxt.isoformat() if nxt else "",
        }

    # ------------------------------------------------------------ tools
    def import_old(self, path: str, dry_run: bool = False) -> dict:
        return import_legacy(path, self._need_store(), dry_run=bool(dry_run))

    def backup(self) -> dict:
        p = self._need_store().make_backup_zip()
        return {"path": str(p), "name": p.name}
