import { h, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { timetableEditor } from "../components/timetable_editor.js";

export async function renderTimetable(root) {
  const [tt, structure, settings] = await Promise.all([api.get("/api/timetable"), api.get("/api/structure"), api.get("/api/settings")]);
  state.structure = structure;
  let dirty = false;
  const saveBtn = h("button", { class: "btn primary", disabled: true, onClick: save }, t("save"));
  const status = h("span", { class: "saved" });
  const ed = timetableEditor({ timetable: tt, structure, workingDays: settings.working_days,
    onChange: () => { dirty = true; saveBtn.disabled = false; status.textContent = ""; } });

  async function save() {
    const r = await guarded(() => api.put("/api/timetable", ed.value()));
    if (r) { dirty = false; saveBtn.disabled = true; status.textContent = "✓ " + t("saved"); toast(t("saved")); }
  }
  state.isDirty = () => dirty;

  root.replaceChildren(h("div", { class: "page full" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_timetable")), h("p", {}, t("timetable_page_lead"))),
      h("div", { class: "row" }, status, saveBtn)),
    h("div", { class: "panel" }, ed.el)));
}
