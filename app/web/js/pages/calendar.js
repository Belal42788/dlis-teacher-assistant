import { h, toast, icon, confirmBox, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { calendarEditor } from "../components/calendar_editor.js";
import { weeksLine, termCard, monthView, upcoming, calendarIndex } from "../components/calendar_views.js";
import { fmtDate, addDays } from "../labels.js";

// The calendar page is a picture of the school year first (weeks line + month); the dates are edited behind the "Edit" button.
export async function renderCalendar(root, edit = false) {
  const [cal, ov] = await Promise.all([api.get("/api/calendar"), api.get("/api/overview")]);
  if (edit === true) return drawEditor(root, cal);

  const view = { y: Number(ov.today.slice(0, 4)), m: Number(ov.today.slice(5, 7)) - 1 };
  const box = h("div", {});
  let idx = calendarIndex(cal, ov);

  function drawMonth() {
    box.replaceChildren(h("div", { class: "mo-wrap panel" }, monthView({ cal, ov, idx, workingDays: state.settings?.working_days, view, onMove: (n) => {
      if (n === 0) { view.y = Number(ov.today.slice(0, 4)); view.m = Number(ov.today.slice(5, 7)) - 1; }
      else { const d = new Date(Date.UTC(view.y, view.m + n, 1)); view.y = d.getUTCFullYear(); view.m = d.getUTCMonth(); }
      drawMonth();
    }, onDay: (iso) => dayNotes(iso) }), upcoming(cal, ov)));
  }

  // The notes of one day: add one, or remove the ones you added. Official school events are listed too.
  function dayNotes(iso) {
    const mine = () => (cal.events || []).map((e, i) => ({ e, i })).filter((x) => x.e.date === iso);
    const list = h("div", { class: "list" });
    const name = h("input", { type: "text", placeholder: t("event_name"), "aria-label": t("event_name"), maxlength: 120,
      onKeydown: (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); add(); } } });
    const holName = idx.hol.get(iso);
    async function save() {
      const r = await guarded(() => api.put("/api/calendar", cal)); if (!r) return false;
      idx = calendarIndex(cal, ov); drawMonth(); return true;
    }
    async function add() {
      const v = name.value.trim(); if (!v) return;
      cal.events = [...(cal.events || []), { date: iso, name: v }].sort((a, b) => (a.date || "~").localeCompare(b.date || "~"));
      if (await save()) { name.value = ""; drawList(); }
    }
    function drawList() {
      const rows = mine();
      list.replaceChildren(...(rows.length ? rows.map(({ i, e }) => h("div", { class: "list-row", style: { gridTemplateColumns: "1fr auto" } }, h("span", {}, e.name),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: async () => { cal.events.splice(i, 1); if (await save()) drawList(); } }, icon("trash"))))
        : [h("p", { class: "muted small" }, t("cal_no_notes"))]));
    }
    drawList();
    modal({ title: fmtDate(iso), body: h("div", {}, holName ? h("div", { class: "banner holiday" }, icon("info"), h("div", {}, holName)) : null, list, h("div", { class: "row", style: { marginTop: ".6rem" } }, name,
      h("button", { class: "btn primary", onClick: add }, icon("plus"), t("add_event")))), actions: [{ label: t("close"), onClick: () => {} }] });
    setTimeout(() => name.focus(), 50);
  }

  root.replaceChildren(h("div", { class: "page full" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_calendar")), h("p", {}, t("calendar_page_lead"))),
      h("div", { class: "row" }, h("button", { class: "btn", onClick: () => renderCalendar(root, true) }, icon("edit"), t("cal_edit")))),
    weeksLine(ov, cal, idx, (start) => { const d = new Date(`${start}T00:00:00Z`); view.y = d.getUTCFullYear(); view.m = d.getUTCMonth(); drawMonth(); box.scrollIntoView({ behavior: "smooth", block: "start" }); }),
    termCard(ov), box));
  drawMonth();
}

// ---------- editing the dates: trimesters, holidays and events (the old page, now behind a button)
function drawEditor(root, cal) {
  const saveBtn = h("button", { class: "btn primary", disabled: true, onClick: save }, t("save"));
  const status = h("span", { class: "saved" });
  const ed = calendarEditor({ calendar: cal, withEvents: true, onChange: () => { saveBtn.disabled = false; status.textContent = ""; } });
  state.isDirty = () => !saveBtn.disabled;
  async function save() {
    const r = await guarded(() => api.put("/api/calendar", ed.value()));
    if (r) { saveBtn.disabled = true; state.isDirty = null; toast(t("saved")); await renderCalendar(root); }
  }
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("cal_edit")), h("p", {}, t("calendar_page_lead"))),
      h("div", { class: "row" }, status,
        h("button", { class: "btn", onClick: async () => {
          if (!(await confirmBox(t("school_cal_replace"), { okLabel: t("school_cal_replace_ok"), danger: false }))) return;
          const sc = await guarded(() => api.get("/api/school-calendar"));
          if (sc && await guarded(() => api.put("/api/calendar", sc))) { state.isDirty = null; await renderCalendar(root, true); toast(t("saved")); }
        } }, icon("download"), t("load_school_calendar")),
        h("button", { class: "btn", onClick: async () => {
          if (state.isDirty && state.isDirty() && !(await confirmBox(t("unsaved_confirm"), { okLabel: t("leave_page"), danger: false }))) return;
          state.isDirty = null; await renderCalendar(root);
        } }, t("cal_back")), saveBtn)),
    h("div", { class: "panel" }, ed.el)));
}
