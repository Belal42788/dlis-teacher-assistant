import { h, icon } from "../dom.js";
import { t } from "../i18n.js";

// Pages that belong together share one menu entry and a small tab row at the top.
const GROUPS = {
  library: [["library", "lb_tab_files"], ["bank", "nav_bank"]],
  create: [["docs", "cr_tab_docs"], ["tools", "nav_tools"]],
  classes: [["classes", "hub_students"], ["log", "nav_log"], ["progress", "nav_progress"], ["grades", "nav_grades"], ["behavior", "nav_behavior"], ["seating", "nav_seating"], ["insights", "nav_insights"]],
  tasks: [["tasks", "hub_tasks"], ["reminders", "hub_reminders"]],
};
// «My files» has two tabs, so each one says what is in it and what you do there (hh_<tab>_has / _do).

export function hubTabs(group, active) {
  const tabs = h("div", { class: "seg", role: "tablist" }, GROUPS[group].map(([id, key]) =>
    h("a", { class: "seg-btn", role: "tab", href: `#/${id}`, "aria-selected": String(id === active) }, t(key))));
  if (group !== "library") return tabs;
  return h("div", {}, tabs, h("div", { class: "tab-hint" }, icon("info"), h("div", {},
    h("div", {}, h("b", {}, t("hub_has")), ": ", t(`hh_${active}_has`)),
    h("div", {}, h("b", {}, t("hub_do")), ": ", t(`hh_${active}_do`)))));
}
