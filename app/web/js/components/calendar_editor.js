import { dateField } from "./date3.js";
import { h, icon } from "../dom.js";
import { t } from "../i18n.js";
import { api } from "../api.js";

function guessYear() {
  const now = new Date();
  const y = now.getFullYear();
  return now.getMonth() >= 6 ? `${y}-${y + 1}` : `${y - 1}-${y}`;
}

// Academic year, three trimesters, holidays (and optionally events).
export function calendarEditor({ calendar, withEvents = false, onChange }) {
  const cal = JSON.parse(JSON.stringify(calendar));
  cal.academic_year ||= guessYear();
  while (cal.trimesters.length < 3) cal.trimesters.push({ name: `T${cal.trimesters.length + 1}`, start: "", end: "", week1_start: "" });
  const root = h("div", {});
  const changed = () => onChange && onChange();
  // Holidays without a name get the school's official name for that day.
  let official = [];
  let officialEvents = [];
  const officialName = (iso) => (official.find((x) => x.start <= iso && iso <= (x.end || x.start)) || {}).name || "";
  api.get("/api/school-calendar").then((c) => {
    official = c.holidays || []; officialEvents = c.events || [];
    let filled = false;  // rows saved earlier without a name: an official holiday gets its name, a school event (revision, exams...) is not a holiday
    const keep = [];
    for (const hd of cal.holidays) {
      if (hd.start && !hd.name.trim()) {
        const hol = official.find((x) => x.start <= hd.start && hd.start <= (x.end || x.start));
        if (hol) { hd.name = hol.name; filled = true; }
        else if (officialEvents.some((x) => hd.start <= x.date && x.date <= (hd.end || hd.start))) { filled = true; continue; }
      }
      keep.push(hd);
    }
    if (filled) { cal.holidays = keep; changed(); render(); }
  }).catch(() => {});

  const byDate = (k) => (x, y) => (x[k] || "~").localeCompare(y[k] || "~");

  // the school events list is long; its rows are only built when the teacher opens it
  const evBox = h("div", { class: "scroll-list" });
  const eventRows = () => cal.events.map((ev, i) => h("div", { class: "list-row two" },
    dateInput(ev, "date"),
    h("input", { type: "text", value: ev.name, placeholder: t("event_name"), "aria-label": t("event_name"), required: true, onInput: (e) => { ev.name = e.target.value; changed(); } }),
    h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { cal.events.splice(i, 1); changed(); render(); } }, icon("trash"))));

  function render() {
    evBox.replaceChildren(evOpen ? eventRows() : []);
    root.replaceChildren(
      h("label", { class: "field", style: { maxWidth: "220px" } }, h("span", { class: "label" }, t("academic_year")),
        h("input", { type: "text", value: cal.academic_year, placeholder: "2026-2027", dir: "ltr", pattern: "\\d{4}-\\d{4}", "data-label": t("academic_year"),
          onInput: (e) => { cal.academic_year = e.target.value; changed(); } })),
      h("h3", { class: "sec" }, t("trimesters")),
      h("div", { class: "tri-head small muted" }, h("span", {}), h("span", {}, t("starts_on")), h("span", {}, t("ends_on")), h("span", { title: t("week1_hint") }, t("week1_start"))),
      cal.trimesters.map((tr) => h("div", { class: "tri-row" },
        h("b", {}, t("trimester_n", { n: tr.name.replace(/\D/g, "") || tr.name })),
        dateInput(tr, "start"), dateInput(tr, "end"), dateInput(tr, "week1_start"))),
      h("span", { class: "hint" }, t("week1_hint")),

      h("div", { class: "sec-row" }, h("h3", {}, `${t("holidays")} (${cal.holidays.length})`),
        h("button", { class: "btn small", onClick: () => { cal.holidays.push({ start: "", end: "", name: "" }); changed(); render(); } }, icon("plus"), t("add_holiday"))),
      cal.holidays.length ? h("div", { class: "list-head small muted" }, h("span", {}, t("from_date")), h("span", {}, t("to_date_optional")), h("span", {}, t("holiday_name")), h("span", {})) : h("p", { class: "muted small" }, t("holidays_hint")),
      h("div", {}, cal.holidays.map((hd, i) => h("div", { class: "list-row" },
        dateInput(hd, "start", () => { if (!hd.name.trim() && hd.start) { hd.name = officialName(hd.start); render(); } }), dateInput(hd, "end"),
        h("input", { type: "text", value: hd.name, placeholder: t("holiday_name"), "aria-label": t("holiday_name"), required: true, onInput: (e) => { hd.name = e.target.value; changed(); } }),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { cal.holidays.splice(i, 1); changed(); render(); } }, icon("trash"))))),

      withEvents ? [
        h("div", { class: "sec-row" }, h("h3", {}, `${t("events")} (${cal.events.length})`),
          h("button", { class: "btn small", onClick: () => { cal.events.push({ date: "", name: "" }); evOpen = true; changed(); render(); } }, icon("plus"), t("add_event"))),
        h("details", { class: "more", open: evOpen, onToggle: (e) => { evOpen = e.target.open; if (evOpen && !evBox.childElementCount) evBox.replaceChildren(eventRows()); } },
          h("summary", {}, t("show_events")),
          evBox)
      ] : null);
  }
  let evOpen = false;
  cal.holidays.sort(byDate("start")); cal.events.sort(byDate("date"));

  function dateInput(obj, key, after) {
    return dateField({ value: obj[key] || "", label: key, onChange: (v) => { obj[key] = v; changed(); if (after) after(); } });
  }

  render();
  return {
    el: root,
    // Empty rows are dropped so the teacher is never blocked by a half-filled line.
    value: () => ({
      ...cal,
      holidays: cal.holidays.filter((x) => x.start),
      events: cal.events.filter((x) => x.date && x.name),
      // keep T1..Tn in order up to the last one that has dates, so "T2" always means the second trimester
      trimesters: cal.trimesters.slice(0, 1 + Math.max(-1, ...cal.trimesters.map((x, i) => (x.start || x.end ? i : -1)))),
    }),
  };
}
