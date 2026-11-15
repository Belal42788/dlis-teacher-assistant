"""Takes the screenshots used by README.md / README_AR.md (docs/images/en and docs/images/ar) with MADE-UP data only:
made-up teacher, made-up students, a fixed day and time so every picture looks the same each time.
    python scripts/make_readme_shots.py          (about 1 minute)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_data import NOW, ROOT, base, call, s
from PIL import Image
from playwright.sync_api import sync_playwright

OUT = ROOT / "docs" / "images"
SHOTS = [  # (file, hash, wait selector, extra action)
    ("today", "today", ".tl, .today, .panel", None),
    ("timetable", "timetable", ".tt, table", None),
    ("calendar", "calendar", ".cal-year, .cal, .panel", None),
    ("tasks", "tasks", ".panel", None),
    ("create", "docs", ".cr-hub", None),
    ("tool", "tools?tool=lesson_starter", ".panel", None),
    ("files", "library", ".lib-tree, .panel", None),
    ("bank", "bank", ".bk-card", None),
    ("classes", "classes", ".students li", None),
    ("grades", "grades", "table, .panel", None),
    ("behavior", "behavior", ".panel", None),
    ("seating", "seating", ".panel", None),
    ("map", "map", ".panel, svg", None),
    ("settings", "settings", ".panel", None),
]
with sync_playwright() as p:
    b = p.chromium.launch()
    for lang in ("en", "ar"):
        call("PUT", "/api/prefs", {"language": lang})
        out = OUT / lang; out.mkdir(parents=True, exist_ok=True)
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1, bypass_csp=True)
        pg = ctx.new_page(); pg.clock.set_fixed_time(NOW)
        pg.add_init_script("localStorage.setItem('dlis.lang','%s')" % lang)
        pg.goto(base + "/"); pg.wait_for_timeout(900)
        for i, (name, h_, sel, _) in enumerate(SHOTS, 1):
            pg.evaluate(f"location.hash='#/{h_}'")
            try:
                pg.wait_for_selector("#main:not(.busy)", timeout=8000); pg.wait_for_selector(sel, timeout=8000)
            except Exception:
                print("  (no", sel, "on", name, ")")
            pg.wait_for_timeout(700)
            f = out / f"{i:02d}-{name}.png"
            pg.screenshot(path=str(f))
            Image.open(f).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(f, optimize=True)
        ctx.close()
    b.close()
s.shutdown()
print("done:", sum(1 for _ in OUT.rglob("*.png")), "pictures,", sum(f.stat().st_size for f in OUT.rglob("*.png")) // 1024, "KB")
