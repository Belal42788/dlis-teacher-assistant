import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { sourcePicker } from "./source_pick.js";
import { roomLabel, gradeName } from "../labels.js";

// "Prepare my whole week": lesson plan + quiz + revision + grading sheets for every grade the teacher teaches, in one press.
export async function weekPanel(ctx) {
  const { root, structure, rooms, used, sel, ai, aiNeeded } = ctx;
  const weekGrades = structure.grades.filter((g) => rooms.some((r) => r.grade_id === g.id && used.has(r.id)));
  const wk = weekGrades.map((g) => ({ g, topic: h("input", { type: "text", placeholder: t("wk_topic_ph"), "aria-label": `${gradeName(g)} · ${t("d_topic")}`, onInput: (e) => { e.target.dataset.typed = "1"; } }),
    lp: h("input", { type: "checkbox", checked: true, "aria-label": `${gradeName(g)} · ${t("d_lp_title")}` }), qz: h("input", { type: "checkbox", checked: true, "aria-label": `${gradeName(g)} · ${t("d_quiz_title")}` }),
    rv: h("input", { type: "checkbox", checked: true, "aria-label": `${gradeName(g)} · ${t("rv_title")}` }), gs: h("input", { type: "checkbox", checked: true, "aria-label": `${gradeName(g)} · ${t("d_gs_title")}` }) }));
  let docsDir = "", topicsKey = "";
  const keep = (r) => { if (r && r.folder) docsDir = r.folder; return r; };
  const wkOut = h("div", { class: "wk-out" });
  const srcWk = await sourcePicker();
  async function fillWeekTopics() {
    const key = `${sel.tri}|${sel.week}`; if (key === topicsKey) return; topicsKey = key;
    for (const row of wk) {
      if (!root.isConnected) return;   // the teacher already left this page
      const r = await guarded(() => api.get(`/api/slides/topics?grade=${row.g.id}&tri=${sel.tri}`));
      const w = r && r.weeks.find((x) => x.week === sel.week);
      if (!row.topic.value.trim() || !row.topic.dataset.typed) row.topic.value = w && w.topic ? w.topic : "";
    }
  }
  const wkBtn = h("button", { class: "btn primary", disabled: !wk.length, onClick: async () => {
    wkBtn.disabled = true; wkOut.replaceChildren();
    const line = (txt, state) => { const el = h("div", { class: `wk-line ${state}` }, txt); wkOut.append(el); return el; };
    const step = async (label, fn) => { const el = line(label + " …", "busy"); try { const r = await fn(); el.className = "wk-line ok"; el.textContent = "✓ " + label; return r; } catch (e) { if (e.code === "no_students") { el.className = "wk-line busy"; el.textContent = "– " + label + " — " + t("wk_no_students"); return null; } el.className = "wk-line err"; el.textContent = "✗ " + label + " — " + (e.friendly || e.message); return null; } };
    const base = { trimester: sel.tri, week: sel.week };
    const sid = srcWk ? srcWk.value() : "";
    let made = 0;
    for (const row of wk) {
      const g = row.g, topicText = row.topic.value.trim(), name = gradeName(g);
      if ((row.lp.checked || row.qz.checked || row.rv.checked) && !topicText) { line(`${name}: ${t("wk_need_topic")}`, "err"); }
      if (ai.ready && topicText) {
        if (row.lp.checked && await step(`${name} · ${t("d_lp_title")}`, async () => { const c = await api.post("/api/ai/lesson", { grade_id: g.id, ...base, topic: topicText, source_id: sid }); keep(await api.post("/api/docs/lesson-plan", { grade_id: g.id, ...base, content: c.content })); })) made++;
        if (row.qz.checked && await step(`${name} · ${t("d_quiz_title")}`, async () => { const q = await api.post("/api/ai/quiz", { grade_id: g.id, topic: topicText, count: 5, difficulty: "medium", source_id: sid }); keep(await api.post("/api/docs/quiz", { grade_id: g.id, ...base, number: 1, text: q.text, with_answers: true })); })) made++;
        if (row.rv.checked && await step(`${name} · ${t("rv_title")}`, async () => { const v = await api.post("/api/ai/revision", { grade_id: g.id, topic: topicText, count: 6, source_id: sid }); keep(await api.post("/api/docs/revision", { grade_id: g.id, ...base, title: topicText, words: v.words, points: v.points, questions: v.questions, with_answers: true })); })) made++;
      }
      if (row.gs.checked) for (const r of rooms.filter((x) => x.grade_id === g.id && used.has(x.id))) {
        if (!(r.student_count > 0)) { line(`– ${roomLabel(r, structure)} · ${t("d_gs_title")} — ${t("wk_no_students")}`, "busy"); continue; }
        if (await step(`${roomLabel(r, structure)} · ${t("d_gs_title")}`, async () => keep(await api.post("/api/docs/grading-sheet", { room_id: r.id, ...base, lang: getLang() })))) made++;
      }
    }
    wkOut.append(h("div", { class: "banner ok" }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("wk_done", { n: made }))),
      h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: docsDir, folder: true })) }, icon("folder"), t("d_open_folder"))));
    wkBtn.disabled = false;
  } }, icon("spark"), t("wk_go"));
  const panel = h("div", { class: "panel" }, h("h3", {}, t("wk_title")), h("p", { class: "muted small" }, t("wk_lead")), ai.ready ? null : aiNeeded(), srcWk ? srcWk.el : null,
    wk.length ? h("div", { class: "wk-grid" },
      h("div", { class: "wk-head" }, t("ch_class")), h("div", { class: "wk-head" }, t("d_topic")), h("div", { class: "wk-head" }, t("d_lp_title")), h("div", { class: "wk-head" }, t("d_quiz_title")), h("div", { class: "wk-head" }, t("rv_title")), h("div", { class: "wk-head" }, t("d_gs_title")),
      wk.flatMap((r) => [h("b", {}, gradeName(r.g)), r.topic, r.lp, r.qz, r.rv, r.gs])) : h("p", { class: "muted" }, t("wk_none")),
    h("div", { class: "row", style: { marginTop: ".8rem" } }, wkBtn), wkOut);
  return { el: panel, fillTopics: fillWeekTopics };
}
