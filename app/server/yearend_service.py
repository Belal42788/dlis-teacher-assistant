"""End of the school year, in one safe step.

1. A full backup of the data folder is made first.
2. This year's records (marks, lesson log, behaviour notes, parents' weekly notes, seating) are copied to Archive/<year>/ and cleared.
3. Every class moves up one grade (KG1 -> KG2 -> Grade 1 ... ), keeping its letter; the last grade leaves the school.
   Students who are leaving (transferred out) are taken off before that. The new class lists are then the students who moved up;
   a class that receives nobody is empty and waits for the newcomers (Classes -> Paste or import a list).
4. The students' codes for the parents' portal follow them to their new class, so the families stay linked.
   What the school server needs to change is remembered in yearend.json for the administration's server step."""
import csv
import re
import shutil
from datetime import datetime

from ..core.errors import AppError
from ..core.presets import GRADE_PRESETS

YEAR_FILES = ("grades.json", "lesson_log.json", "behavior.json", "parent_week.json", "seating.json")
_ORDER = [g["id"] for g in sorted(GRADE_PRESETS, key=lambda g: g.get("order", 0))]


def _safe_label(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s or "").strip("_") or "year"


class YearEndMixin:
    def _yearend_path(self):
        return self._need_store().root / "yearend.json"

    def _next_of(self, room) -> tuple[str, str] | None:
        """(grade id, room id) of the class this one becomes next year, or None when it is the last grade."""
        if room.grade_id not in _ORDER:
            return None
        i = _ORDER.index(room.grade_id)
        if i + 1 >= len(_ORDER):
            return None
        letter = room.id.rsplit("-", 1)[-1]
        return _ORDER[i + 1], f"{_ORDER[i + 1]}-{letter}"

    def _year_label(self) -> str:
        cal = self._need_store().load_calendar()
        return _safe_label(cal.academic_year or f"{datetime.now():%Y}")

    def yearend_preview(self) -> dict:
        store = self._need_store()
        rooms = store.load_structure().rooms
        ids = {r.id: r for r in rooms}
        out = []
        for r in rooms:
            nxt = self._next_of(r)
            fate = "graduates" if nxt is None else "moves" if nxt[1] in ids else "elsewhere"
            out.append({"id": r.id, "name": r.name, "students": [x["name"] for x in store.load_students_full(r.id)], "fate": fate,
                        "next_name": ids[nxt[1]].name if nxt and nxt[1] in ids else (nxt[1] if nxt else "")})
        have = [f for f in YEAR_FILES if (store.root / f).exists()]
        last = dict(store.read_json(self._yearend_path(), {}) or {})
        srv = last.pop("server", None) or {}
        last["server"] = {"pending": bool(srv) and not srv.get("done"), "done": bool(srv.get("done")), "moved": len(srv.get("moved", [])), "removed": len(srv.get("removed", []))}
        return {"label": self._year_label(), "rooms": out, "files": have, "last": last}

    def yearend_run(self, b: dict) -> dict:
        if not b.get("confirm"):
            raise AppError("yearend_confirm", "Tick the box to confirm.", status=400)
        store = self._need_store()
        label = self._year_label()
        last = store.read_json(self._yearend_path(), {}) or {}
        if last.get("label") == label and not b.get("again"):
            raise AppError("yearend_done", f"The end of {label} was already done on {last.get('at', '')[:10]}.", status=409)
        leaving = {rid: {str(n) for n in names} for rid, names in (b.get("leaving") or {}).items() if isinstance(names, list)}
        rooms = store.load_structure().rooms
        by_id = {r.id: r for r in rooms}

        backup = store.make_backup_zip()                                           # 1. the safety net, before anything changes
        arch = store.root / "Archive" / label
        n = 1
        while arch.exists():
            n += 1; arch = store.root / "Archive" / f"{label}_{n}"
        arch.mkdir(parents=True)
        for f in YEAR_FILES:                                                       # 2. keep this year's records, then clear them
            if (store.root / f).exists():
                shutil.copy2(store.root / f, arch / f)
        lists = {r.id: store.load_students_full(r.id) for r in rooms}
        for rid, studs in lists.items():
            (arch / "rooms" / rid).mkdir(parents=True, exist_ok=True)
            with open(arch / "rooms" / rid / "students.csv", "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh); w.writerow(["Name", "English"]); w.writerows([[s["name"], s.get("english", "")] for s in studs])

        codes_path = self._codes_path()
        mapping = store.read_json(codes_path, {}) or {}
        new_lists: dict[str, list] = {r.id: [] for r in rooms}
        new_map = {k: v for k, v in mapping.items()}
        moved, removed, report = [], [], {"moved": 0, "left": 0, "graduated": 0, "elsewhere": 0}
        left_rows = []
        for r in rooms:
            nxt = self._next_of(r)
            for s in lists[r.id]:
                key = f"{r.id}|{s['name']}"
                if s["name"] in leaving.get(r.id, set()):
                    why = "left"
                elif nxt is None:
                    why = "graduated"
                else:
                    why = "moves" if nxt[1] in by_id else "elsewhere"
                if why in ("left", "graduated"):
                    report[why] += 1; left_rows.append([r.name, s["name"], why])
                    if key in new_map:
                        removed.append(new_map.pop(key)["student"])
                    continue
                if why == "moves":
                    new_lists[nxt[1]].append(s); report["moved"] += 1
                else:
                    report["elsewhere"] += 1                                       # a class this app does not have: the student leaves this teacher's lists
                if key in new_map:                                                 # the code stays, the class changes
                    entry = new_map.pop(key)
                    new_map[f"{nxt[1]}|{s['name']}"] = entry
                    moved.append({"code": entry["student"], "class_id": nxt[1], "grade_id": nxt[0]})
        with open(arch / "left_the_school.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh); w.writerow(["Class", "Name", "Why"]); w.writerows(left_rows)

        for f in YEAR_FILES:
            (store.root / f).unlink(missing_ok=True)
        for rid, studs in new_lists.items():                                       # 3. the new class lists
            store.save_students_full(rid, studs)
        if mapping:                                                                # 4. the parents' codes follow the students
            store.write_json(codes_path, new_map)
        empty = [by_id[rid].name for rid, studs in new_lists.items() if not studs]
        store.write_json(self._yearend_path(), {"label": label, "at": datetime.now().isoformat(timespec="seconds"), "archive": str(arch), "backup": str(backup),
                                                "server": {"moved": moved, "removed": removed, "done": False}})
        return {**report, "label": label, "archive": str(arch), "backup": str(backup), "empty": empty, "server_changes": len(moved) + len(removed), "server_moved": len(moved), "server_removed": len(removed)}

    def yearend_server_run(self, b: dict) -> dict:
        """Administration only, after the local end of the year: the school server follows.
        A backup of the server tables first; students move to their new class (the families stay linked); the students who left are deleted
        with their codes, links and marks; this year's marks, week plans and published files are cleared. Safe to run again if it stops half way."""
        if self._cloud_cfg()["role"] != "admin":
            raise AppError("cloud_admin_only", "Only the administration can do this.", status=403)
        if not b.get("confirm"):
            raise AppError("yearend_confirm", "Tick the box to confirm.", status=400)
        store = self._need_store()
        info = store.read_json(self._yearend_path(), {}) or {}
        srv = info.get("server")
        if not srv:
            raise AppError("yearend_first", "Do the end of the year on this computer first.", status=409)
        if srv.get("done") and not b.get("again"):
            raise AppError("yearend_done", "The school server was already updated.", status=409)
        backup = self.cloud_backup()                                                   # 1. the safety net
        c = self._cloud_client()
        by_class: dict[tuple[str, str], list[str]] = {}
        for m in srv.get("moved", []):
            by_class.setdefault((m["class_id"], m["grade_id"]), []).append(m["code"])
        for (class_id, grade_id), codes in by_class.items():                           # 2. the students move up; their codes stay
            for i in range(0, len(codes), 50):
                c.update("students", "code=in.(" + ",".join(codes[i:i + 50]) + ")", {"class_id": class_id, "grade_id": grade_id})
        gone = srv.get("removed", [])
        for i in range(0, len(gone), 50):                                              # 3. who left: codes, links, marks and chats go with the student
            c.delete("students", "code=in.(" + ",".join(gone[i:i + 50]) + ")")
        pubs = c.select("publications", "select=id,file_path&limit=5000")              # 4. the old year's published files, marks and week plans
        paths_ = sorted({p["file_path"] for p in pubs if p.get("file_path")})
        for p in paths_:
            c.remove_object("files", p)
        if pubs:
            c.delete("publications", "created_at=gte.1970-01-01T00:00:00Z")
        c.delete("week_plans", "trimester=gte.0")
        c.delete("grades", "trimester=gte.0")
        srv["done"] = True
        info["server"] = srv; info["server_at"] = datetime.now().isoformat(timespec="seconds")
        store.write_json(self._yearend_path(), info)
        return {"backup": backup["name"], "backup_path": backup["path"], "moved": len(srv.get("moved", [])), "removed": len(gone), "publications": len(pubs), "files": len(paths_)}
