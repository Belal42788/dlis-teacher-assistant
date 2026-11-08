"""Putting a backup back. The app keeps copies in three places (the weekly quiet copy, the copy made before an upgrade,
and the zip from "Back up now"); a teacher picks one from a list, never a file path. Before anything is touched, the
folder as it is right now is copied to _backup/before_restore, so a restore can itself be undone."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

from .errors import AppError
from .store import DATA_VERSION, DataStore

KINDS = (("auto", "_backup/auto", "DLIS_auto_*.zip"),
         ("upgrade", "_backup/before_upgrade", "DLIS_before_v*.zip"),
         ("restore", "_backup/before_restore", "DLIS_before_restore_*.zip"),
         ("manual", "Exports", "DLIS_backup_*.zip"))
MARKERS = {"config.json", "structure.json", "schedule.json", "calendar.json"}   # a real data folder has at least one


def _usable(path) -> bool:
    """Cheap check from the zip's table of contents: a copy made from an empty folder has nothing to put back."""
    try:
        with zipfile.ZipFile(path) as z:
            return bool({_safe_member(n) for n in z.namelist()} & MARKERS)
    except (OSError, zipfile.BadZipFile):
        return False


def list_backups(store: DataStore) -> list[dict]:
    """Newest first: [{"id": "_backup/auto/x.zip", "kind", "name", "size", "usable", "when"}]. The id is always inside the data folder."""
    rows = []
    for kind, folder, pattern in KINDS:
        for p in (store.root / folder).glob(pattern):
            try:
                st = p.stat()
            except OSError:
                continue
            rows.append({"id": f"{folder}/{p.name}", "kind": kind, "name": p.name, "size": st.st_size, "usable": _usable(p),
                         "when": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return sorted(rows, key=lambda r: r["when"], reverse=True)


def _safe_member(name: str) -> str | None:
    """The path inside the folder, or None when it must not be written (outside the folder, a backup of backups, a leftover)."""
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]) or not p.parts:
        return None
    if p.parts[0] in ("_backup", "Exports") or p.name.endswith(".tmp"):
        return None
    return p.as_posix()


def check_backup(store: DataStore, backup_id: str):
    """Opens the chosen zip and proves it is a DLIS folder from this app or an older one. Returns (path, members)."""
    known = {r["id"]: r for r in list_backups(store)}
    if backup_id not in known:
        raise AppError("backup_unknown", "That backup is not in the list.", status=404)
    path = store.root / backup_id
    try:
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise AppError("backup_damaged", "This backup file is damaged.", status=422)
            members = [(m, _safe_member(m.filename)) for m in z.infolist() if not m.is_dir()]
            members = [(m, rel) for m, rel in members if rel]
            names = {rel for _, rel in members}
            if not names & MARKERS:
                raise AppError("backup_not_dlis", "This file does not look like a DLIS data backup.", status=422)
            if "data_version.json" in names:
                try:
                    v = json.loads(z.read("data_version.json").decode("utf-8-sig")).get("data_version", 1)
                except (ValueError, AttributeError):
                    v = 1
                if isinstance(v, int) and v > DATA_VERSION:
                    raise AppError("backup_newer", "This backup was made by a newer version of the app.", status=409)
    except zipfile.BadZipFile as e:
        raise AppError("backup_damaged", "This backup file is damaged.", status=422) from e
    return path, [rel for _, rel in members]


def restore(store: DataStore, backup_id: str) -> dict:
    """Copies the folder aside, then writes every file of the backup over the current ones.
    Files that were made after the backup are kept (nothing is deleted), so nothing is lost by choosing the wrong date."""
    if store.locked:
        raise AppError("data_locked", "This data folder cannot be changed by this version of the app.", status=409, why=store.locked)
    path, names = check_backup(store, backup_id)
    names = set(names)
    with store._lock:
        stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        safety = store.backup_root() / "before_restore" / f"DLIS_before_restore_{stamp}.zip"
        safety.parent.mkdir(parents=True, exist_ok=True)
        n = 1
        while safety.exists():      # two restores in the same second must never overwrite the copy being restored from
            n += 1
            safety = safety.with_name(f"DLIS_before_restore_{stamp}_{n}.zip")
        store._zip_to(safety)
        count = 0
        with zipfile.ZipFile(path) as z:
            for m in z.infolist():
                rel = None if m.is_dir() else _safe_member(m.filename)
                if not rel:
                    continue
                dest = store.root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".tmp")
                tmp.write_bytes(z.read(m))
                store._replace(tmp, dest)
                count += 1
        if "data_version.json" not in names:
            (store.root / "data_version.json").unlink(missing_ok=True)   # a backup from before version numbers existed: the next open reads it as version 1
    return {"restored": count, "safety": safety.name, "from": path.name}
