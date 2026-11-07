"""Run before a release is built: is everything that carries the version number saying the same thing?
    python scripts/check_release.py v1.0.1          (the release workflow runs this first; run it yourself before you make a release)
It reads the files as plain text, so it needs nothing installed. Exit code 0 = ready, 1 = a list of what to fix."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def problems(tag: str, root: Path = ROOT) -> list[str]:
    out: list[str] = []
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag or ""):
        return [f'The release name must look like v1.0.1 (it is "{tag}").']
    want = tag[1:]
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', (root / "app/core/paths.py").read_text(encoding="utf-8"), re.M)
    app_v = m.group(1) if m else ""
    if app_v != want:
        out.append(f'The app says version {app_v or "?"} (app/core/paths.py) but the release is {want}. Change VERSION there.')
    m = re.search(r'#define AppVersion "([^"]+)"', (root / "installer/dlis.iss").read_text(encoding="utf-8"))
    if not m or m.group(1) != want:
        out.append(f'The Windows installer says {m.group(1) if m else "?"} (installer/dlis.iss) but the release is {want}.')
    try:
        notes = json.loads((root / "resources/whats_new.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        notes = {}
    entry = notes.get(want) if isinstance(notes, dict) else None
    if not (isinstance(entry, dict) and entry.get("ar") and entry.get("en")):
        out.append(f'resources/whats_new.json has no "{want}" entry (needs a list in "ar" and a list in "en"). It is the "What is new" window teachers see after the update.')
    try:
        json.loads((root / "portal/latest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out.append("portal/latest.json is missing or is not valid JSON.")
    return out


if __name__ == "__main__":
    bad = problems(sys.argv[1] if len(sys.argv) > 1 else "")
    for line in bad:
        print("PROBLEM:", line)
    print("Ready to release." if not bad else f"{len(bad)} problem(s).")
    sys.exit(1 if bad else 0)
