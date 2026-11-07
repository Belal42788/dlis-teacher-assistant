"""Rewrites the parts of docs/DEVELOPER.md that can be read straight from the code (routes, feature files, pages, data files),
so the guide cannot drift away from the program.   python scripts/make_dev_docs.py          (a test fails when they are out of date)"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "DEVELOPER.md"


def routes() -> str:
    text = (ROOT / "app/server/http.py").read_text(encoding="utf-8")
    rows = ["| Method | Route | Service method |", "|---|---|---|"]
    for m in re.finditer(r'\("(GET|POST|PUT|DELETE)", r"([^"]+)", (.*)\),?\s*$', text, re.M):
        call = re.search(r"svc\.(\w+)", m.group(3))
        rows.append(f"| {m.group(1)} | `{m.group(2)}` | {('`' + call.group(1) + '`') if call else ''} |")
    return "\n".join(rows)


def features() -> str:
    svc = (ROOT / "app/server/service.py").read_text(encoding="utf-8")
    bases = re.search(r"class Service\(([^)]*)\)", svc).group(1).replace("\n", " ").split(",")
    by_class = {}   # class name -> file, from every "from .file import A, B" line
    for f, names in re.findall(r"from \.(\w+) import ([^\n]+)", svc):
        for c in names.split(","):
            by_class[c.strip()] = f
    rows = ["| Mixin | File | Lines |", "|---|---|---|"]
    for b in (x.strip() for x in bases):
        f = by_class.get(b)
        if f:
            n = len((ROOT / "app/server" / f"{f}.py").read_text(encoding="utf-8").splitlines())
            rows.append(f"| `{b}` | `app/server/{f}.py` | {n} |")
    return "\n".join(rows)


def pages() -> str:
    text = (ROOT / "app/web/js/main.js").read_text(encoding="utf-8")
    top, tabs = [], []
    for m in re.finditer(r'^  \{ id: "(\w+)"([^\n]*)\},?$', text, re.M):
        inside = re.search(r'nav: "(\w+)"', m.group(2))
        (tabs if inside else top).append(f"`{m.group(1)}`" + (f" (tab of `{inside.group(1)}`)" if inside else ""))
    return "Menu pages: " + ", ".join(top) + ".\n\nTabs inside a menu page: " + ", ".join(tabs) + "."


def data_files() -> str:
    names = set()
    for p in list((ROOT / "app").rglob("*.py")):
        for m in re.finditer(r'(?:root|store\.root|self\.root)\s*/\s*"([\w.-]+\.json)"', p.read_text(encoding="utf-8")):
            names.add(m.group(1))
    return ", ".join(f"`{n}`" for n in sorted(names)) + " (plus `data_version.json`, written by the store)."


SECTIONS = {"routes": routes, "features": features, "pages": pages, "datafiles": data_files}


def render(doc: str) -> str:
    for key, fn in SECTIONS.items():
        pat = re.compile(rf"(<!-- AUTO:{key} -->\n)(?:.*?\n)?(<!-- /AUTO:{key} -->)", re.S)
        if not pat.search(doc):
            raise SystemExit(f"DEVELOPER.md has no AUTO:{key} block")
        doc = pat.sub(lambda m: m.group(1) + fn() + "\n" + m.group(2), doc)
    return doc


if __name__ == "__main__":
    old = DOC.read_text(encoding="utf-8")
    new = render(old)
    if "--check" in sys.argv:
        sys.exit(0 if old == new else 1)
    DOC.write_text(new, encoding="utf-8")
    print("DEVELOPER.md updated" if old != new else "DEVELOPER.md already up to date")
