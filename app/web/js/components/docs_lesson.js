import { showProblems } from "./validate.js";
import { h, icon, toast } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { sourcePicker } from "./source_pick.js";

const DAY_FIELDS = ["sunday", "monday", "tuesday", "wednesday", "thursday"];

// The lesson plan box of the "Create files" page.
export async function lessonPanel(ctx) {
  const { sel, gradeOf, aiNeeded, aiButton, sid, run, showResult } = ctx;
  const srcLp = await sourcePicker(async (id, s) => { if (id && s && s.topic && !topic.value.trim()) topic.value = s.topic; });
  const lp = {};
  const field = (key, label, rows = 2, ph = "") => { lp[key] = h("textarea", { rows, placeholder: ph, style: { minHeight: "0" } }); return h("label", { class: "field" }, h("span", { class: "label" }, label), lp[key]); };
  const topic = h("input", { type: "text", required: true, "data-label": t("d_topic") }); lp.topic = topic;
  const lpBtn = h("button", { class: "btn primary", onClick: () => run(lpBtn, async () => {
    const content = Object.fromEntries(Object.entries(lp).map(([k, el]) => [k, el.value]));
    showResult(await api.post("/api/docs/lesson-plan", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, content }));
  }) }, icon("file"), t("d_create_lp"));
  const lpAi = aiButton(t("ai_write"), async () => {
    if (!topic.value.trim()) { showProblems(lpPanel, [{ el: topic, label: t("d_topic"), reason: t("v_required") }]); return null; }
    const r = await api.post("/api/ai/lesson", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, topic: topic.value.trim(), source_id: sid(srcLp) });
    for (const [k, v] of Object.entries(r.content)) if (lp[k] && v) lp[k].value = v;
    return true;
  });
  const lpPanel = h("div", { class: "panel" }, h("h3", {}, t("d_lp_title")), h("p", { class: "muted small" }, t("d_lp_lead")), aiNeeded(),
    srcLp ? srcLp.el : null, h("label", { class: "field" }, h("span", { class: "label" }, t("d_topic")), topic),
    field("objectives", t("d_objectives"), 3),
    h("details", { class: "more" }, h("summary", {}, t("d_steps_by_day")),
      DAY_FIELDS.map((d) => field(d, t(`day_${d[0].toUpperCase()}${d.slice(1)}`), 2))),
    h("details", { class: "more" }, h("summary", {}, t("d_more")),
      field("practice_pages", t("d_practice"), 1), field("activities", t("d_activities")), field("resources", t("d_resources")),
      field("differentiation", t("d_diff")), field("assessment", t("d_assess")), field("reflection", t("d_reflect"))),
    h("div", { class: "row" }, lpAi, lpBtn));
  // days this grade has no lesson: the Word file will say "No session"
  const applyContext = (c) => DAY_FIELDS.forEach((d) => { const off = !c.teach_days.includes(d[0].toUpperCase() + d.slice(1)); lp[d].placeholder = off ? t("d_no_session") : ""; lp[d].classList.toggle("no-session", off); });
  // curriculum objectives from the scheme of work, unless the teacher already typed their own
  const setObjectives = (text) => { if (lp.objectives && (!lp.objectives.value.trim() || lp.objectives.dataset.auto === lp.objectives.value)) { lp.objectives.value = text; lp.objectives.dataset.auto = text; } };
  return { el: lpPanel, topic, applyContext, setObjectives };
}
