import { hubTabs } from "../components/hubtabs.js";
import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { roomLabel, fmtDate } from "../labels.js";

// How far each class really is: lessons logged against lessons held this term. Also the one-click inspection pack.
export async function renderProgress(root) {
  const [cov, structure, cloud] = await Promise.all([api.get("/api/coverage"), api.get("/api/structure"), api.get("/api/cloud")]);
  const staff = cloud.signed_in && (cloud.role === "teacher" || cloud.role === "admin");
  const room = (id) => { const r = structure.rooms.find((x) => x.id === id); return r ? roomLabel(r, structure) : id; };
  const rows = cov.rows || [];
  root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "progress"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_progress")), h("p", {}, t("pg_lead")))),
    h("div", { class: "row", style: { marginBottom: ".8rem" } },
      h("button", { class: "btn primary", onClick: () => guarded(async () => { const r = await api.post("/api/inspection-pack", {}); await api.post("/api/open", { path: r.path, folder: false }); toast(t("pg_pack_done")); }) }, icon("download"), t("pg_pack")),
      staff ? h("button", { class: "btn", onClick: () => guarded(async () => { const r = await api.post("/api/status/push", {}); toast(r.sent ? t("pg_sent") : t("pg_not_sent")); }) }, icon("send"), t("pg_send")) : null),
    cov.state !== "in_term" ? h("div", { class: "banner info" }, icon("info"), h("div", {}, t("pg_no_term")))
      : !rows.length ? h("div", { class: "paper empty" }, h("h3", {}, t("pg_none")))
      : h("div", { class: "paper" }, h("table", { class: "tasks-table" },
        h("thead", {}, h("tr", {}, [t("d_class"), t("pg_progress"), t("pg_last"), t("pg_planned")].map((x) => h("th", {}, x)))),
        h("tbody", {}, rows.map((r) => h("tr", {},
          h("td", {}, h("b", {}, room(r.room_id))),
          h("td", {}, h("div", { class: `bar ${r.status}`, title: `${r.percent}%` }, h("i", { style: { width: `${r.percent}%` } })), h("span", { class: "small muted" }, t("pg_n_of", { a: r.logged, b: r.held }))),
          h("td", { class: "small" }, r.last_date ? `${fmtDate(r.last_date, { day: "numeric", month: "short" })} · ${r.last_topic || "—"}` : t("pg_never")),
          h("td", { class: "small" }, r.planned_now || "—"))))))));
}
