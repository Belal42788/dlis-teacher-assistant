"""Bring in the students of the whole school from one file (every row says the class), in one step."""
import base64

from ..core.errors import AppError
from ..core.school_students import group_by_room, parse_school_rows, rows_of
from ..core.upload_check import check_document


class SchoolStudentsMixin:
    def _school_items(self, b: dict):
        raw = b""
        if b.get("data_b64"):
            try:
                raw = base64.b64decode(b["data_b64"])
            except ValueError as e:
                raise AppError("file_unreadable", status=400) from e
            if len(raw) > 5 * 1024 * 1024:
                raise AppError("file_too_big", "The file is too big for a list of students.", status=400)
            if not str(b.get("filename", "")).lower().endswith(".xls") or raw.lstrip()[:1] != b"<":
                check_document(str(b.get("filename", "")), raw)
        items = parse_school_rows(rows_of(str(b.get("filename", "")), raw, str(b.get("text", ""))))
        groups, unknown = group_by_room(items)
        if not groups:
            raise AppError("school_students_none", "No students with a class were found in this file.", status=400)
        return groups, unknown

    def students_all_preview(self, b: dict) -> dict:
        groups, unknown = self._school_items(b)
        store = self._need_store()
        have = {r.id for r in store.load_structure().rooms}
        classes = []
        for (g, letter), studs in sorted(groups.items(), key=lambda kv: (_order(kv[0][0]), kv[0][1])):
            rid = f"{g}-{letter}"
            classes.append({"room_id": rid, "name": _name(g, letter), "count": len({n.casefold() for n, _ in studs}),
                            "english": sum(1 for _, e in studs if e), "in_app": rid in have})
        return {"classes": classes, "unknown": unknown, "students": sum(c["count"] for c in classes), "new_classes": sum(1 for c in classes if not c["in_app"])}

    def students_all_import(self, b: dict) -> dict:
        groups, unknown = self._school_items(b)
        store = self._need_store()
        add_classes, replace = bool(b.get("add_classes")), b.get("replace", True) is not False
        have = {r.id for r in store.load_structure().rooms}
        want = {f"{g}-{letter}": (g, letter) for g, letter in groups}
        if add_classes and set(want) - have:
            sel: dict = {}
            for rid, (g, letter) in want.items():
                if rid not in have:
                    sel.setdefault(g, []).append(letter.upper())
            self.build_structure(sel)
            have = {r.id for r in store.load_structure().rooms}
        done, skipped, total, english = 0, [], 0, 0
        for (g, letter), studs in groups.items():
            rid = f"{g}-{letter}"
            if rid not in have:
                skipped.append({"name": _name(g, letter), "count": len(studs)})
                continue
            names = [n for n, _ in studs]; en = [e or None for _, e in studs]
            if not replace:                                           # keep the class as it is and add the students it does not have
                cur = store.load_students_full(rid)
                known = {x["name"].casefold() for x in cur}
                names = [x["name"] for x in cur] + [n for n in names if n.casefold() not in known]
                en = [x["english"] or None for x in cur] + [e for (n, _), e in zip(studs, en) if n.casefold() not in known]
            r = self.put_students(rid, names, en)
            done += 1; total += len(r["names"]); english += sum(1 for e in r["english"] if e)
        return {"rooms": done, "students": total, "english": english, "skipped": skipped, "unknown": unknown}


def _order(gid: str) -> int:
    from ..core.presets import GRADE_PRESET_BY_ID
    return GRADE_PRESET_BY_ID.get(gid, {}).get("order", 99)


def _name(gid: str, letter: str) -> str:
    from ..core.presets import GRADE_PRESET_BY_ID
    return f"{GRADE_PRESET_BY_ID[gid]['name']} {letter.upper()}"
