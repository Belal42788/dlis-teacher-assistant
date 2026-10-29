"""Where things live on this computer (not in the synced data folder)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "DLIS Teacher Assistant"
VERSION = "1.0.0"


def app_support_dir() -> Path:
    """Per-computer folder for tiny local preferences (data folder location, language)."""
    override = os.environ.get("DLIS_APP_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        p = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def bundle_root() -> Path:
    """Folder that contains `app/` and `resources/` (works inside a PyInstaller exe too)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def web_dir() -> Path:
    return bundle_root() / "app" / "web"


def resources_dir() -> Path:
    return bundle_root() / "resources"


def default_data_folder() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.exists() else Path.home()) / APP_NAME


# ---- local preferences (language + where the data folder is) ----

def _prefs_path() -> Path:
    return app_support_dir() / "local_prefs.json"


def read_prefs() -> dict:
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_prefs(**changes) -> dict:
    prefs = read_prefs()
    prefs.update({k: v for k, v in changes.items()})
    tmp = _prefs_path().with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _prefs_path())
    return prefs


def bell_schedule() -> dict:
    """The school's fixed period times, break duty and late duty (same for every teacher)."""
    import json
    return json.loads((resources_dir() / "bell_schedule.json").read_text(encoding="utf-8"))


def log_error(text: str) -> None:
    """Append to error.log (a windowed .exe has no console, so printing would itself fail)."""
    try:
        from datetime import datetime

        log = app_support_dir() / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 200_000:
            log.write_text("", encoding="utf-8")
        with log.open("a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
    except Exception:
        pass
