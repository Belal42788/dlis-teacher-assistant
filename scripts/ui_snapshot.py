"""Records how every element on every page looks (size, colours, spacing...) in Arabic and English, on a desktop and a phone width.
Use it to prove that a clean-up or a split of a big file changed NOTHING on screen:
    python scripts/ui_snapshot.py before.json        (before the change)
    python scripts/ui_snapshot.py after.json         (after the change)
    python scripts/ui_snapshot.py --compare before.json after.json
Two runs of the same code give identical files, so any difference is real. Takes about 4 minutes."""
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

if sys.argv[1:2] == ["--compare"]:
    a, b = (json.load(open(f)) for f in sys.argv[2:4])
    diff = [(k, x[0]) for k in a for x, y in zip(a[k], b.get(k, []), strict=False) if x != y] + [(k, "different number of elements") for k in a if len(a[k]) != len(b.get(k, []))]
    print(f"{len(diff)} differences in {len(a)} page views")
    for d in diff[:20]:
        print("  ", *d)
    sys.exit(1 if diff else 0)
root = str(Path(__file__).resolve().parents[1])
outp = sys.argv[1]
os.environ["DLIS_APP_HOME"]=tempfile.mkdtemp()
sys.path.insert(0,root)
from app.server.http import AppServer
from playwright.sync_api import sync_playwright
s=AppServer(); s.start_in_thread()
base=f"http://127.0.0.1:{s.port_number}"
def call(m,p,b=None):
    r=urllib.request.Request(base+p,method=m,data=json.dumps(b).encode() if b is not None else None,headers={"X-DLIS-Token":s.token,"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r).read() or b"null")
call("POST","/api/data-folder",{"path":tempfile.mkdtemp()+"/data"})
call("PUT","/api/settings",{"teacher_name":"Bilal","subject":"ICT","setup_done":True})
call("POST","/api/structure/build",{"selection":{"g4":["A"],"g5":["A"]}})
rid = call("GET", "/api/structure")["rooms"][0]["id"]
call("PUT",f"/api/rooms/{rid}/students",{"names":["أحمد علي","سارة خالد","عمر حسن"]})
call("POST","/api/tasks",{"title":"Task one","importance":"high","deadline":"2026-12-01"})
call("POST","/api/behavior",{"room_id":rid,"student":"سارة خالد","kind":"good","note":"nice"})
call("PUT","/api/seating",{"room_id":rid,"rows":2,"cols":3,"seats":{"0-0":"أحمد علي"}})
ids=re.findall(r'\{ id: "(\w+)"',open(root+"/app/web/js/main.js",encoding="utf-8").read())
JS="""() => { const props=['display','position','width','height','min-height','margin','padding','border','border-radius','background-color','color','font-size','font-weight','box-shadow','flex','grid-template-columns','grid-template-rows','gap','align-items','justify-content','white-space','outline','transition','opacity','overflow','grid-column','grid-row','content'];
 const out=[]; document.querySelectorAll('#main *, header *, nav *').forEach((e,i)=>{ if(i>1500) return; const cs=getComputedStyle(e); const k=e.tagName+'.'+(typeof e.className==='string'?e.className:'')+'#'+i; out.push([k, props.map(p=>cs.getPropertyValue(p)).join('|')]); }); return out; }"""
res={}
with sync_playwright() as p:
    b=p.chromium.launch()
    for lang in ("ar","en"):
        call("PUT","/api/prefs",{"language":lang})
        for w in (1200,390):
            pg=b.new_page(viewport={"width":w,"height":800}); pg.add_init_script("localStorage.setItem('dlis.lang','%s')"%lang)
            pg.goto(base+"/"); pg.wait_for_timeout(900)
            for pid in ids:
                pg.evaluate(f"location.hash='#/{pid}'"); 
                try: pg.wait_for_selector("#main:not(.busy)",timeout=5000)
                except Exception: pass
                pg.wait_for_timeout(350)
                res[f"{lang}-{w}-{pid}"]=pg.evaluate(JS)
            pg.close()
    b.close()
s.shutdown()
json.dump(res,open(outp,"w"))
print(len(res), "page views,", sum(len(v) for v in res.values()), "elements")
