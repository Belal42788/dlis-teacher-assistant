import { hubTabs } from "../components/hubtabs.js";
import { h } from "../dom.js";
import { t } from "../i18n.js";
import { alarmsPanel } from "../components/reminder_panel.js";

export async function renderReminders(root) {
  root.replaceChildren(h("div", { class: "page" }, hubTabs("tasks", "reminders"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_reminders")), h("p", {}, t("rem_page_lead")))),
    alarmsPanel()));
}
