import { h, icon, toast, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { hubTabs } from "../components/hubtabs.js";
import { roomLabel, triName, fmtShort } from "../labels.js";

const memo = { room: "", tri: null, week: null, fullParts: { behavior: true, attendance: true, classwork: true, homework: true, quiz: false } };

// Weekly marks of one class: typed here (every change is saved), filled with the full mark for everyone except the absent,
// or taken from an LMS file; then sent to the parents' portal.
export async function renderGrades(root) {
  const [structure, ov] = await Promise.all([api.get("/api/structure"), api.get("/api/overview")]);
  const rooms = structure.rooms, tris = ov.trimesters.filter((x) => x.weeks.length), pos = ov.position;
  const tabs = hubTabs("classes", "grades");
  if (!rooms.length || !tris.length) {
    root.replaceChildren(h("div", { class: "page" }, tabs, h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_rooms")))));
    return;
  }
  if (!rooms.some((r) => r.id === memo.room)) memo.room = rooms[0].id;
  if (memo.tri === null || !tris.some((x) => x.index === memo.tri)) memo.tri = pos.state === "in_term" ? pos.trimester : tris[0].index;
  if (memo.week === null) memo.week = pos.state === "in_term" ? pos.week : 1;
  const triObj = () => tris.find((x) => x.index === memo.tri) || tris[0];

  const roomSel = h("select", { "aria-label": t("d_class"), onChange: () => { memo.room = roomSel.value; load(); } }, rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const triSel = h("select", { "aria-label": t("d_trimester"), onChange: () => { memo.tri = +triSel.value; memo.week = 1; drawWeeks(); load(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  const weekSel = h("select", { "aria-label": t("d_week"), onChange: () => { memo.week = +weekSel.value; load(); } });
  function drawWeeks() {
    weekSel.replaceChildren(triObj().weeks.map((w) => h("option", { value: w.number }, `${t("week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}`)));
    if (!triObj().weeks.some((w) => w.number === memo.week)) memo.week = 1;
    weekSel.value = memo.week;
  }
  roomSel.value = memo.room; triSel.value = memo.tri; drawWeeks();

  const plabel = (p) => t(`gs_part_${p.key}`);   // e.g. "Behavior (10)" / "السلوك (10)"
  const box = h("div", {}), status = h("span", { class: "muted small" });
  let data = null, inputs = [];

  const num = (v) => (v === "" || v === null || v === undefined || isNaN(+v) ? null : +v);
  const collect = () => ({ room_id: memo.room, trimester: memo.tri, week: memo.week, lms_max: num(lmsMax.value) || 0,
    rows: inputs.map((r) => ({ name: r.name, absent: r.abs.checked, marks: Object.fromEntries([...Object.entries(r.parts).map(([k, el]) => [k, el.value]), ["lms", r.lms ? r.lms.value : ""]].filter(([, v]) => v !== "")) })) });
  let timer = null;
  const later = () => { status.textContent = "…"; clearTimeout(timer); timer = setTimeout(save, 700); };
  async function save() {
    const r = await guarded(() => api.put("/api/grades", collect()));
    if (r) { data = r; status.textContent = t("gr_saved"); recompute(); } else status.textContent = "";
  }
  const lmsMax = h("input", { type: "number", min: 0, style: { width: "5em" }, "aria-label": t("gr_lms_max"), onChange: later });

  function recompute() {
    let sum = 0, n = 0;
    inputs.forEach((r) => {
      const tot = Object.values(r.parts).reduce((a, el) => a + (num(el.value) || 0), 0);
      r.total.textContent = r.abs.checked ? "—" : String(Math.round(tot * 100) / 100);
      r.row.classList.toggle("abs", r.abs.checked);
      Object.values(r.parts).forEach((el) => { el.disabled = r.abs.checked; }); if (r.lms) r.lms.disabled = r.abs.checked;
      if (!r.abs.checked && Object.values(r.parts).some((el) => el.value !== "")) { sum += tot; n++; }
    });
    avg.textContent = n ? t("gr_avg", { v: Math.round((sum / n) * 10) / 10, max: data.parts.reduce((a, p) => a + p.max, 0) }) : "";
  }
  const avg = h("span", { class: "muted small" });

  function draw() {
    const hasLms = data.students.some((s) => s.marks.lms !== undefined) || data.lms_max;
    lmsMax.value = data.lms_max || "";
    inputs = data.students.map((s) => {
      const parts = Object.fromEntries(data.parts.map((p) => [p.key, h("input", { type: "number", min: 0, max: p.max, step: 0.5, value: s.marks[p.key] ?? "", class: "gr-in", "aria-label": plabel(p), onInput: later })]));
      const abs = h("input", { type: "checkbox", checked: s.absent, "aria-label": t("gr_absent"), onChange: () => { if (abs.checked) Object.values(parts).forEach((el) => { el.value = ""; }); if (lms) lms.value = ""; later(); recompute(); } });
      const lms = hasLms ? h("input", { type: "number", min: 0, step: 0.5, value: s.marks.lms ?? "", class: "gr-in", "aria-label": t("gr_lms"), onInput: later }) : null;
      const total = h("b", {});
      const row = h("tr", {}, h("td", { class: "c-chk" }, abs), h("td", {}, s.name), ...data.parts.map((p) => h("td", {}, parts[p.key])), lms ? h("td", {}, lms) : null, h("td", {}, total));
      return { name: s.name, abs, parts, lms, total, row };
    });
    const partBoxes = Object.fromEntries(data.parts.map((p) => [p.key, h("input", { type: "checkbox", checked: memo.fullParts[p.key], onChange: (e) => { memo.fullParts[p.key] = e.target.checked; } })]));
    box.replaceChildren(
      h("div", { class: "panel" },
        h("details", { class: "fold", open: true }, h("summary", {}, t("gr_tools")),
          h("div", { class: "row small", style: { flexWrap: "wrap", margin: ".4rem 0" } }, h("span", {}, t("gr_full_parts")), data.parts.map((p) => h("label", { class: "row" }, partBoxes[p.key], plabel(p)))),
          h("div", { class: "row", style: { flexWrap: "wrap" } },
            h("button", { class: "btn primary", onClick: () => { inputs.forEach((r) => { if (r.abs.checked) return; data.parts.forEach((p) => { if (memo.fullParts[p.key]) r.parts[p.key].value = p.max; }); }); later(); recompute(); toast(t("gr_filled")); } }, icon("check"), t("gr_full")),
            h("button", { class: "btn", onClick: () => { inputs.forEach((r) => { Object.values(r.parts).forEach((el) => { el.value = ""; }); if (r.lms) r.lms.value = ""; }); later(); recompute(); } }, icon("trash"), t("gr_clear")),
            h("label", { class: "btn" }, icon("download"), t("gr_import"), h("input", { type: "file", accept: ".xlsx,.csv,.txt", hidden: true, onChange: async (e) => {
              const f = e.target.files[0]; if (!f) return; e.target.value = "";
              const r = await guarded(async () => api.post("/api/grades/import", { room_id: memo.room, trimester: memo.tri, week: memo.week, filename: f.name, data_b64: await readFileB64(f), max: num(lmsMax.value) || 0 }));
              if (r) { data = r; draw(); toast(t("gr_imported", { n: r.imported })); if (r.unmatched.length) box.prepend(h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("gr_unmatched", { n: r.unmatched.length }), ": ", r.unmatched.slice(0, 8).join("، ")))); }
            } })),
            h("label", { class: "row small" }, t("gr_lms_max"), lmsMax)),
          h("p", { class: "muted small" }, t("gr_lms_hint")))),
      h("div", { class: "panel", style: { overflowX: "auto" } },
        h("table", { class: "tasks-table gr-table" },
          h("thead", {}, h("tr", {}, h("th", {}, t("gr_absent")), h("th", {}, t("students")), ...data.parts.map((p) => h("th", {}, plabel(p))), hasLms ? h("th", {}, t("gr_lms")) : null, h("th", {}, t("gr_total")))),
          h("tbody", {}, inputs.map((r) => r.row))),
        h("div", { class: "row", style: { marginTop: ".5rem" } }, status, h("span", { class: "grow" }), avg)),
      h("div", { class: "panel" }, h("h3", {}, t("gr_portal")),
        data.role === "teacher" || data.role === "admin"
          ? h("div", {}, h("p", { class: "muted small" }, t("gr_portal_lead")),
              h("button", { class: "btn primary", onClick: () => guarded(async () => {
                await save();
                const r = await api.post("/api/grades/upload", { room_id: memo.room, trimester: memo.tri, week: memo.week });
                toast(t("gr_sent", { n: r.sent })); if (r.missing.length) box.prepend(h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("gr_missing", { n: r.missing.length }), ": ", r.missing.slice(0, 8).join("، "))));
              }) }, icon("send"), t("gr_upload")),
              data.uploaded ? h("span", { class: "muted small", style: { marginInlineStart: ".6rem" } }, t("gr_uploaded_on", { d: data.uploaded })) : null)
          : h("p", { class: "muted small" }, t("gr_need_login"), " ", h("a", { href: "#/settings" }, t("nav_settings")))));
    recompute();
  }
  async function load() {
    const r = await guarded(() => api.get(`/api/grades?room=${memo.room}&tri=${memo.tri}&week=${memo.week}`));
    if (r) { data = r; status.textContent = ""; draw(); }
  }
  root.replaceChildren(h("div", { class: "page" }, tabs,
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("gr_title")), h("p", {}, t("gr_lead")))),
    h("div", { class: "panel sticky-pick" }, h("div", { class: "pick-row" }, h("label", {}, h("span", { class: "label" }, t("d_class")), roomSel),
      h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel), h("label", {}, h("span", { class: "label" }, t("d_week")), weekSel))),
    box));
  await load();
}
