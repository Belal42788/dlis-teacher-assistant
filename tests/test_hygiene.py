"""Rules that keep the code from getting tangled again. Each one fails with a message that says what to fix."""
import ast
import collections
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import nonet
nonet.install()
APP = ROOT / "app"


def py_files(folder=APP):
    return [p for p in folder.rglob("*.py") if "__pycache__" not in p.parts]


def module_name(p: Path) -> str:
    parts = list(p.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class TestLayers(unittest.TestCase):
    def test_core_never_imports_the_server_or_the_window(self):
        """app/core is the part that knows about files and documents; it must work without the web server on top of it."""
        for p in py_files(APP / "core"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(n, ast.ImportFrom):
                    target = ("." * n.level) + (n.module or "")
                    bad = n.module and (n.module.split(".")[0] in ("server", "launcher") or n.module.startswith(("app.server", "app.launcher")))
                    self.assertFalse(bad or target.startswith("..server") or target.startswith("..launcher"), f"{p.name} imports {target}: core must not depend on server")

    def test_no_import_cycles_at_module_level(self):
        mods = {module_name(p): p for p in py_files()}
        graph = collections.defaultdict(set)
        for name, p in mods.items():
            pkg = name if p.name == "__init__.py" else name.rsplit(".", 1)[0]
            for n in ast.parse(p.read_text(encoding="utf-8")).body:   # only imports at the top of the file: the ones inside functions are the usual way out of a cycle
                if isinstance(n, ast.ImportFrom):
                    base = pkg.split(".")
                    if n.level:
                        base = base[:len(base) - (n.level - 1)]
                        target = ".".join(base + ([n.module] if n.module else []))
                    else:
                        target = n.module or ""
                    for cand in [target] + [f"{target}.{a.name}" for a in n.names]:
                        if cand in mods and cand != name:
                            graph[name].add(cand)
        found, seen = [], set()

        def walk(u, path):
            if u in path:
                found.append(" -> ".join(path[path.index(u):] + [u]))
            elif u not in seen:
                seen.add(u)
                for v in sorted(graph[u]):
                    walk(v, path + [u])
        for u in sorted(graph):
            walk(u, [])
        self.assertEqual(found, [], "modules import each other in a circle")


class TestDeadCode(unittest.TestCase):
    # Names that are called from outside Python: the window's JavaScript bridge, the web server's own method names, the HTML parser's hooks.
    ALLOWED = {"toggle_maximize", "start_drag", "reminder_stop", "reminder_alert", "do_PUT", "handle_starttag", "handle_endtag", "handle_data", "_days", "_time"}

    def test_every_function_in_app_is_used_somewhere(self):
        texts = {p: p.read_text(encoding="utf-8") for p in py_files(ROOT) if ".git" not in p.parts}
        words = collections.Counter(re.findall(r"[A-Za-z_]\w*", "\n".join(texts.values())))
        dead = []
        for p in py_files():
            for n in ast.walk(ast.parse(texts[p])):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith(("__", "test")) and n.name not in self.ALLOWED and words[n.name] <= 1:
                    dead.append(f"{p.relative_to(ROOT)}:{n.lineno} {n.name}")
        self.assertEqual(dead, [], "nobody calls these: delete them (or add to ALLOWED if the call comes from outside Python)")


class TestWebFiles(unittest.TestCase):
    def test_every_javascript_file_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        tmp = ROOT / "app" / "web" / "_syntax_check.mjs"
        bad = []
        try:
            for p in sorted((APP / "web" / "js").rglob("*.js")):
                tmp.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                r = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True)
                if r.returncode:
                    bad.append(f"{p.relative_to(ROOT)}: {r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'error'}")
        finally:
            tmp.unlink(missing_ok=True)
        self.assertEqual(bad, [])

    def test_no_css_declaration_that_never_applies(self):
        import css_dedupe
        dead = css_dedupe.analyse(css_dedupe.CSS.read_text(encoding="utf-8"))
        self.assertEqual([(sel, prop) for _s, _e, sel, prop in dead], [], "the same rule is written again later: run  python scripts/css_dedupe.py --fix")


class TestDocs(unittest.TestCase):
    def test_developer_guide_matches_the_code(self):
        import make_dev_docs
        old = make_dev_docs.DOC.read_text(encoding="utf-8")
        self.assertEqual(make_dev_docs.render(old), old, "docs/DEVELOPER.md is out of date: run  python scripts/make_dev_docs.py")


class TestNoInternet(unittest.TestCase):
    """A test that quietly used the real internet passed on the developer's computer and failed on GitHub. Never again."""

    def test_every_test_file_cuts_the_internet(self):
        for f in sorted((ROOT / "tests").glob("test_*.py")):
            self.assertIn("nonet.install()", f.read_text(encoding="utf-8"), f"{f.name} must call nonet.install() near the top")

    def test_other_computers_are_unreachable_but_this_one_is(self):
        import socket
        import urllib.error
        import urllib.request
        before = len(nonet.ATTEMPTS)
        with self.assertRaises((urllib.error.URLError, OSError)):
            urllib.request.urlopen("https://image.pollinations.ai/prompt/x", timeout=5)
        self.assertGreater(len(nonet.ATTEMPTS), before)
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        c = socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=2)     # the app's own local server must still work
        c.close(); srv.close()


if __name__ == "__main__":
    unittest.main()
