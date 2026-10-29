import { hubTabs } from "../components/hubtabs.js";
import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { tasksTable } from "../components/tasks_table.js";
import { weeklyPanel } from "./weekly.js";

export async function renderTasks(root) {
  let data = await api.get("/api/tasks");
  const list = h("div", {});
  const title = h("input", { type: "text", placeholder: t("t_what"), "aria-label": t("t_what"), onKeydown: (e) => e.key === "Enter" && add() });
  const imp = h("select", { "aria-label": t("t_importance") }, ["high", "medium", "low"].map((k) => h("option", { value: k }, t(`imp_${k}`))));
  imp.value = "medium";
  const deadline = h("input", { type: "date", "aria-label": t("t_deadline") });
  async function add() {
    if (!title.value.trim()) { title.focus(); return; }
    const r = await guarded(() => api.post("/api/tasks", { title: title.value, importance: imp.value, deadline: deadline.value }));
    if (r) { data = r; title.value = ""; deadline.value = ""; draw(); }
  }
  function draw() {
    list.replaceChildren(tasksTable(data, { showDone: true, onChange: (r) => { data = r; draw(); } }));
  }

  root.replaceChildren(h("div", { class: "page" }, hubTabs("tasks", "tasks"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_tasks")), h("p", {}, t("t_lead")))),
    await weeklyPanel(),
    h("h2", { class: "tasks-h" }, t("hub_tasks")),
    h("div", { class: "panel" }, h("div", { class: "task-add" }, title, imp, deadline, h("button", { class: "btn primary", onClick: add }, icon("plus"), t("t_add")))),
    list));
  draw();
}
