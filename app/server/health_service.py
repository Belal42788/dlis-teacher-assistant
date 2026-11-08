"""The "App health" panel in Settings: what the app is running on, how the data folder is doing, the backups that exist
(with a restore button), and the last errors. Nothing here leaves the computer; "copy report" is for the teacher to paste to IT."""
from __future__ import annotations

import shutil
import sys

from ..core import paths, restore
from ..core.store import DATA_VERSION, DataStore


def _mb(n: int) -> float:
    return round(n / (1024 * 1024), 1)


class HealthMixin:
    def health(self) -> dict:
        store = self._need_store()
        size = files = 0
        for p in store.root.rglob("*"):
            if p.is_file() and store.backup_root() not in p.parents and store.exports_dir() not in p.parents:
                files += 1
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
        rooms = students = 0
        for f in (store.root / "rooms").glob("*/students.csv"):
            rooms += 1
            try:
                students += max(0, len([x for x in f.read_text(encoding="utf-8-sig").splitlines() if x.strip()]) - 1)
            except OSError:
                pass
        log = paths.app_support_dir() / "error.log"
        try:
            errors = [x for x in log.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()][-8:] if log.is_file() else []
        except OSError:
            errors = []
        try:
            free = _mb(shutil.disk_usage(store.root).free)
        except OSError:
            free = None
        backups = restore.list_backups(store)
        use = paths.read_prefs().get("usage") or {}
        opens = {k: int(v) for k, v in (use.get("pages") or {}).items() if k in self.PAGE_IDS}
        return {
            "app_version": paths.VERSION, "platform": sys.platform, "data_version": store._stored_version() or DATA_VERSION,
            "latest_data_version": DATA_VERSION, "locked": store.locked, "data_folder": str(store.root),
            "folder_mb": _mb(size), "free_mb": free, "files": files, "rooms": rooms, "students": students,
            "problems": list(store.problems), "errors": errors,
            "last_auto_backup": next((b["when"] for b in backups if b["kind"] == "auto"), ""),
            "backups": backups[:30],
            "usage": {"since": use.get("since") or "", "pages": opens, "never": [k for k in self.PAGE_IDS if not opens.get(k)]},
        }

    def backup_restore(self, b: dict) -> dict:
        """Puts the chosen backup back, then re-opens the folder (so an older backup is upgraded the normal, safe way)."""
        store = self._need_store()
        out = restore.restore(store, str(b.get("id", "")))
        self.store = DataStore(store.root)
        return {**out, "data_locked": self.store.locked}
