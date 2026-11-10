import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { roomLabel } from "../labels.js";

// Ctrl+K: one box to jump to a page, a tool, a class, a file or a source. With nothing typed it shows the recent files.
const norm = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[ً-ٰٟـ̀-ͯ]/g, "")
  .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/\s+/g, " ").trim();

const safe = (p) => p.catch(() => null);

async function collect(pages) {
  const lang = getLang(), L = (o) => (o && (o[lang] || o.en)) || "";
  const [cat, structure, lib, src] = await Promise.all([safe(api.get("/api/tools")), safe(api.get("/api/structure")), safe(api.get("/api/library")), safe(api.get("/api/sources"))]);
  const go = (hash) => () => { location.hash = hash; };
  const out = [];
  for (const p of pages) {
    const nav = document.querySelector(`.nav a[data-page="${p.nav || p.id}"]`);
    if (p.need && nav && nav.hidden) continue;                       // a page this teacher cannot use is not offered
    if (!p.icon && nav && nav.hidden) continue;
    out.push({ kind: "page", label: t(`nav_${p.id}`), hint: "", ico: p.icon || "info", run: go(`#/${p.id}`) });
  }
  if (cat) for (const x of cat.tools) out.push({ kind: "tool", label: L(x.name), hint: L(x.desc), ico: "tool", run: go(`#/tools?tool=${x.id}`) });
  if (structure) for (const r of structure.rooms) out.push({ kind: "class", label: roomLabel(r, structure), hint: "", ico: "classes", run: go(`#/classes?room=${encodeURIComponent(r.id)}`) });
  let files = [];
  if (lib) {
    files = lib.items.map((f) => ({ kind: "file", label: f.name, hint: f.folder || "", ico: "file", mtime: f.mtime, run: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel })) }));
    out.push(...files);
  }
  if (src) for (const s of src.sources) out.push({ kind: "source", label: s.topic ? `${s.name} — ${s.topic}` : s.name, hint: "", ico: "slides", run: go("#/library") });
  return { all: out, recent: files.slice(0, 6) };
}

function rank(items, q) {
  const words = norm(q).split(" ").filter(Boolean);
  const scored = [];
  for (const it of items) {
    const label = norm(it.label), hay = label + " " + norm(it.hint);
    if (!words.every((w) => hay.includes(w))) continue;
    let sc = 0;
    if (label.startsWith(words[0])) sc += 3;
    else if (label.includes(words[0])) sc += 2;
    if (it.kind === "page") sc += 1;
    scored.push([sc, it]);
  }
  return scored.sort((a, b) => b[0] - a[0]).map((x) => x[1]).slice(0, 14);
}

let openBox = null;
export async function openQuick(pages) {
  if (openBox) { openBox.input.focus(); return; }
  const data = await collect(pages);
  let shown = [], active = 0;
  const input = h("input", { type: "text", class: "quick-input", placeholder: t("qk_ph"), "aria-label": t("qk_ph"), autocomplete: "off", role: "combobox", "aria-expanded": "true" });
  const list = h("div", { class: "quick-list", role: "listbox" });
  const overlay = h("div", { class: "overlay quick-overlay", role: "dialog", "aria-modal": "true", "aria-label": t("qk_btn") },
    h("div", { class: "modal quick" }, h("div", { class: "quick-top" }, icon("search"), input), list, h("div", { class: "quick-foot" }, t("qk_keys"))));
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey, true); openBox = null; };
  const run = (it) => { close(); setTimeout(it.run, 0); };
  function draw() {
    const q = input.value.trim();
    shown = q ? rank(data.all, q) : [...data.recent, ...data.all.filter((x) => x.kind === "page").slice(0, 8)];
    if (active >= shown.length) active = 0;
    const rows = []; let last = "";
    shown.forEach((it, i) => {
      const head = q ? "" : (it.kind === "file" ? t("qk_recent") : t("qk_pages"));
      if (head && head !== last) { rows.push(h("div", { class: "quick-head" }, head)); last = head; }
      rows.push(h("div", { class: `quick-item${i === active ? " on" : ""}`, role: "option", "aria-selected": i === active ? "true" : "false", onMousemove: () => { if (active !== i) { active = i; mark(); } }, onClick: () => run(it) },
        icon(it.ico), h("span", { class: "quick-label" }, it.label), h("span", { class: "quick-kind" }, t(`qk_${it.kind}`))));
    });
    list.replaceChildren(...(rows.length ? rows : [h("div", { class: "quick-none" }, t("qk_none"))]));
  }
  function mark() {
    list.querySelectorAll(".quick-item").forEach((el, i) => { el.classList.toggle("on", i === active); el.setAttribute("aria-selected", i === active ? "true" : "false"); });
    list.querySelector(".quick-item.on")?.scrollIntoView({ block: "nearest" });
  }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); if (shown.length) { active = (active + 1) % shown.length; mark(); } }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (shown.length) { active = (active - 1 + shown.length) % shown.length; mark(); } }
    else if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); if (shown[active]) run(shown[active]); }
  }
  input.addEventListener("input", () => { active = 0; draw(); });
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", onKey, true);
  document.body.append(overlay);
  openBox = { input };
  draw(); input.focus();
}
