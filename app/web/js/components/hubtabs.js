import { h } from "../dom.js";
import { t } from "../i18n.js";

// Pages that belong together share one menu entry and a small tab row at the top.
const GROUPS = {
  slides: [["slides", "hub_make_slides"], ["sources", "nav_sources"]],
  tasks: [["tasks", "hub_tasks"], ["weekly", "hub_weekly"], ["reminders", "hub_reminders"]],
};
export function hubTabs(group, active) {
  return h("div", { class: "seg", role: "tablist" }, GROUPS[group].map(([id, key]) =>
    h("a", { class: "seg-btn", role: "tab", href: `#/${id}`, "aria-selected": String(id === active) }, t(key))));
}
