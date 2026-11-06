"""A quiet "there is a newer version" notice. The school decides where the newest version is announced (resources/school_server.json):
  "update_url":  an address that answers {"version": "1.0.2", "url": "https://...", "notes": "..."}  (a small file on the school's GitHub Pages is perfect)
  "update_repo": "owner/name" of a public GitHub repository that publishes releases (its latest release tag is read)
Nothing is sent about the teacher; it is one plain GET about once a day, it never blocks the app, and a failure is silent."""
from __future__ import annotations

import json
import re
import time
import urllib.request

from ..core import paths
from ..core.errors import AppError

CHECK_EVERY = 24 * 3600
RETRY_EVERY = 6 * 3600


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
        return {"version": version, "url": page, "notes": str(d.get("notes") or "")[:300]}

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
            return {**none, "available": True, "version": cache["version"], "url": cache["url"], "notes": cache.get("notes", "")}
        return none

    def dismiss_update(self, version: str) -> dict:
        paths.write_prefs(update_dismissed=str(version)[:20])
        return {"ok": True}

    def set_update_check(self, enabled: bool) -> dict:
        paths.write_prefs(update_check=bool(enabled))
        return {"enabled": bool(enabled)}
