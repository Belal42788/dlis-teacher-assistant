"""Before you build the program for a school: are its server settings safe and sane?
    python scripts/school_check.py            (reads resources/school_server.json and portal/config.js)
The program is sold per school, and you edit those two files for each one. The classic mistake is pasting the SECRET
key (service_role / sb_secret_) instead of the public one: it would then ship inside every teacher's installer.
Exit code 0 = fine (warnings are only reminders), 1 = fix the errors first. The Build and Release workflows run it."""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.([A-Za-z0-9_-]{5,})\.[A-Za-z0-9_-]{5,}")


def _role(token: str) -> str:
    m = JWT.fullmatch(token.strip())
    if not m:
        return ""
    try:
        payload = m.group(1) + "=" * (-len(m.group(1)) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("role", ""))
    except (ValueError, TypeError):
        return "?"


def check_key(key: str, where: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    key = (key or "").strip()
    if not key:
        return out
    if key.startswith("sb_secret_") or _role(key) == "service_role":
        out.append(("error", f"{where}: this is the SECRET key. Use the public one (anon / publishable). A secret key inside the program lets anyone read and change everything."))
    elif key.startswith("sb_publishable_") or _role(key) == "anon":
        pass
    else:
        out.append(("error", f"{where}: this does not look like a Supabase public key (it should start with eyJ… or sb_publishable_…)."))
    return out


def problems(root: Path = ROOT) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        cfg = json.loads((root / "resources/school_server.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return [("error", "resources/school_server.json is missing or is not valid JSON.")]
    url, key, school = (str(cfg.get(k) or "").strip() for k in ("url", "key", "school"))
    if bool(url) != bool(key):
        out.append(("error", "resources/school_server.json: fill both url and key, or leave both empty."))
    if url and not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co/?", url):
        out.append(("error", f"resources/school_server.json: url should look like https://abcdxyz.supabase.co (it is {url!r})."))
    out += [(lvl, txt) for lvl, txt in check_key(key, "resources/school_server.json key")]
    for field in ("update_url",):
        v = str(cfg.get(field) or "").strip()
        if v and not v.startswith("https://"):
            out.append(("error", f"resources/school_server.json: {field} must start with https://"))
    repo = str(cfg.get("update_repo") or "").strip()
    if repo and not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repo):
        out.append(("error", "resources/school_server.json: update_repo should look like owner/name."))
    if len(school) > 80:
        out.append(("error", "resources/school_server.json: school is too long (80 letters at most)."))
    portal = root / "portal/config.js"
    if portal.is_file():
        text = portal.read_text(encoding="utf-8")
        pk = re.search(r'key:\s*"([^"]*)"', text)
        pu = re.search(r'url:\s*"([^"]*)"', text)
        out += check_key(pk.group(1) if pk else "", "portal/config.js key")
        if url and pu and pu.group(1).strip() and pu.group(1).strip().rstrip("/") != url.rstrip("/"):
            out.append(("error", "portal/config.js and resources/school_server.json point at different Supabase projects."))
        if url and pu and not pu.group(1).strip():
            out.append(("warning", "The program has a server but portal/config.js is still empty: the parents' page will not work."))
    # a secret key hidden anywhere else that ships
    for folder in ("resources", "portal"):
        for f in (root / folder).rglob("*"):
            if f.is_file() and f.suffix in (".json", ".js", ".html", ".txt", ".md"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"sb_secret_[A-Za-z0-9_]{10,}", text) or any(_role(m.group(0)) == "service_role" for m in JWT.finditer(text)):
                    out.append(("error", f"{f.relative_to(root).as_posix()} contains a SECRET Supabase key. Remove it."))
    if not url:
        out.append(("warning", "No server is set: this build has no school server (announcements, parents' page, online backup are off)."))
    if not school and url:
        out.append(("warning", "resources/school_server.json: school name is empty."))
    return out


if __name__ == "__main__":
    found = problems()
    for lvl, txt in found:
        print(f"{lvl.upper()}: {txt}")
    errors = [x for x in found if x[0] == "error"]
    print("OK for this school." if not errors else f"{len(errors)} error(s): fix them before building.")
    sys.exit(1 if errors else 0)
