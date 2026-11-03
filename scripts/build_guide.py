"""Makes the teachers' user guide (PDF, Arabic + English) from app/web/js/help_content.json and the e2e screenshots.
Run:  python3 scripts/e2e.py   (makes the screenshots in /tmp/shots)  then  python3 scripts/build_guide.py
"""
import base64, html, json, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = Path("/tmp/shots")
VERSION = re.search(r'VERSION = "([^"]+)"', (ROOT / "app/core/paths.py").read_text()).group(1)
content = json.loads((ROOT / "app/web/js/help_content.json").read_text(encoding="utf-8"))
logo = base64.b64encode((ROOT / "resources/logo.png").read_bytes()).decode()

TEXT = {"ar": {"title": "دليل استخدام مساعد المعلم", "sub": "لمدرسي مدرسة دار لقمان الحكيم الدولية", "dir": "rtl", "lang": "ar"},
        "en": {"title": "DLIS Teacher Assistant — User Guide", "sub": "For the teachers of Dar Luqman Al-Hakim International School", "dir": "ltr", "lang": "en"}}


def rich(t):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(t))


def page(lang):
    T = TEXT[lang]
    secs = []
    for i, s in enumerate(content[lang], 1):
        img = ""
        f = SHOTS / f"{s['image']}.png"
        if s.get("image") and f.exists():
            img = f'<img src="data:image/png;base64,{base64.b64encode(f.read_bytes()).decode()}" alt="">'
        steps = "".join(f"<li>{rich(x)}</li>" for x in s["steps"])
        secs.append(f'<section><h2><span>{i}</span>{html.escape(s["title"])}</h2><ol>{steps}</ol>{img}</section>')
    return f"""<!doctype html><html lang="{T['lang']}" dir="{T['dir']}"><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 14mm; }}
body {{ font-family: "Noto Sans Arabic", "Segoe UI", Tahoma, Arial, sans-serif; color: #1c1f4d; line-height: 1.75; font-size: 12.5pt; }}
.cover {{ height: 255mm; display: grid; place-content: center; text-align: center; gap: 12px; page-break-after: always; }}
.cover img {{ width: 340px; margin: 0 auto 30px; }} .cover h1 {{ font-size: 30pt; margin: 0; }} .cover p {{ color: #5a6a85; margin: 0; font-size: 14pt; }}
section {{ margin-bottom: 22px; }}
h2 {{ break-after: avoid; }}
h2 {{ font-size: 17pt; border-bottom: 3px solid #a2c65a; padding-bottom: 4px; display: flex; gap: 10px; align-items: center; }}
h2 span {{ background: #2f82a8; color: #fff; border-radius: 50%; width: 1.7em; height: 1.7em; display: grid; place-items: center; font-size: 12pt; flex: none; }}
ol {{ padding-inline-start: 1.5em; }} li {{ margin-bottom: 5px; }}
img {{ width: 88%; display: block; margin: 8px auto 0; border: 1px solid #c7d5e2; border-radius: 8px; break-inside: avoid; }}
</style><body>
<div class="cover"><img src="data:image/png;base64,{logo}" alt=""><h1>{T['title']}</h1><p>{T['sub']}</p><p>v{VERSION}</p></div>
{''.join(secs)}</body></html>"""


with sync_playwright() as p:
    b = p.chromium.launch()
    for lang, name in (("ar", "DLIS_User_Guide_AR.pdf"), ("en", "DLIS_User_Guide_EN.pdf")):
        pg = b.new_page()
        pg.set_content(page(lang), wait_until="load")
        out = ROOT / "docs" / name
        out.parent.mkdir(exist_ok=True)
        pg.pdf(path=str(out), format="A4", print_background=True)
        print("wrote", out)
    b.close()
