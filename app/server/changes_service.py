"""Changes for ONE day only: cancel a lesson, move/swap lessons, or add a cover lesson for an absent colleague.
The normal timetable is never touched; the changes live in Timetable.overrides[date]."""
from __future__ import annotations

from datetime import date, timedelta

from ..core.errors import AppError
from ..core.models import WEEKDAYS


class ChangesMixin:
    def change_today(self, b: dict) -> dict:
        store = self._need_store()
        today = date.today()
        iso = today.isoformat()
        if str(b.get("date") or iso) != iso:
            raise AppError("today_only", "You can change today's lessons only.", status=400)
        action = str(b.get("action", ""))
        tt = self._with_fixed(store.load_timetable())
        names = [p.name for p in tt.periods]
        day = WEEKDAYS[today.weekday()]
        rooms = {r.id for r in store.load_structure().rooms}
        # forget old changes
        tt.overrides = {k: v for k, v in tt.overrides.items() if k >= (today - timedelta(days=14)).isoformat()}

        if action == "restore":
            tt.overrides.pop(iso, None)
            store.save_timetable(tt)
            return self.today(iso)

        ov = tt.overrides.setdefault(iso, {})
        ov["cancel"] = [str(x) for x in ov.get("cancel", [])]
        ov["extra"] = [dict(x) for x in ov.get("extra", [])]
        ov["cancel_duties"] = [str(x) for x in ov.get("cancel_duties", [])]
        if action in ("cancel_duty", "restore_duty"):
            kind = str(b.get("kind", ""))
            if kind not in ("break", "late"):
                raise AppError("invalid_data", "Unknown duty.")
            ov["cancel_duties"] = [x for x in ov["cancel_duties"] if x != kind] + ([kind] if action == "cancel_duty" else [])
            if not ov["cancel"] and not ov["extra"] and not ov["cancel_duties"]:
                tt.overrides.pop(iso, None)
            store.save_timetable(tt)
            return self.today(iso)

        def base(p):  # the normal lesson in period p, if not cancelled
            return "" if p in ov["cancel"] else (tt.grid.get(day, {}) or {}).get(p, "")

        def extra_at(p):
            return next((x for x in ov["extra"] if str(x.get("period")) == p), None)

        def room_at(p):
            e = extra_at(p)
            return e["room_id"] if e else base(p)

        def clear(p):
            if extra_at(p):
                ov["extra"] = [x for x in ov["extra"] if str(x.get("period")) != p]
            if (tt.grid.get(day, {}) or {}).get(p) and p not in ov["cancel"]:
                ov["cancel"].append(p)

        period = str(b.get("period", ""))
        if action != "restore" and period not in names:
            raise AppError("bad_period", "Choose a period.", status=400)

        if action == "cancel":
            if not room_at(period):
                raise AppError("no_session", "There is no lesson in that period.", status=409)
            clear(period)
        elif action == "uncancel":
            ov["cancel"] = [x for x in ov["cancel"] if x != period]
        elif action == "cover":
            room = str(b.get("room_id", ""))
            if room not in rooms:
                raise AppError("room_not_found", status=404)
            if room_at(period):
                raise AppError("period_busy", "You already have a lesson in that period.", status=409)
            ov["extra"].append({"period": period, "room_id": room, "kind": "cover", "note": " ".join(str(b.get("note", "")).split())[:80]})
        elif action == "move":
            to = str(b.get("to", ""))
            if to not in names or to == period:
                raise AppError("bad_period", "Choose another period.", status=400)
            ra, rb = room_at(period), room_at(to)
            if not ra:
                raise AppError("no_session", "There is no lesson in that period.", status=409)
            note = (extra_at(period) or {}).get("note", "")
            clear(period)
            clear(to)
            ov["extra"].append({"period": to, "room_id": ra, "kind": "moved", "note": note})
            if rb:  # swap
                ov["extra"].append({"period": period, "room_id": rb, "kind": "moved", "note": ""})
        else:
            raise AppError("invalid_data", "Unknown change.")

        if not ov["cancel"] and not ov["extra"] and not ov["cancel_duties"]:
            tt.overrides.pop(iso, None)
        store.save_timetable(tt)
        return self.today(iso)
