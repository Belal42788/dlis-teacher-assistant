import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { triName, fmtShort, stageTone } from "../labels.js";

const memo = { tri: "", week: "" };
const NEXT = { wait: "done", done: "no", no: "wait" };
const MARK = { wait: "", done: "✓", no: "✗" };

// Week follow-up: one row per grade, five jobs (three of them with two boxes). Click a box: not yet -> done -> not done.
export async function weeklyPanel() {
  const ov = await api.get("/api/overview");
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  const panel = h("section", { class: "panel wc-panel" });
  if (!tris.length) { panel.append(h("h2", {}, t("hub_weekly")), h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_calendar")))); return panel; }
  const pos = ov.position;
  const triSel = h("select", { "aria-label": t("ch_term"), onChange: () => { memo.tri = triSel.value; fillWeeks(true); load(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  const weekSel = h("select", { "aria-label": t("week"), onChange: () => { memo.week = weekSel.value; load(); } });
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
    const cell = (r, k) => {
      const st = r.states[k], auto = r.auto && r.auto[k];
      return h("td", {}, h("button", { class: `wc-cell ${st}${auto ? " auto" : ""}`, "aria-label": `${r.name} — ${t(`wc_c_${k}`)}: ${t(`wc_s_${st}`)}`, title: `${t(`wc_c_${k}`)}: ${t(`wc_s_${st}`)}${auto ? " · " + t("wc_auto") : ""}`,
        onClick: async () => { const nd = await guarded(() => api.put("/api/weekly", { trimester: +triSel.value, week: +weekSel.value, grade_id: r.grade_id, task: k, state: NEXT[st] })); if (nd) draw(nd); } }, MARK[st]));
    };
    box.replaceChildren(h("div", { class: "wc-scroll" }, h("table", { class: "wc" },
      h("colgroup", {}, h("col", { class: "wc-name" }), d.tasks.map(() => h("col", {}))),
      h("thead", {},
        h("tr", {}, h("th", { rowspan: 2, class: "wc-corner" }, t("wc_grade")), d.groups.map((g) => h("th", { colspan: g.cols.length, rowspan: g.cols.length === 1 ? 2 : 1, class: "wc-g" }, t(`wc_g_${g.id}`)))),
        h("tr", {}, d.groups.filter((g) => g.cols.length > 1).flatMap((g) => g.cols.map((k) => h("th", { class: "wc-sub" }, t(`wc_c_${k}`)))))),
      h("tbody", {}, d.rows.map((r) => h("tr", {}, h("th", { scope: "row" }, h("span", { class: "dot", style: { background: stageTone(r.grade_id) } }), " ", r.name), d.tasks.map((k) => cell(r, k))))))),
      h("p", { class: "muted small", style: { marginTop: ".5rem" } }, h("span", { class: "wc-key done" }, "✓"), t("wc_s_done"), " · ", h("span", { class: "wc-key no" }, "✗"), t("wc_s_no"), " · ", h("span", { class: "wc-key" }), t("wc_s_wait"), " — ", t("wc_hint")));
  }
  fillWeeks(false);
  panel.append(h("div", { class: "sec-row" }, h("h2", { style: { margin: 0 } }, t("hub_weekly")), sum),
    h("div", { class: "wc-pick" }, h("label", { class: "field" }, h("span", { class: "label" }, t("ch_term")), triSel), h("label", { class: "field" }, h("span", { class: "label" }, t("week")), weekSel)), box);
  load();
  return panel;
}
