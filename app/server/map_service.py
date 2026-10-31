"""School map: floors with rooms drawn on a grid. Each room has a kind, notes and (for offices) a contact person and phone.
The whole map lives in one file in the data folder (map.json); a ready-made one can ship as resources/school_map.json."""
from __future__ import annotations

import json
import re
import uuid

from ..core import paths
from ..core.errors import AppError

KINDS = ("class", "lab", "office", "admin", "facility", "other")
GRID_W, GRID_H = 24, 14
WINGS = ("left", "center", "right")
# The building is a wide "V" turned upside down: two class wings and an administrative block in the middle.
# Rooms are drawn in list order inside their wing, so the order of the list is the order on the map.
VERSION = 2


def default_wing(name: str, x: int, w: int) -> str:
    return "left" if x + w / 2 < 12 else "right"


def _s(x, n: int) -> str:
    return " ".join(str(x or "").split())[:n]


def _int(x, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(x)))
    except (TypeError, ValueError):
        return default


def clean_map(data) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("floors", []), list):
        raise ValueError("bad map")
    floors, seen = [], set()
    for f in data.get("floors", [])[:12]:
        if not isinstance(f, dict):
            continue
        rooms = []
        for r in (f.get("rooms") or [])[:200]:
            if not isinstance(r, dict):
                continue
            w, h = _int(r.get("w"), 1, GRID_W, 3), _int(r.get("h"), 1, GRID_H, 3)
            rid = str(r.get("id") or "")
            if not re.fullmatch(r"[a-z0-9]{6,32}", rid) or rid in seen:
                rid = uuid.uuid4().hex[:10]
            seen.add(rid)
            rooms.append({"id": rid, "name": _s(r.get("name"), 60) or "?", "kind": r.get("kind") if r.get("kind") in KINDS else "other",
                          "x": _int(r.get("x"), 0, GRID_W - w, 0), "y": _int(r.get("y"), 0, GRID_H - h, 0), "w": w, "h": h,
                          "room_id": _s(r.get("room_id"), 40), "notes": str(r.get("notes") or "").strip()[:600],
                          "person": _s(r.get("person"), 80), "phone": _s(r.get("phone"), 40),
                          "wing": r.get("wing") if r.get("wing") in WINGS else default_wing(_s(r.get("name"), 60), _int(r.get("x"), 0, GRID_W - w, 0), w)})
        fid = str(f.get("id") or "")
        if not re.fullmatch(r"[a-z0-9]{4,32}", fid) or fid in seen:
            fid = uuid.uuid4().hex[:8]
        seen.add(fid)
        floors.append({"id": fid, "name": _s(f.get("name"), 40) or "Floor", "rooms": rooms})
    return {"floors": floors, "version": VERSION}


class MapMixin:
    def _map_path(self):
        return self._need_store().root / "map.json"

    def _seed_map(self) -> dict:
        seed = paths.resources_dir() / "school_map.json"
        return json.loads(seed.read_text(encoding="utf-8")) if seed.is_file() else {"floors": []}

    def get_map(self) -> dict:
        store = self._need_store()
        data = store.read_json(self._map_path(), None, check=clean_map)
        if data is None:
            data = self._seed_map()
        elif int(data.get("version") or 1) < VERSION:
            # old drawing (before the inverted-V building): take the new building and keep what was typed about each room
            old = {(r["name"] or "").lower(): r for f in data.get("floors", []) for r in f.get("rooms", [])}
            data = self._seed_map()
            for f in data["floors"]:
                for r in f["rooms"]:
                    o = old.get(r["name"].lower())
                    if o:
                        for k in ("room_id", "notes", "person", "phone"):
                            if o.get(k):
                                r[k] = o[k]
            store.write_json(self._map_path(), clean_map(data))
        return {**clean_map(data), "grid": [GRID_W, GRID_H], "kinds": list(KINDS), "wings": list(WINGS)}

    def put_map(self, b: dict) -> dict:
        try:
            data = clean_map(b)
        except ValueError:
            raise AppError("bad_value", "The map is not in the right shape.", status=400)
        self._need_store().write_json(self._map_path(), data)
        return self.get_map()
