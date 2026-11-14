import { showProblems } from "./validate.js";
import { h, icon, toast } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { sourcePicker } from "./source_pick.js";
import { saveToBank, pickFromBank } from "./bank_pick.js";

const QUIZ_EXAMPLE = "1. What is the CPU?\na) The brain of the computer\nb) A screen\nc) A printer\nAnswer: a\n\n2. Which one is an input device?\na) Mouse\nb) Speaker\nAnswer: a";

// The quiz box of the "Create files" page: write or paste questions, pick from the bank, make the file or an LMS import.
export async function quizPanel(ctx) {
  const { sel, gradeOf, aiNeeded, aiButton, sid, run, open, showResult } = ctx;
  const srcQz = await sourcePicker(null, { exact: true });
  const quizNo = h("input", { type: "number", min: 1, max: 20, value: 1, style: { width: "5em" } });
  const quizText = h("textarea", { rows: 9, placeholder: QUIZ_EXAMPLE, dir: "ltr", required: true, "data-label": t("d_quiz_title"), onInput: () => countQ() });
  const withAns = h("input", { type: "checkbox" });
  const twoVer = h("input", { type: "checkbox" });
  const found = h("span", { class: "muted small" });
  let bankIds = [];   // saved questions that went into this quiz (so the bank can remember where they were used)
  const countQ = () => { const n = (quizText.value.match(/^\s*(?:Q\s*)?\d+\s*[.)\-:]/gim) || []).length; found.textContent = n ? t("d_questions_found", { n }) : ""; };
  const quizBtn = h("button", { class: "btn primary", onClick: () => run(quizBtn, async () => {
    await api.post("/api/docs/quiz", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, number: +quizNo.value || 1, text: quizText.value, with_answers: withAns.checked, versions: twoVer.checked ? 2 : 1, bank_ids: bankIds }).then((r) => { showResult(r, r.b ? h("div", {}, h("button", { class: "btn small", onClick: () => open(r.b.path, false) }, icon("file"), t("d_open_b"))) : null); });
  }) }, icon("file"), t("d_create_quiz"));
  const exportBtn = (fmt, label) => { const b = h("button", { class: "btn", "data-check": "", onClick: () => run(b, async () => {
    const r = await api.post("/api/docs/quiz-export", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, number: +quizNo.value || 1, text: quizText.value, format: fmt, bank_ids: bankIds });
    showResult(r, h("p", { class: "muted small" }, t(fmt === "forms" ? "qx_forms_how" : "qx_moodle_how")));
  }) }, icon("download"), label); return b; };
  const qTopic = h("input", { type: "text", placeholder: t("ai_topic_q"), style: { flex: "1", minWidth: "10em" } });
  const secBox = h("div", { class: "qsec-list" });
  const secs = [{ type: "mcq", count: 5, options: 4, topic: "" }];
  const drawSecs = () => secBox.replaceChildren(...secs.map((sc, i) => {
    const type = h("select", { onChange: (e) => { sc.type = e.target.value; drawSecs(); } }, ["mcq", "tf", "match", "essay", "fill"].map((k) => h("option", { value: k, selected: k === sc.type }, t(`qt_${k}`))));
    const cnt = h("input", { type: "number", min: 1, max: 20, value: sc.count, "aria-label": t("ai_q_count"), style: { width: "4.5em" }, onInput: (e) => { sc.count = +e.target.value || 1; } });
    const opts = sc.type === "mcq" ? h("label", { class: "row small" }, t("qt_choices"), h("input", { type: "number", min: 2, max: 6, value: sc.options, style: { width: "4em" }, onInput: (e) => { sc.options = +e.target.value || 4; } })) : null;
    const topic = h("input", { type: "text", value: sc.topic, placeholder: t("qt_topic_ph"), style: { flex: "1", minWidth: "9em" }, onInput: (e) => { sc.topic = e.target.value; } });
    return h("div", { class: "qsec" }, type, h("label", { class: "row small" }, t("ai_q_count"), cnt), opts, topic,
      secs.length > 1 ? h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { secs.splice(i, 1); drawSecs(); } }, icon("trash")) : null);
  }));
  drawSecs();
  const addSec = h("button", { class: "btn small", onClick: () => { secs.push({ type: "mcq", count: 3, options: 4, topic: "" }); drawSecs(); } }, icon("plus"), t("qt_add"));
  const qLevel = h("select", {}, ["easy", "medium", "hard"].map((l) => h("option", { value: l, selected: l === "medium" }, t(`ai_${l}`))));
  const quizAi = aiButton(t("ai_write"), async () => {
    if (!sid(srcQz) && !qTopic.value.trim() && secs.some((x) => !x.topic.trim())) { showProblems(panel, [{ el: qTopic, label: t("ai_topic_q"), reason: t("v_required") }]); return null; }
    const r = await api.post("/api/ai/quiz", { grade_id: gradeOf().id, topic: qTopic.value.trim(), sections: secs, difficulty: qLevel.value, source_id: sid(srcQz), ...(srcQz ? srcQz.extra() : {}) });
    quizText.value = r.text; countQ(); return true;
  });
  const bankPick = h("button", { class: "btn small", onClick: () => pickFromBank({ gradeId: gradeOf().id, start: (quizText.value.match(/^\s*(?:Q\s*)?\d+\s*[.)\-:]/gim) || []).length, onPick: (r) => {
    quizText.value = `${quizText.value.trim()}${quizText.value.trim() ? "\n\n" : ""}${r.text}`; bankIds = [...new Set([...bankIds, ...r.ids])]; countQ();
  } }) }, icon("list"), t("bk_pick"));
  const bankSave = h("button", { class: "btn small", "data-check": "", onClick: () => saveToBank({ gradeId: gradeOf().id, topic: qTopic.value.trim(), level: qLevel.value, text: quizText.value }) }, icon("plus"), t("bk_save_these"));
  const panel = h("div", { class: "panel" }, h("h3", {}, t("d_quiz_title")), h("p", { class: "muted small" }, t("d_quiz_lead")), aiNeeded(), srcQz ? srcQz.el : null,
    h("div", { class: "ai-bar" }, qTopic, qLevel),
    secBox, h("div", { class: "row", style: { margin: ".4rem 0" } }, addSec, h("span", { class: "grow" }), quizAi),
    h("div", { "data-form": "" },   // the questions and the buttons that use them are checked together
      h("label", { class: "row", style: { marginBottom: ".6rem" } }, h("b", {}, t("d_quiz_n")), quizNo),
      h("div", { class: "row", style: { marginBottom: ".4rem" } }, bankPick, bankSave),
      quizText, found,
      h("div", { class: "row", style: { marginTop: ".6rem" } },
        h("label", { class: "row" }, withAns, t("d_with_answers")), h("label", { class: "row" }, twoVer, t("d_two_versions")), h("span", { class: "grow" }), quizBtn),
      h("div", { class: "row", style: { marginTop: ".5rem" } }, h("span", { class: "muted small" }, t("qx_title")), exportBtn("gift", t("qx_moodle")), exportBtn("forms", t("qx_forms")))));
  return { el: panel, topic: qTopic };
}
