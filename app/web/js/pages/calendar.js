import { h, toast, icon, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { calendarEditor } from "../components/calendar_editor.js";
import { fmtShort, fmtDay, triName, localName, groupHolidays } from "../labels.js";

export async function renderCalendar(root) {
  const cal = await api.get("/api/calendar");
  const weeksBox = h("div", {});
  const saveBtn = h("button", { class: "btn primary", disabled: true, onClick: save }, t("save"));
  const status = h("span", { class: "saved" });
  const ed = calendarEditor({ calendar: cal, withEvents: true, onChange: () => { saveBtn.disabled = false; status.textContent = ""; } });

  state.isDirty = () => !saveBtn.disabled;

  async function save() {
    const r = await guarded(() => api.put("/api/calendar", ed.value()));
    if (r) { saveBtn.disabled = true; status.textContent = "✓ " + t("saved"); toast(t("saved")); await drawWeeks(); }
  }

  async function drawWeeks() {
    const ov = await api.get("/api/overview");
    const nowWeek = ov.position.state === "in_term" ? ov.position : null;
    weeksBox.replaceChildren(ov.trimesters.every((x) => !x.weeks.length)
      ? h("p", { class: "muted" }, t("weeks_empty"))
      : ov.trimesters.filter((x) => x.weeks.length).map((tri) => h("div", { style: { marginBottom: "1.6rem" } },
        h("h3", { style: { marginBottom: ".5rem" } }, `${triName(tri.name)} · ${t("weeks_count", { n: tri.weeks.length })}`),
        h("table", { class: "weeks" },
          h("thead", {}, h("tr", {}, h("th", {}, t("week")), h("th", {}, t("dates")), h("th", {}, t("school_days")), h("th", {}, t("notes")))),
          h("tbody", {}, tri.weeks.map((w) => h("tr", { class: nowWeek && nowWeek.trimester === tri.index && nowWeek.week === w.number ? "now" : "" },
            h("td", {}, h("b", {}, w.number)),
            h("td", {}, h("span", { class: "dir-ltr" }, `${fmtShort(w.start)} → ${fmtShort(w.end)}`)),
            h("td", {}, w.school_days),
            h("td", {}, groupHolidays(w.holidays).map((x) => h("span", { class: "tag" }, `${localName(x.name) || t("holiday")} · ${x.from === x.to ? fmtDay(x.from) : fmtDay(x.from) + " → " + fmtDay(x.to)}`))))))))));
  }

  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_calendar")), h("p", {}, t("calendar_page_lead"))),
      h("div", { class: "row" }, status,
        h("button", { class: "btn", onClick: async () => {
          if (!(await confirmBox(t("school_cal_replace"), { okLabel: t("school_cal_replace_ok"), danger: false }))) return;
          const sc = await guarded(() => api.get("/api/school-calendar"));
          if (sc && await guarded(() => api.put("/api/calendar", sc))) { state.isDirty = null; await renderCalendar(root); toast(t("saved")); }
        } }, icon("download"), t("load_school_calendar")), saveBtn)),
    h("div", { class: "panel" }, ed.el),
    h("div", { class: "panel" }, h("h2", { style: { marginBottom: "1rem" } }, t("weeks_title")), weeksBox)));
  await drawWeeks();
}
