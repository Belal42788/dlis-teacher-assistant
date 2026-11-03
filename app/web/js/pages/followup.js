import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { triName } from "../labels.js";

// For the administration: who has finished the week's papers (numbers only, never the files).
export async function renderFollowup(root) {
  const c = await api.get("/api/cloud");
  if (!c.signed_in || c.role !== "admin") {
    root.replaceChildren(h("div", { class: "page" }, h("div", { class: "page-head" }, h("h1", {}, t("nav_followup"))), h("div", { class: "panel" }, h("p", {}, t("fu_admin_only")))));
    return;
  }
  const d = await api.get("/api/status/staff");
  const pct = (r) => (r.total ? Math.round((100 * r.done) / r.total) : 0);
  const cls = (p) => (p >= 80 ? "" : p >= 50 ? "warn" : "bad");
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_followup")), h("p", {}, t("fu_lead")))),
    d.rows.length ? h("div", { class: "paper" }, h("table", { class: "tasks-table" },
      h("thead", {}, h("tr", {}, [t("fu_teacher"), t("fu_week"), t("fu_progress"), t("fu_cover"), t("fu_updated")].map((x) => h("th", {}, x)))),
      h("tbody", {}, d.rows.map((r) => h("tr", {},
        h("td", {}, h("b", {}, r.teacher_name || "—"), h("div", { class: "small muted" }, r.subject)),
        h("td", { class: "small" }, `${r.week}`),
        h("td", {}, h("div", { class: `bar ${cls(pct(r))}`, title: `${pct(r)}%` }, h("i", { style: { width: `${pct(r)}%` } })), h("span", { class: "small muted" }, `${r.done} / ${r.total}`)),
        h("td", { class: "small" }, `${r.progress_percent}%`),
        h("td", { class: "small muted" }, r.updated_at)))))) : h("div", { class: "paper empty" }, h("h3", {}, t("fu_none"))),
    h("p", { class: "muted small" }, t("fu_note"))));
}
