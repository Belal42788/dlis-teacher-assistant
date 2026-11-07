import { h } from "../dom.js";
import { t } from "../i18n.js";

// Pages that belong together share one menu entry and a small tab row at the top.
const GROUPS = {
  library: [["library", "lb_tab_files"], ["publish", "lb_tab_shared"], ["sources", "nav_sources"]],
  classes: [["classes", "hub_students"], ["log", "nav_log"], ["progress", "nav_progress"], ["grades", "nav_grades"], ["behavior", "nav_behavior"], ["seating", "nav_seating"], ["insights", "nav_insights"]],
  parents: [["announcements", "an_tab"], ["parentweek", "nav_parentweek"]],
  tasks: [["tasks", "hub_tasks"], ["reminders", "hub_reminders"]],
};
export function hubTabs(group, active) {
  return h("div", { class: "seg", role: "tablist" }, GROUPS[group].map(([id, key]) =>
    h("a", { class: "seg-btn", role: "tab", href: `#/${id}`, "aria-selected": String(id === active) }, t(key))));
}
