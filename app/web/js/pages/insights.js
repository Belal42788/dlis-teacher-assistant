import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { hubTabs } from "../components/hubtabs.js";
import { roomLabel, triName, fmtShort } from "../labels.js";

const memo = { room: "", tri: null };
const tone = (v) => (v === null ? "none" : v >= 85 ? "good" : v >= 60 ? "ok" : "low");

// One class at a glance: class average, marks week by week, students who need follow-up, lessons taught.
export async function renderInsights(root) {
  const [structure, ov] = await Promise.all([api.get("/api/structure"), api.get("/api/overview")]);
  const rooms = structure.rooms, tris = ov.trimesters.filter((x) => x.weeks.length), pos = ov.position;
  const tabs = hubTabs("classes", "insights");
  if (!rooms.length || !tris.length) { root.replaceChildren(h("div", { class: "page" }, tabs, h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_rooms"))))); return; }
  if (!rooms.some((r) => r.id === memo.room)) memo.room = rooms[0].id;
  if (memo.tri === null || !tris.some((x) => x.index === memo.tri)) memo.tri = pos.state === "in_term" ? pos.trimester : tris[0].index;
  const roomSel = h("select", { "aria-label": t("d_class"), onChange: () => { memo.room = roomSel.value; load(); } }, rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const triSel = h("select", { "aria-label": t("d_trimester"), onChange: () => { memo.tri = +triSel.value; load(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  roomSel.value = memo.room; triSel.value = memo.tri;
  const body = h("div", {});
  const kpi = (label, value, sub) => h("div", { class: "kpi" }, h("div", { class: "kpi-v" }, value), h("div", { class: "kpi-l" }, label), sub ? h("div", { class: "muted small" }, sub) : null);

  async function load() {
    const r = await guarded(() => api.get(`/api/insights?room=${memo.room}&tri=${memo.tri}`));
    if (!r) return;
    if (!r.weeks.length) {
      body.replaceChildren(h("div", { class: "banner info" }, icon("info"), h("div", { class: "grow" }, t("in_none")), h("a", { class: "btn small primary", href: "#/grades" }, t("nav_grades"))));
      if (r.lessons) body.append(h("div", { class: "kpis" }, kpi(t("in_lessons"), r.lessons, r.last_topic)));
      return;
    }
    const need = r.rows.filter((x) => x.attention);
    body.replaceChildren(
      h("div", { class: "kpis" },
        kpi(t("in_avg"), r.avg === null ? "—" : `${r.avg}%`), kpi(t("students"), r.students), kpi(t("in_lessons"), r.lessons, r.last_topic ? `${t("in_last")}: ${r.last_topic}` : ""),
        kpi(t("in_absences"), r.absences, t("in_absences_hint"))),
      h("div", { class: "panel" }, h("h3", {}, t("in_by_week")),
        h("div", { class: "bars", role: "img", "aria-label": t("in_by_week") }, r.weeks.map((w) => h("div", { class: "bar-col" },
          h("div", { class: "bar-v" }, w.avg === null ? "—" : `${w.avg}%`),
          h("div", { class: "bar-track" }, h("div", { class: `bar ${tone(w.avg)}`, style: { height: `${w.avg || 0}%` } })),
          h("div", { class: "bar-l" }, t("week_n", { n: w.week })),
          w.absent ? h("div", { class: "muted small" }, `${t("gr_absent")}: ${w.absent}`) : null)))),
      h("div", { class: "panel" }, h("h3", {}, t("in_attention")), h("p", { class: "muted small" }, t("in_attention_rule", { p: r.attention_pct, n: r.attention_absent })),
        need.length ? h("table", { class: "tasks-table" }, h("thead", {}, h("tr", {}, h("th", {}, t("students")), h("th", {}, t("in_avg")), h("th", {}, t("gr_absent")))),
          h("tbody", {}, need.map((x) => h("tr", {}, h("td", {}, x.name), h("td", { class: `tone-${tone(x.avg)}` }, x.avg === null ? "—" : `${x.avg}%`), h("td", {}, x.absent))))) : h("p", { class: "muted" }, icon("check"), " ", t("in_all_fine"))),
      h("details", { class: "panel fold" }, h("summary", {}, t("in_all")),
        h("table", { class: "tasks-table" }, h("thead", {}, h("tr", {}, h("th", {}, t("students")), h("th", {}, t("in_avg")), h("th", {}, t("in_now")), h("th", {}, t("gr_absent")))),
          h("tbody", {}, r.rows.map((x) => h("tr", {}, h("td", {}, x.name), h("td", { class: `tone-${tone(x.avg)}` }, x.avg === null ? "—" : `${x.avg}%`), h("td", {}, x.last === null ? "—" : `${x.last}%`), h("td", {}, x.absent)))))));
  }
  root.replaceChildren(h("div", { class: "page" }, tabs,
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("in_title")), h("p", {}, t("in_lead")))),
    h("div", { class: "panel sticky-pick" }, h("div", { class: "pick-row" }, h("label", {}, h("span", { class: "label" }, t("d_class")), roomSel), h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel))),
    body));
  await load();
}
