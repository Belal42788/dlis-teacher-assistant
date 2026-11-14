import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { timetableEditor } from "../components/timetable_editor.js";
import { openBellEditor } from "../components/bell_editor.js";

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
  // lessons that would no longer show if the day had only n lessons (they stay saved and come back if the number goes up again)
  const usedCells = (n) => Object.values(tt.grid || {}).reduce((sum, row) => sum + Object.entries(row).filter(([p, r]) => r && +p > n).length, 0);
  const shape = () => openBellEditor({ usedCells, beforeSave: async () => { if (dirty) await save(); }, onSaved: () => { dirty = false; renderTimetable(root); } });

  root.replaceChildren(h("div", { class: "page full" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_timetable")), h("p", {}, t("timetable_page_lead"))),
      h("div", { class: "row" }, status, h("button", { class: "btn", onClick: shape }, icon("clock"), t("tt_shape")), saveBtn)),
    h("div", { class: "panel" }, ed.el)));
}
