import { h, icon, toast, modal, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { timeInput12 } from "./time12.js";

// The shape of the school day: lesson times, breakfast, break, prayer break and the late duty.
// The top part arranges the times from a few numbers; the table under it can then be fixed by hand, one time at a time.
const toMin = (v) => { const [a, b] = String(v || "0:0").split(":").map(Number); return a * 60 + b; };
const fromMin = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const copy = (x) => JSON.parse(JSON.stringify(x));

export async function openBellEditor({ usedCells = (n) => 0, beforeSave, onSaved }) {
  const cfg = await guarded(() => api.get("/api/bell")); if (!cfg) return;
  const m = copy(cfg.bell);   // { periods:[{start,end}], breakfast?, break?, prayer?, late? }
  const oldCount = cfg.bell.periods.length;
  const box = h("div", { class: "bl" });
  const num = (v, min, max, label, w = "5em") => { const el = h("input", { type: "number", min, max, value: v, style: { width: w }, "aria-label": label }); return el; };
  const lessonSel = (cur, label) => { const s = h("select", { "aria-label": label }, m.periods.map((_, i) => h("option", { value: String(i + 1) }, t("period_n", { n: i + 1 })))); s.value = String(cur); return s; };

  // ---- the quick arranger
  const len0 = m.periods[0] ? toMin(m.periods[0].end) - toMin(m.periods[0].start) : 40;
  const q = {
    start: timeInput12((m.breakfast || m.periods[0] || { start: "08:00" }).start),
    n: num(m.periods.length, 1, 12, t("bl_lessons")), len: num(len0, 10, 120, t("bl_len")),
    bf: num(m.breakfast ? toMin(m.breakfast.end) - toMin(m.breakfast.start) : 0, 0, 60, t("slot_breakfast")),
    brAfter: null, br: num(m.break ? toMin(m.break.end) - toMin(m.break.start) : 0, 0, 90, t("duty_break")),
    prAfter: null, pr: num(m.prayer ? toMin(m.prayer.end) - toMin(m.prayer.start) : 0, 0, 60, t("slot_prayer")),
    late: num(m.late ? toMin(m.late.end) - toMin(m.late.start) : 0, 0, 120, t("duty_late")),
  };
  q.brAfter = lessonSel(m.break ? m.break.after : 4, t("bl_after")); q.prAfter = lessonSel(m.prayer ? m.prayer.after : 7, t("bl_after"));
  q.n.addEventListener("change", () => {   // the "after lesson" lists follow the number of lessons
    const n = Math.max(1, Math.min(12, +q.n.value || 1)), keep = (s) => Math.min(+s.value || 1, n);
    for (const s of [q.brAfter, q.prAfter]) { const v = keep(s); s.replaceChildren(...Array.from({ length: n }, (_, i) => h("option", { value: String(i + 1) }, t("period_n", { n: i + 1 })))); s.value = String(v); }
  });
  const arrange = () => {
    const n = Math.max(1, Math.min(12, +q.n.value || 1)), len = Math.max(10, +q.len.value || 40);
    let cur = toMin(q.start.value); const out = { periods: [] };
    const take = (mins) => { const s = fromMin(cur); cur += mins; return { start: s, end: fromMin(cur) }; };
    if (+q.bf.value > 0) out.breakfast = { before: "1", ...take(+q.bf.value) };
    for (let i = 1; i <= n; i++) {
      out.periods.push(take(len));
      if (+q.br.value > 0 && +q.brAfter.value === i) out.break = { after: String(i), ...take(+q.br.value) };
      if (+q.pr.value > 0 && +q.prAfter.value === i) out.prayer = { after: String(i), ...take(+q.pr.value) };
    }
    if (+q.late.value > 0) out.late = take(+q.late.value);
    for (const k of Object.keys(m)) delete m[k];
    Object.assign(m, out); drawTable();
  };
  const field = (label, el, extra) => h("label", { class: "field" }, h("span", { class: "label" }, label), el, extra || null);
  const quick = h("div", { class: "panel" }, h("h4", {}, t("bl_auto_h")), h("p", { class: "muted small" }, t("bl_auto_hint")),
    h("div", { class: "bl-grid" },
      field(t("bl_start"), q.start), field(t("bl_lessons"), q.n), field(t("bl_len"), q.len), field(t("bl_late"), q.late),
      field(t("slot_breakfast"), q.bf, h("small", { class: "muted" }, t("bl_zero_none"))),
      field(t("duty_break"), h("span", { class: "row" }, q.br, h("span", {}, t("bl_after")), q.brAfter), h("small", { class: "muted" }, t("bl_zero_none"))),
      field(t("slot_prayer"), h("span", { class: "row" }, q.pr, h("span", {}, t("bl_after")), q.prAfter), h("small", { class: "muted" }, t("bl_zero_none")))),
    h("div", { class: "row", style: { marginTop: ".6rem" } }, h("button", { class: "btn primary", onClick: arrange }, icon("clock"), t("bl_arrange"))));

  // ---- the table, one row per part of the day
  const table = h("div", { class: "bl-table" });
  const pick = (o, key) => { const a = timeInput12(o[key]); a.addEventListener("change", () => { o[key] = a.value; }); return a; };
  const row = (label, o, extra, remove) => h("div", { class: "bl-row" }, h("b", {}, label), pick(o, "start"), h("span", { class: "muted" }, "→"), pick(o, "end"), extra || h("span"), remove || h("span"));
  const rm = (k) => h("button", { class: "btn small ghost", type: "button", onClick: () => { delete m[k]; drawTable(); } }, icon("close"), t("bl_remove"));
  const afterSel = (k) => { const s = lessonSel(m[k].after, t("bl_after")); s.addEventListener("change", () => { m[k].after = s.value; drawTable(); }); return h("span", { class: "row" }, h("span", { class: "muted small" }, t("bl_after")), s); };
  function drawTable() {
    const rows = [];
    if (m.breakfast) rows.push(row(t("slot_breakfast"), m.breakfast, null, rm("breakfast")));
    m.periods.forEach((p, i) => {
      rows.push(row(t("period_n", { n: i + 1 }), p));
      for (const k of ["break", "prayer"]) if (m[k] && +m[k].after === i + 1) rows.push(row(t(k === "break" ? "duty_break" : "slot_prayer"), m[k], afterSel(k), rm(k)));
    });
    if (m.late) rows.push(row(t("duty_late"), m.late, null, rm("late")));
    const missing = [["breakfast", "slot_breakfast"], ["break", "duty_break"], ["prayer", "slot_prayer"], ["late", "duty_late"]].filter(([k]) => !m[k]);
    const addPart = ([k, key]) => h("button", { class: "btn small", type: "button", onClick: () => {
      const last = m.periods[m.periods.length - 1], end = toMin(last.end);
      if (k === "breakfast") { const s = toMin(m.periods[0].start); m.breakfast = { before: "1", start: fromMin(Math.max(0, s - 15)), end: m.periods[0].start }; }
      else if (k === "late") m.late = { start: last.end, end: fromMin(Math.min(1439, end + 30)) };
      else { const i = Math.max(1, Math.floor(m.periods.length / 2)), at = m.periods[i - 1].end; m[k] = { after: String(i), start: at, end: fromMin(Math.min(1439, toMin(at) + (k === "break" ? 30 : 10))) }; }
      drawTable(); } }, icon("plus"), t(key));
    table.replaceChildren(h("h4", {}, t("bl_table_h")), ...rows, missing.length ? h("div", { class: "row", style: { marginTop: ".6rem" } }, h("span", { class: "muted small" }, t("bl_add")), missing.map(addPart)) : null);
  }
  drawTable();
  box.append(h("p", { class: "muted" }, t("bl_lead")), ...(cfg.custom ? [h("div", { class: "banner info" }, icon("info"), h("div", {}, t("bl_custom")))] : []), quick, h("div", { class: "panel" }, table));

  const modalRef = modal({ title: t("tt_shape"), wide: true, body: box, actions: [
    ...(cfg.custom ? [{ label: t("bl_reset"), onClick: async () => {
      if (!(await confirmBox(t("bl_reset_confirm"), { danger: false, okLabel: t("ok") }))) return false;
      if (beforeSave) await beforeSave();
      const ok = await guarded(() => api.post("/api/bell/reset", {})); if (!ok) return false; toast(t("saved")); onSaved && onSaved(); return true; } }] : []),
    { label: t("cancel") },
    { label: t("save"), kind: "primary", onClick: async () => {
      const lost = m.periods.length < oldCount ? usedCells(m.periods.length) : 0;
      if (lost && !(await confirmBox(t("bl_reduce_warn", { n: lost }), { danger: false, okLabel: t("ok") }))) return false;
      if (beforeSave) await beforeSave();
      const ok = await guarded(() => api.put("/api/bell", { bell: m })); if (!ok) return false; toast(t("saved")); onSaved && onSaved(); return true; } }] });
  return modalRef;
}
