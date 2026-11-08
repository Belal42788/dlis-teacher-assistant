import { h, icon, toast } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { sourcePicker } from "./source_pick.js";

// The revision sheet box (words, key points, questions, optional cover page).
export async function revisionPanel(ctx) {
  const { sel, gradeOf, aiNeeded, aiButton, sid, run, showResult } = ctx;
  const srcRv = await sourcePicker((id, s) => { if (id && s && s.topic && !rvTopic.value.trim()) rvTopic.value = s.topic; }, { exact: true });
  const rvTopic = h("input", { type: "text", placeholder: t("rv_topic_ph") });
  const rvWhole = h("input", { type: "checkbox" });
  const rvCount = h("input", { type: "number", min: 3, max: 15, value: 6, style: { width: "5em" } });
  const rvWords = h("textarea", { rows: 4, placeholder: "CPU: the brain of the computer" });
  const rvPoints = h("textarea", { rows: 4, placeholder: "..." });
  const rvQs = h("textarea", { rows: 5, placeholder: "What does the CPU do? | It processes data" });
  const rvAns = h("input", { type: "checkbox", checked: true });
  const rvAi = aiButton(t("ai_write"), async () => {
    if (!rvTopic.value.trim()) { toast(t("ai_need_topic"), "error"); return null; }
    const r = await api.post("/api/ai/revision", { grade_id: gradeOf().id, topic: rvTopic.value.trim(), count: +rvCount.value || 6, source_id: sid(srcRv), ...(srcRv ? srcRv.extra() : {}) });
    rvWords.value = r.words; rvPoints.value = r.points; rvQs.value = r.questions; return true;
  });
  const rvFromSrc = h("button", { class: "btn", onClick: () => run(rvFromSrc, async () => {
    const id = sid(srcRv); if (!id) { toast(t("src_pick_first"), "error"); return; }
    const d = (await api.get(`/api/sources/${id}`)).digest;
    if (!d || !d.topic) { toast(t("src_no_digest"), "error"); return; }
    if (!rvTopic.value.trim()) rvTopic.value = d.topic;
    rvWords.value = d.words.map((w) => `${w.term}: ${w.meaning}`).join("\n"); rvPoints.value = d.points.join("\n"); rvQs.value = d.questions.map((x) => `${x.q} | ${x.a}`).join("\n");
  }) }, icon("file"), t("src_fill_rv"));
  // the cover page (school logo, Cognia logo, subject, covered lessons and book pages) goes inside the same file
  const cvOn = h("input", { type: "checkbox" });
  const cvRows = h("textarea", { rows: 7, placeholder: t("cv_ph") });
  const cvFill = h("button", { class: "btn", onClick: () => run(cvFill, async () => { const r = await api.get(`/api/docs/revision-cover?grade_id=${gradeOf().id}&tri=${sel.tri}`); cvRows.value = r.lines; if (!r.lines) toast(t("cv_none"), "error"); }) }, icon("file"), t("cv_fill"));
  const cvBox = h("div", { class: "fold-body", hidden: true }, h("p", { class: "muted small" }, t("cv_lead")), h("label", { class: "field" }, h("span", { class: "label" }, t("cv_rows")), cvRows), cvFill);
  cvOn.addEventListener("change", () => { cvBox.hidden = !cvOn.checked; });
  const rvBtn = h("button", { class: "btn primary", onClick: () => run(rvBtn, async () => {
    showResult(await api.post("/api/docs/revision", { grade_id: gradeOf().id, trimester: sel.tri, week: rvWhole.checked ? 0 : sel.week, title: rvTopic.value.trim(),
      words: rvWords.value, points: rvPoints.value, questions: rvQs.value, with_answers: rvAns.checked, with_cover: cvOn.checked, cover_rows: cvRows.value }));
  }) }, icon("file"), t("rv_create"));
  const panel = h("div", { class: "panel" }, h("h3", {}, t("rv_title")), h("p", { class: "muted small" }, t("rv_lead")), aiNeeded(), srcRv ? srcRv.el : null,
    h("div", { class: "ai-bar" }, rvTopic, h("label", { class: "row" }, t("ai_q_count"), rvCount), rvAi),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_words")), rvWords),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_points")), rvPoints),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_qs")), rvQs),
    h("label", { class: "row" }, cvOn, t("cv_include")), cvBox,
    h("div", { class: "row" }, srcRv ? rvFromSrc : null, h("label", { class: "row" }, rvWhole, t("rv_whole")), h("label", { class: "row" }, rvAns, t("d_with_answers")), h("span", { class: "grow" }), rvBtn));
  return { el: panel, topic: rvTopic };
}
