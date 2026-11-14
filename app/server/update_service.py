"""A quiet "there is a newer version" notice. The school decides where the newest version is announced (resources/school_server.json):
  "update_url":  an address that answers {"version": "1.0.2", "url": "https://...", "notes": "..."}  (a small file on the school's GitHub Pages is perfect)
  "update_repo": "owner/name" of a public GitHub repository that publishes releases (its latest release tag is read)
Nothing is sent about the teacher; it is one plain GET about once a day, it never blocks the app, and a failure is silent."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from ..core import paths
from ..core.errors import AppError

CHECK_EVERY = 24 * 3600
RETRY_EVERY = 6 * 3600
MAX_INSTALLER = 600 * 1024 * 1024
_ASSET_URL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/releases/download/[\w.+-]+/[\w. +-]{3,120}$")   # only a GitHub release file is ever downloaded
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _platform() -> str:
    return "windows" if sys.platform == "win32" else "mac" if sys.platform == "darwin" else ""


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))   # a program run from the source folder is updated by replacing the folder, not by an installer


def clean_asset(a) -> dict | None:
    """{"url", "sha256", "size"} for an installer file, or None. Without the sha256 nothing is installed: the download could not be checked."""
    if not isinstance(a, dict):
        return None
    url, sha, size = str(a.get("url") or ""), str(a.get("sha256") or "").lower().removeprefix("sha256:"), a.get("size")
    if not _ASSET_URL.match(url) or not _SHA.match(sha) or not isinstance(size, int) or not 0 < size <= MAX_INSTALLER:
        return None
    return {"url": url, "sha256": sha, "size": size}


def _parts(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


def is_newer(candidate: str, current: str) -> bool:
    a, b = _parts(candidate), _parts(current)
    return bool(a) and a > b


class UpdateMixin:
    def _update_sources(self) -> dict:
        f = paths.resources_dir() / "school_server.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        except ValueError:
            d = {}
        return d if isinstance(d, dict) else {}

    def _fetch_update(self, src: dict) -> dict | None:
        url = str(src.get("update_url") or "")
        repo = str(src.get("update_repo") or "")
        if not url and re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            url = f"https://api.github.com/repos/{repo}/releases/latest"
        if not url.startswith("https://"):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": f"DLIS-Teacher-Assistant/{paths.VERSION}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read(200_000).decode("utf-8"))
        version = str(d.get("version") or d.get("tag_name") or "").lstrip("vV")
        page = str(d.get("url") or d.get("html_url") or "")
        if not version or not page.startswith("https://"):
            return None
        out = {"version": version, "url": page, "notes": str(d.get("notes") or "")[:300]}
        assets = {k: clean_asset(d.get(k)) for k in ("windows", "mac")}
        for a in d.get("assets") or []:   # the GitHub release itself: the Windows .exe and the Mac .dmg
            if isinstance(a, dict) and str(a.get("name", "")).lower().endswith((".exe", ".dmg")):
                key = "windows" if str(a["name"]).lower().endswith(".exe") else "mac"
                assets[key] = assets[key] or clean_asset({"url": a.get("browser_download_url"), "sha256": a.get("digest"), "size": a.get("size")})
        return {**out, **{k: v for k, v in assets.items() if v}}

    def check_update(self) -> dict:
        prefs = paths.read_prefs()
        none = {"available": False, "enabled": prefs.get("update_check") is not False}
        src = self._update_sources()
        if not none["enabled"] or not (src.get("update_url") or src.get("update_repo")):
            return none
        cache = prefs.get("update") if isinstance(prefs.get("update"), dict) else {}
        age = time.time() - float(cache.get("at") or 0)
        if age > (CHECK_EVERY if cache.get("ok") else RETRY_EVERY):
            try:
                found = self._fetch_update(src)
                cache = {"at": time.time(), "ok": bool(found), **(found or {})}
            except Exception:   # offline, a school firewall, a private repository: just no notice
                cache = {"at": time.time(), "ok": False}
            paths.write_prefs(update=cache)
        if cache.get("ok") and is_newer(cache.get("version", ""), paths.VERSION) and prefs.get("update_dismissed") != cache.get("version"):
            self._update_url = cache["url"]
            return {**none, "available": True, "version": cache["version"], "url": cache["url"], "notes": cache.get("notes", ""),
                    "install": bool(_frozen() and _platform() and clean_asset(cache.get(_platform())))}
        return none

    # ---------------------------------------------------------------- "Download and install" from inside the app
    _upd_job: dict = {"state": "idle", "done": 0, "total": 0, "error": ""}

    def _open_download(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": f"DLIS-Teacher-Assistant/{paths.VERSION}"})
        return urllib.request.urlopen(req, timeout=30)

    def _update_asset(self) -> tuple[dict, str]:
        cache = paths.read_prefs().get("update")
        cache = cache if isinstance(cache, dict) else {}
        asset = clean_asset(cache.get(_platform())) if _platform() else None
        if not (_frozen() and asset and cache.get("ok") and is_newer(cache.get("version", ""), paths.VERSION)):
            raise AppError("update_unsupported", "This copy of the program cannot install updates by itself. Use «Get it» to open the download page.", status=400)
        return asset, str(cache["version"])

    def update_install(self) -> dict:
        """Start downloading the installer in the background (progress: update_progress). Nothing runs until it is fully downloaded and checked."""
        asset, version = self._update_asset()
        if self._upd_job.get("state") == "downloading":
            return dict(self._upd_job)
        job = {"state": "downloading", "done": 0, "total": asset["size"], "error": "", "version": version}
        self._upd_job = job
        folder = paths.app_support_dir() / "update"
        threading.Thread(target=self._download_installer, args=(job, asset, folder), daemon=True).start()
        return dict(job)

    def _download_installer(self, job: dict, asset: dict, folder) -> None:
        part = None
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.iterdir():
                if old.is_file():
                    old.unlink(missing_ok=True)
            dest = folder / asset["url"].rsplit("/", 1)[1]
            part = dest.with_name(dest.name + ".part")
            sha = hashlib.sha256()
            with self._open_download(asset["url"]) as r, open(part, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    job["done"] += len(chunk)
                    if job["done"] > asset["size"]:
                        raise ValueError("bigger than announced")
                    sha.update(chunk)
                    f.write(chunk)
            if job["done"] != asset["size"] or sha.hexdigest() != asset["sha256"]:
                raise ValueError("the file is not the one that was announced")
            part.replace(dest)
            job.update(state="ready", path=str(dest))
        except ValueError:
            job.update(state="error", error="update_bad_file")
        except Exception:   # offline, a school firewall, a full disk
            job.update(state="error", error="update_download_failed")
        finally:
            if job["state"] != "ready" and part is not None:
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass

    def update_progress(self) -> dict:
        return {k: v for k, v in self._upd_job.items() if k != "path"}

    def update_launch(self) -> dict:
        """Run the downloaded installer. On Windows the program closes itself so the installer can replace it, and the new version opens when it is done."""
        job = self._upd_job
        if job.get("state") != "ready" or not job.get("path") or not os.path.isfile(job["path"]):
            raise AppError("update_unsupported", "The new version has not been downloaded yet.", status=400)
        if _platform() == "windows":
            subprocess.Popen([job["path"], "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"], close_fds=True, creationflags=0x00000008 | 0x00000200)   # detached, so it outlives this program
            threading.Timer(1.5, self._quit_for_update).start()
            return {"ok": True, "quits": True}
        subprocess.Popen(["open", job["path"]])   # the Mac disk image opens: drag the program into Applications
        return {"ok": True, "quits": False}

    def _quit_for_update(self) -> None:
        hook = getattr(self, "quit_hook", None)
        if hook:
            try:
                hook()
            except Exception:
                pass
        threading.Timer(6.0, lambda: os._exit(0)).start()   # if the window did not close, the installer still must not wait for ever

    def dismiss_update(self, version: str) -> dict:
        paths.write_prefs(update_dismissed=str(version)[:20])
        return {"ok": True}

    def set_update_check(self, enabled: bool) -> dict:
        paths.write_prefs(update_check=bool(enabled))
        return {"enabled": bool(enabled)}

    # ---------------------------------------------------------------- "What is new" after an update
    def _whats_new_all(self) -> list[dict]:
        """Every written release note up to this version, newest first: [{"version", "ar": [...], "en": [...]}]."""
        f = paths.resources_dir() / "whats_new.json"
        try:
            notes = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(notes, dict):
            return []
        mine = _parts(paths.VERSION)
        rows = [(_parts(v), v, e) for v, e in notes.items() if isinstance(e, dict) and _parts(v) and _parts(v) <= mine]
        rows.sort(reverse=True)
        return [{"version": v, "ar": list(e.get("ar") or []), "en": list(e.get("en") or [])} for _, v, e in rows]

    def whats_new(self, everything: bool = False) -> dict:
        """`everything`: the last three releases (the "What is new" button in Settings). Otherwise only what the teacher has not seen yet."""
        rows = self._whats_new_all()
        if everything:
            return {"entries": rows[:3]}
        seen = _parts(paths.read_prefs().get("seen_version") or "")
        return {"entries": [r for r in rows if _parts(r["version"]) > seen][:3]}

    def stamp_first_run(self) -> None:
        """A brand-new install has nothing "new" to show: remember this version before any folder is chosen."""
        prefs = paths.read_prefs()
        if not prefs.get("seen_version") and not prefs.get("data_folder"):
            paths.write_prefs(seen_version=paths.VERSION)

    def mark_whats_new_seen(self) -> dict:
        paths.write_prefs(seen_version=paths.VERSION)
        return {"ok": True}
