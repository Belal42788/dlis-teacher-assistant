"""Writes portal/latest.json, the small file every installed app asks "is there a newer version?".
The release workflow runs it after the installers are attached:
    python scripts/write_latest.py v1.0.1 https://github.com/OWNER/REPO/releases/tag/v1.0.1 --notes-file notes.txt"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clean_notes(text: str, limit: int = 300) -> str:
    """The first lines of the release description as one calm sentence or two (no markdown marks)."""
    text = re.sub(r"[#*`>_]+|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def write(tag: str, url: str, notes: str, root: Path = ROOT) -> dict:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"bad release name: {tag}")
    if not url.startswith("https://"):
        raise ValueError("the release address must start with https://")
    data = {"version": tag[1:], "url": url, "notes": clean_notes(notes)}
    (root / "portal").mkdir(exist_ok=True)
    (root / "portal/latest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("url")
    ap.add_argument("--notes-file", default="")
    a = ap.parse_args()
    body = Path(a.notes_file).read_text(encoding="utf-8") if a.notes_file and Path(a.notes_file).is_file() else ""
    print(json.dumps(write(a.tag, a.url, body), ensure_ascii=False))
    sys.exit(0)
