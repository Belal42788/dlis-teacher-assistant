import { h, icon } from "../dom.js";
import { t } from "../i18n.js";
import { dayName, shortRoomLabel, fmt12, stageTone } from "../labels.js";

// Weekly timetable: one row per school day (Sunday first), one column per period.
// Period times are fixed by the school. Between period 4 and 5 there is a "break duty" column,
// and at the end of the day a "late duty" column: tick the days you have them.
export function timetableEditor({ timetable, structure, workingDays, onChange }) {
  const periods = timetable.periods || [];
  const bell = timetable.bell || {};
  const grid = JSON.parse(JSON.stringify(timetable.grid || {}));
  const duties = JSON.parse(JSON.stringify(timetable.duties || {}));
  const overrides = timetable.overrides || {};
  const changed = () => onChange && onChange();
  const rooms = structure.rooms;
  const breakAfter = String(bell.break?.after ?? "4");

  const options = () => [h("option", { value: "" }, "—"), ...rooms.map((r) => h("option", { value: r.id }, shortRoomLabel(r, structure)))];

  const cols = [];
  for (const p of periods) {
    if (bell.breakfast && p.name === bell.breakfast.before) cols.push({ kind: "breakfast", span: bell.breakfast });
    cols.push({ kind: "period", p });
    if (p.name === breakAfter && bell.break) cols.push({ kind: "break", span: bell.break });
    if (bell.prayer && p.name === bell.prayer.after) cols.push({ kind: "prayer", span: bell.prayer });
  }
  if (bell.late) cols.push({ kind: "late", span: bell.late });

  const timeText = (a, b) => h("div", { class: "times" }, h("span", { class: "dir-ltr" }, fmt12(a)), h("span", { class: "dir-ltr" }, fmt12(b)));

  const isDuty = (c) => c.kind === "break" || c.kind === "late";
  const head = cols.map((c) => c.kind === "period"
    ? h("th", { class: "p", scope: "col" }, h("div", { class: "pn" }, t("period_n", { n: c.p.name })), timeText(c.p.start, c.p.end))
    : h("th", { class: `p ${isDuty(c) ? "duty-h" : "info-h"} ${c.kind}`, scope: "col" },
      h("div", { class: "pn" }, t(isDuty(c) ? `duty_${c.kind}` : `slot_${c.kind}`)), timeText(c.span.start, c.span.end)));

  function cell(day, c) {
    if (c.kind === "period") {
      const sel = h("select", {
        "aria-label": `${dayName(day)} - ${t("period_n", { n: c.p.name })}`,
        onChange: (e) => { (grid[day] ||= {})[c.p.name] = e.target.value; sel.classList.toggle("filled", !!e.target.value); tint(); changed(); },
      }, options());
      const tint = () => { const r = rooms.find((x) => x.id === sel.value); sel.style.setProperty("--tone", r ? stageTone(r.grade_id) : ""); };
      sel.value = (grid[day] || {})[c.p.name] || ""; tint();
      sel.classList.toggle("filled", !!sel.value);
      return h("td", {}, sel);
    }
    if (!isDuty(c)) return h("td", { class: "info-cell" });
    const on = (duties[day] || []).includes(c.kind);
    const btn = h("button", { class: `duty-btn${on ? " on" : ""}`, type: "button", "aria-pressed": String(on),
      "aria-label": `${dayName(day)} - ${t(`duty_${c.kind}`)}`,
      onClick: () => {
        const cur = new Set(duties[day] || []);
        cur.has(c.kind) ? cur.delete(c.kind) : cur.add(c.kind);
        duties[day] = [...cur];
        const now = cur.has(c.kind);
        btn.classList.toggle("on", now); btn.setAttribute("aria-pressed", String(now)); btn.replaceChildren(now ? icon("check") : "");
        changed();
      } }, on ? icon("check") : "");
    return h("td", { class: "duty-cell" }, btn);
  }

  const table = h("table", { class: "grid" },
    h("thead", {}, h("tr", {}, h("th", { class: "d" }, t("day")), head)),
    h("tbody", {}, workingDays.map((d) => h("tr", {}, h("th", { class: "d", scope: "row" }, dayName(d)), cols.map((c) => cell(d, c))))));

  const el = h("div", {},
    rooms.length ? null : h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("add_classes_first"))),
    h("p", { class: "muted small", style: { margin: "0 0 .6rem" } }, icon("clock"), " ", t("fixed_times_note")),
    h("div", { class: "tt-wrap" }, table));

  return { el, value: () => ({ grid, overrides, duties }) };
}
