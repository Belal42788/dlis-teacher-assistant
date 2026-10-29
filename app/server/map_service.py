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
                          "person": _s(r.get("person"), 80), "phone": _s(r.get("phone"), 40)})
        fid = str(f.get("id") or "")
        if not re.fullmatch(r"[a-z0-9]{4,32}", fid) or fid in seen:
            fid = uuid.uuid4().hex[:8]
        seen.add(fid)
        floors.append({"id": fid, "name": _s(f.get("name"), 40) or "Floor", "rooms": rooms})
    return {"floors": floors}


class MapMixin:
    def _map_path(self):
        return self._need_store().root / "map.json"

    def get_map(self) -> dict:
        store = self._need_store()
        data = store.read_json(self._map_path(), None, check=clean_map)
        if data is None:
            seed = paths.resources_dir() / "school_map.json"
            data = json.loads(seed.read_text(encoding="utf-8")) if seed.is_file() else {"floors": []}
        return {**clean_map(data), "grid": [GRID_W, GRID_H], "kinds": list(KINDS)}

    def put_map(self, b: dict) -> dict:
        try:
            data = clean_map(b)
        except ValueError:
            raise AppError("bad_value", "The map is not in the right shape.", status=400)
        self._need_store().write_json(self._map_path(), data)
        return self.get_map()
