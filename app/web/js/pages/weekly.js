import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { hubTabs } from "../components/hubtabs.js";
import { gradeName, triName, fmtShort, stageTone } from "../labels.js";

const memo = { tri: "", week: "" };
const NEXT = { wait: "done", done: "no", no: "wait" };
const MARK = { wait: "○", done: "✓", no: "✗" };

// The weekly jobs for every grade as one table: click a cell to change it  (not yet → done → not done).
export async function renderWeekly(root) {
  const ov = await api.get("/api/overview");
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  if (!tris.length) { root.replaceChildren(h("div", { class: "page" }, hubTabs("tasks", "weekly"), h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_calendar"))))); return; }
  const pos = ov.position;
  const triSel = h("select", { onChange: () => { memo.tri = triSel.value; fillWeeks(true); load(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  const weekSel = h("select", { onChange: () => { memo.week = weekSel.value; load(); } });
  triSel.value = memo.tri !== "" && tris.some((x) => String(x.index) === String(memo.tri)) ? memo.tri : (pos.state === "in_term" ? pos.trimester : tris[0].index);
  memo.tri = triSel.value;
  function fillWeeks(reset) {
    const tri = tris.find((x) => x.index === +triSel.value) || tris[0];
    weekSel.replaceChildren(tri.weeks.map((w) => h("option", { value: w.number }, `${t("week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}`)));
    const want = !reset && memo.week !== "" ? memo.week : (pos.state === "in_term" && pos.trimester === +triSel.value ? pos.week : tri.weeks[0].number);
    weekSel.value = tri.weeks.some((w) => String(w.number) === String(want)) ? want : tri.weeks[0].number;
    memo.week = weekSel.value;
  }
  const box = h("div", {});
  const sum = h("span", { class: "tag" });
  async function load() {
    const d = await guarded(() => api.get(`/api/weekly?tri=${triSel.value}&week=${weekSel.value}`)); if (!d) return;
    draw(d);
  }
  function draw(d) {
    sum.textContent = t("wc_summary", { done: d.done, total: d.total });
    if (!d.rows.length) { box.replaceChildren(h("p", { class: "muted" }, t("wk_none"))); return; }
    box.replaceChildren(h("div", { class: "paper" }, h("table", { class: "wc" },
      h("thead", {}, h("tr", {}, h("th", {}, t("wc_grade")), d.tasks.map((k) => h("th", {}, t(`wc_t_${k}`))))),
      h("tbody", {}, d.rows.map((r) => h("tr", {}, h("th", { scope: "row" }, h("span", { class: "dot", style: { background: stageTone(r.grade_id) } }), " ", r.name),
        d.tasks.map((k) => {
          const st = r.states[k];
          const b = h("button", { class: `wc-cell ${st}`, "aria-label": `${r.name} — ${t(`wc_t_${k}`)}: ${t(`wc_s_${st}`)}`, title: t(`wc_s_${st}`),
            onClick: async () => { const nd = await guarded(() => api.put("/api/weekly", { trimester: +triSel.value, week: +weekSel.value, grade_id: r.grade_id, task: k, state: NEXT[st] })); if (nd) draw(nd); } },
            MARK[st], h("span", { class: "wc-txt" }, t(`wc_s_${st}`)));
          return h("td", {}, b);
        })))))),
      h("p", { class: "muted small", style: { marginTop: ".6rem" } }, t("wc_hint")));
  }
  fillWeeks(false);
  root.replaceChildren(h("div", { class: "page" }, hubTabs("tasks", "weekly"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("hub_weekly")), h("p", {}, t("wc_lead"))), sum),
    h("div", { class: "panel" }, h("div", { class: "pick-row" }, h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel), h("label", {}, h("span", { class: "label" }, t("d_week")), weekSel))),
    box));
  await load();
}
