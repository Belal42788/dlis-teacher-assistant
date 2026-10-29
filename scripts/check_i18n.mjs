// Fails if a word used on screen is missing in Arabic or English.
import fs from "node:fs";
import path from "node:path";
import { STR } from "../app/web/js/i18n.mjs";

const root = new URL("../app/web/js/", import.meta.url).pathname;
const files = [];
(function walk(d) { for (const f of fs.readdirSync(d, { withFileTypes: true })) f.isDirectory() ? walk(path.join(d, f.name)) : f.name.endsWith(".js") && files.push(path.join(d, f.name)); })(root);
const used = new Set();
for (const f of files.filter((x) => !x.endsWith("i18n.js"))) {
  const src = fs.readFileSync(f, "utf8");
  for (const m of src.matchAll(/(?<![\w.])t\("([A-Za-z0-9_ ]+)"/g)) used.add(m[1]);
  for (const m of src.matchAll(/"(err_[a-z_]+)"/g)) used.add(m[1]);
}
for (const d of ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]) used.add(`day_${d}`);
for (const k of ["documents","desktop","home"]) used.add(`sc_${k}`);
for (const p of ["today","classes","timetable","calendar","settings"]) used.add(`nav_${p}`);
for (const s of ["folder","about","classes","timetable","calendar"]) used.add(`step_${s}`);
for (const b of ["KG","LOWER_PRIMARY","UPPER_PRIMARY","PREPARATORY","SECONDARY"]) used.add(`band_${b}`);
for (const k of ["Behavior","Attendance","Classwork","Homework","Quiz Score"]) used.add(`gm_${k}`);
let bad = 0;
for (const k of used) for (const l of ["en", "ar"]) if (!(k in STR[l])) { console.log(`MISSING ${l}: ${k}`); bad++; }
for (const k of Object.keys(STR.en)) if (!(k in STR.ar)) { console.log(`only in en: ${k}`); bad++; }
for (const k of Object.keys(STR.ar)) if (!(k in STR.en)) { console.log(`only in ar: ${k}`); bad++; }
const unused = Object.keys(STR.en).filter((k) => !used.has(k) && !/^(err_|day_|nav_|step_|band_|gm_)/.test(k));
console.log(`${used.size} keys used, ${bad} problems, ${unused.length} unused: ${unused.join(" ")}`);
process.exit(bad ? 1 : 0);
