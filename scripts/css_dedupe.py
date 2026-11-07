"""Finds (and with --fix removes) CSS declarations that can never apply: the same selector is written again LATER in the file
with the same property, so the earlier one is always overridden. Only top-level rules; shorthand/longhand pairs are left alone.
  python scripts/css_dedupe.py          report, exit 1 if there are any
  python scripts/css_dedupe.py --fix    remove them"""
import collections
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app" / "web" / "css" / "style.css"


def top_level(text):
    """[(start, end_of_prelude, body_start, body_end)] for every top-level {} block (comments are skipped)."""
    out, depth, i, n, prelude_start, body_start = [], 0, 0, len(text), 0, 0
    while i < n:
        c = text[i]
        if text.startswith("/*", i):
            i = text.find("*/", i) + 2
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            if depth == 0:
                body_start = i + 1
                pre_end = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append((prelude_start, pre_end, body_start, i))
                prelude_start = i + 1
        i += 1
    return out


def declarations(body, offset):
    """[(prop, start, end, important)] with absolute positions; end includes the trailing ';'."""
    res, i, n, start, paren, quote = [], 0, len(body), 0, 0, ""
    while i <= n:
        c = body[i] if i < n else ";"
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        elif c == ";" and paren == 0:
            chunk = body[start:i]
            m = re.match(r"\s*([\w-]+)\s*:", chunk)
            if m and not chunk.lstrip().startswith("/*"):
                res.append((m.group(1), offset + start, offset + min(i + 1, n), "!important" in chunk))
            start = i + 1
        i += 1
    return res


def analyse(text):
    rules = top_level(text)
    seen = collections.defaultdict(list)   # selector -> [(rule index)]
    for k, (ps, pe, _bs, _be) in enumerate(rules):
        sel = re.sub(r"/\*.*?\*/", "", text[ps:pe], flags=re.S).strip()
        if sel and not sel.startswith("@"):
            seen[sel].append(k)
    dead = []   # (start, end, selector, prop)
    for sel, ks in seen.items():
        if len(ks) < 2:
            continue
        decls = {k: declarations(text[rules[k][2]:rules[k][3]], rules[k][2]) for k in ks}
        for pos, k in enumerate(ks[:-1]):
            later = {p for kk in ks[pos + 1:] for p, _s, _e, imp in decls[kk] if not imp}
            for prop, s, e, imp in decls[k]:
                if prop in later and not imp:
                    dead.append((s, e, sel, prop))
    return sorted(dead)


def main():
    text = CSS.read_text(encoding="utf-8")
    dead = analyse(text)
    for _s, _e, sel, prop in dead:
        print(f"  never applies: {sel} {{ {prop} }}  (written again later)")
    if "--fix" in sys.argv:
        for s, e, _sel, _p in reversed(dead):
            text = text[:s] + text[e:]
        text = re.sub(r"[ \t]*[^{}\n]*\{\s*\}\n?", lambda m: "" if not m.group(0).strip().startswith("@") else m.group(0), text)
        CSS.write_text(text, encoding="utf-8")
        print(f"removed {len(dead)}")
        return 0
    print(f"{len(dead)} declarations that never apply")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
