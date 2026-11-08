import { h, icon } from "../dom.js";
import { t } from "../i18n.js";

// Pages that belong together share one menu entry and a small tab row at the top.
const GROUPS = {
  library: [["library", "lb_tab_files"], ["publish", "lb_tab_shared"], ["sources", "nav_sources"], ["bank", "nav_bank"]],
  classes: [["classes", "hub_students"], ["log", "nav_log"], ["progress", "nav_progress"], ["grades", "nav_grades"], ["behavior", "nav_behavior"], ["seating", "nav_seating"], ["insights", "nav_insights"]],
  parents: [["announcements", "an_tab"], ["parentweek", "nav_parentweek"]],
  tasks: [["tasks", "hub_tasks"], ["reminders", "hub_reminders"]],
};
// The library has four tabs that sound alike, so each one says what is in it and what you do there (hh_<tab>_has / _do),
// and, where two tabs are easy to mix up, where the other thing lives (hh_<tab>_not + this link).
const HINT_LINK = { library: ["sources", "nav_sources"], publish: ["library", "lb_tab_files"], sources: ["library", "lb_tab_files"] };

export function hubTabs(group, active) {
  const tabs = h("div", { class: "seg", role: "tablist" }, GROUPS[group].map(([id, key]) =>
    h("a", { class: "seg-btn", role: "tab", href: `#/${id}`, "aria-selected": String(id === active) }, t(key))));
  if (group !== "library") return tabs;
  const link = HINT_LINK[active];
  return h("div", {}, tabs, h("div", { class: "tab-hint" }, icon("info"), h("div", {},
    h("div", {}, h("b", {}, t("hub_has")), ": ", t(`hh_${active}_has`)),
    h("div", {}, h("b", {}, t("hub_do")), ": ", t(`hh_${active}_do`)),
    link ? h("div", { class: "muted" }, t(`hh_${active}_not`), " ", h("a", { href: `#/${link[0]}` }, t(link[1]))) : null)));
}
