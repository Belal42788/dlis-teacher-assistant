import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { promptEditor } from "../components/prompt_editor.js";
import { sourcePicker } from "../components/source_pick.js";
import { roomLabel, gradeName, fmtShort, triName } from "../labels.js";

const memoDocs = { tab: "wk" };
const DAY_FIELDS = ["sunday", "monday", "tuesday", "wednesday", "thursday"];
const QUIZ_EXAMPLE = "1. What is the CPU?\na) The brain of the computer\nb) A screen\nc) A printer\nAnswer: a\n\n2. Which one is an input device?\na) Mouse\nb) Speaker\nAnswer: a";

export async function renderDocs(root) {
  const [structure, ov, tt] = await Promise.all([api.get("/api/structure"), api.get("/api/overview"), api.get("/api/timetable")]);
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  const rooms = structure.rooms;
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  if (!rooms.length || !tris.length) {
    root.replaceChildren(h("div", { class: "page" }, h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_docs")))),
      h("div", { class: "banner warn" }, icon("warn"), h("div", {}, rooms.length ? t("d_need_calendar") : t("d_need_rooms"), " ",
        h("a", { href: rooms.length ? "#/calendar" : "#/classes" }, rooms.length ? t("nav_calendar") : t("nav_classes"))))));
    return;
  }
  const used = new Set(Object.values(tt.grid).flatMap((row) => Object.values(row)).filter(Boolean));
  const pos = ov.position;
  const sel = {
    room: (rooms.find((r) => r.id === q.get("room")) || rooms.find((r) => r.grade_id === q.get("grade") && used.has(r.id))
      || rooms.find((r) => r.grade_id === q.get("grade")) || rooms.find((r) => used.has(r.id)) || rooms[0]).id,
    tri: q.has("tri") ? +q.get("tri") : pos.state === "in_term" ? pos.trimester : tris[0].index,
    week: q.has("week") ? +q.get("week") : pos.state === "in_term" ? pos.week : 1,
  };
  if (!tris.some((x) => x.index === sel.tri)) sel.tri = tris[0].index;
  const gradeOf = () => structure.grades.find((g) => g.id === rooms.find((r) => r.id === sel.room).grade_id);
  const triObj = () => tris.find((x) => x.index === sel.tri) || tris[0];

  const roomSel = h("select", { "aria-label": t("d_class"), onChange: (e) => { sel.room = e.target.value; refresh(); } },
    rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const triSel = h("select", { "aria-label": t("d_trimester"), onChange: (e) => { sel.tri = +e.target.value; sel.week = 1; drawWeeks(); refresh(); } },
    tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  const weekSel = h("select", { "aria-label": t("d_week"), onChange: (e) => { sel.week = +e.target.value; refresh(); } });
  const info = h("div", { class: "muted small", style: { marginTop: ".5rem" } });
  roomSel.value = sel.room; triSel.value = sel.tri;

  function drawWeeks() {
    weekSel.replaceChildren(triObj().weeks.map((w) => h("option", { value: w.number }, `${t("week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}${w.school_days === 0 ? " ✕" : ""}`)));
    if (!triObj().weeks.some((w) => w.number === sel.week)) sel.week = 1;
    weekSel.value = sel.week;
  }
  async function refresh() {
    const c = await guarded(() => api.get(`/api/docs/context?room=${sel.room}&tri=${sel.tri}&week=${sel.week}`));
    if (!c) return;
    const notes = Object.entries(c.day_notes).map(([d, n]) => `${t(`day_${d}`)}: ${n}`);
    info.replaceChildren(`${gradeName(gradeOf())} · ${c.range}`, notes.length ? h("div", {}, icon("info"), " ", notes.join(" · ")) : null);
    gsCount.textContent = t("students_n", { n: c.students });
    fillWeekTopics();
    // days this grade has no lesson: the Word file will say "No session"
    DAY_FIELDS.forEach((d) => { const off = !c.teach_days.includes(d[0].toUpperCase() + d.slice(1)); lp[d].placeholder = off ? t("d_no_session") : ""; lp[d].classList.toggle("no-session", off); });
  }

  // ---------- AI helper (fills the boxes; the teacher reviews, then creates the file)
  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  const aiNeeded = () => ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, h("a", { href: "#/settings" }, t("ai_setup_link"))));
  const aiButton = (label, run) => {
    const b = h("button", { class: "btn", disabled: !ai.ready, onClick: async () => {
      b.disabled = true; const old = b.lastChild.textContent; b.lastChild.textContent = t("ai_writing");
      try { const ok = await guarded(run); if (ok !== undefined) toast(t("ai_filled")); } finally { b.disabled = false; b.lastChild.textContent = old; }
    } }, icon("spark"), label);
    return b;
  };

  // ---------- "use my slides" (sources the teacher imported): the AI helpers then write from them
  const srcLp = await sourcePicker(async (id, s) => { if (id && s && s.topic && !topic.value.trim()) topic.value = s.topic; });
  const srcQz = await sourcePicker();
  const srcRv = await sourcePicker((id, s) => { if (id && s && s.topic && !rvTopic.value.trim()) rvTopic.value = s.topic; });
  const sid = (p) => (p ? p.value() : "");

  // ---------- results area
  const result = h("div", {});
  function showResult(r, extra) {
    result.replaceChildren(h("div", { class: "banner ok" }, icon("check"),
      h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel), extra || null),
      h("div", { class: "row" },
        h("button", { class: "btn small primary", onClick: () => open(r.path, false) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small", onClick: () => open(r.path, true) }, icon("folder"), t("d_open_folder")))));
    result.scrollIntoView({ block: "nearest" });
  }
  const open = (path, folder) => guarded(() => api.post("/api/open", { path, folder }));
  const run = async (btn, fn) => { btn.disabled = true; try { return await guarded(fn); } finally { btn.disabled = false; } };

  // ---------- lesson plan
  const lp = {};
  const field = (key, label, rows = 2, ph = "") => { lp[key] = h("textarea", { rows, placeholder: ph, style: { minHeight: "0" } }); return h("label", { class: "field" }, h("span", { class: "label" }, label), lp[key]); };
  const topic = h("input", { type: "text" }); lp.topic = topic;
  const lpBtn = h("button", { class: "btn primary", onClick: () => run(lpBtn, async () => {
    const content = Object.fromEntries(Object.entries(lp).map(([k, el]) => [k, el.value]));
    showResult(await api.post("/api/docs/lesson-plan", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, content }));
  }) }, icon("file"), t("d_create_lp"));
  const lpAi = aiButton(t("ai_write"), async () => {
    if (!topic.value.trim()) { toast(t("ai_need_topic"), "error"); return null; }
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

  // ---------- quiz
  const quizNo = h("input", { type: "number", min: 1, max: 20, value: 1, style: { width: "5em" } });
  const quizText = h("textarea", { rows: 9, placeholder: QUIZ_EXAMPLE, dir: "ltr", onInput: () => countQ() });
  const withAns = h("input", { type: "checkbox" });
  const found = h("span", { class: "muted small" });
  const countQ = () => { const n = (quizText.value.match(/^\s*(?:Q\s*)?\d+\s*[.)\-:]/gim) || []).length; found.textContent = n ? t("d_questions_found", { n }) : ""; };
  const quizBtn = h("button", { class: "btn primary", onClick: () => run(quizBtn, async () => {
    showResult(await api.post("/api/docs/quiz", { grade_id: gradeOf().id, trimester: sel.tri, week: sel.week, number: +quizNo.value || 1, text: quizText.value, with_answers: withAns.checked }));
  }) }, icon("file"), t("d_create_quiz"));
  const qTopic = h("input", { type: "text", placeholder: t("ai_topic_q"), style: { flex: "1", minWidth: "10em" } });
  const qCount = h("input", { type: "number", min: 1, max: 20, value: 5 });
  const qLevel = h("select", {}, ["easy", "medium", "hard"].map((l) => h("option", { value: l, selected: l === "medium" }, t(`ai_${l}`))));
  const quizAi = aiButton(t("ai_write"), async () => {
    if (!qTopic.value.trim()) { toast(t("ai_need_topic"), "error"); return null; }
    const r = await api.post("/api/ai/quiz", { grade_id: gradeOf().id, topic: qTopic.value.trim(), count: +qCount.value || 5, difficulty: qLevel.value, source_id: sid(srcQz) });
    quizText.value = r.text; countQ(); return true;
  });
  const quizPanel = h("div", { class: "panel" }, h("h3", {}, t("d_quiz_title")), h("p", { class: "muted small" }, t("d_quiz_lead")), aiNeeded(), srcQz ? srcQz.el : null,
    h("div", { class: "ai-bar" }, qTopic, h("label", { class: "row" }, t("ai_q_count"), qCount), qLevel, quizAi),
    h("label", { class: "row", style: { marginBottom: ".6rem" } }, h("b", {}, t("d_quiz_n")), quizNo),
    quizText, found,
    h("div", { class: "row", style: { marginTop: ".6rem" } },
      h("label", { class: "row" }, withAns, t("d_with_answers")), h("span", { class: "grow" }), quizBtn));

  // ---------- grading sheet
  const gsCount = h("span", { class: "muted" });
  const gsBtn = h("button", { class: "btn primary", onClick: () => run(gsBtn, async () => {
    showResult(await api.post("/api/docs/grading-sheet", { room_id: sel.room, trimester: sel.tri, week: sel.week, lang: getLang() }));
  }) }, icon("file"), t("d_create_gs"));
  const gsX = h("button", { class: "btn", onClick: () => run(gsX, async () => {
    showResult(await api.post("/api/docs/grading-sheet", { room_id: sel.room, trimester: sel.tri, week: sel.week, lang: getLang(), format: "xlsx" }));
  }) }, icon("file"), t("d_create_gs_xlsx"));
  const gsPanel = h("div", { class: "panel" }, h("h3", {}, t("d_gs_title")), h("p", { class: "muted small" }, t("d_gs_lead")),
    h("div", { class: "row" }, gsBtn, gsX, gsCount), h("p", { class: "muted small", style: { marginTop: ".6rem" } }, t("d_gs_lms")));

  // ---------- trimester plan
  const tpLessons = h("textarea", { rows: 6, placeholder: t("d_tp_ph") });
  const tpBtn = h("button", { class: "btn primary", onClick: () => run(tpBtn, async () => {
    showResult(await api.post("/api/docs/trimester-plan", { grade_id: gradeOf().id, trimester: sel.tri, lessons: tpLessons.value.split("\n") }));
  }) }, icon("file"), t("d_create_tp"));
  const tpTopics = h("input", { type: "text", placeholder: t("ai_tp_topics"), style: { flex: "1", minWidth: "10em" } });
  const tpAi = aiButton(t("ai_write"), async () => {
    const r = await api.post("/api/ai/trimester", { grade_id: gradeOf().id, trimester: sel.tri, textbooks: tpTopics.value.trim() });
    tpLessons.value = r.lessons.join("\n"); tpLessons.closest("details").open = true; return true;
  });
  const tpPanel = h("div", { class: "panel" }, h("h3", {}, t("d_tp_title")), h("p", { class: "muted small" }, t("d_tp_lead")), aiNeeded(),
    h("div", { class: "ai-bar" }, tpTopics, tpAi),
    h("details", { class: "more" }, h("summary", {}, t("d_tp_lessons")), tpLessons), h("div", { class: "row" }, tpBtn));

  // ---------- revision sheet
  const rvTopic = h("input", { type: "text", placeholder: t("rv_topic_ph") });
  const rvWhole = h("input", { type: "checkbox" });
  const rvCount = h("input", { type: "number", min: 3, max: 15, value: 6, style: { width: "5em" } });
  const rvWords = h("textarea", { rows: 4, placeholder: "CPU: the brain of the computer" });
  const rvPoints = h("textarea", { rows: 4, placeholder: "..." });
  const rvQs = h("textarea", { rows: 5, placeholder: "What does the CPU do? | It processes data" });
  const rvAns = h("input", { type: "checkbox", checked: true });
  const rvAi = aiButton(t("ai_write"), async () => {
    if (!rvTopic.value.trim()) { toast(t("ai_need_topic"), "error"); return null; }
    const r = await api.post("/api/ai/revision", { grade_id: gradeOf().id, topic: rvTopic.value.trim(), count: +rvCount.value || 6, source_id: sid(srcRv) });
    rvWords.value = r.words; rvPoints.value = r.points; rvQs.value = r.questions; return true;
  });
  const rvFromSrc = h("button", { class: "btn", onClick: () => run(rvFromSrc, async () => {
    const id = sid(srcRv); if (!id) { toast(t("src_pick_first"), "error"); return; }
    const d = (await api.get(`/api/sources/${id}`)).digest;
    if (!d || !d.topic) { toast(t("src_no_digest"), "error"); return; }
    if (!rvTopic.value.trim()) rvTopic.value = d.topic;
    rvWords.value = d.words.map((w) => `${w.term}: ${w.meaning}`).join("\n"); rvPoints.value = d.points.join("\n"); rvQs.value = d.questions.map((x) => `${x.q} | ${x.a}`).join("\n");
  }) }, icon("file"), t("src_fill_rv"));
  const rvBtn = h("button", { class: "btn primary", onClick: () => run(rvBtn, async () => {
    showResult(await api.post("/api/docs/revision", { grade_id: gradeOf().id, trimester: sel.tri, week: rvWhole.checked ? 0 : sel.week, title: rvTopic.value.trim(),
      words: rvWords.value, points: rvPoints.value, questions: rvQs.value, with_answers: rvAns.checked }));
  }) }, icon("file"), t("rv_create"));
  const rvPanel = h("div", { class: "panel" }, h("h3", {}, t("rv_title")), h("p", { class: "muted small" }, t("rv_lead")), aiNeeded(), srcRv ? srcRv.el : null,
    h("div", { class: "ai-bar" }, rvTopic, h("label", { class: "row" }, t("ai_q_count"), rvCount), rvAi),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_words")), rvWords),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_points")), rvPoints),
    h("label", { class: "field" }, h("span", { class: "label" }, t("rv_qs")), rvQs),
    h("div", { class: "row" }, srcRv ? rvFromSrc : null, h("label", { class: "row" }, rvWhole, t("rv_whole")), h("label", { class: "row" }, rvAns, t("d_with_answers")), h("span", { class: "grow" }), rvBtn));

  // ---------- prepare the whole week: lesson plan + quiz + revision + grading sheets, for every grade you teach
  const weekGrades = structure.grades.filter((g) => rooms.some((r) => r.grade_id === g.id && used.has(r.id)));
  const wk = weekGrades.map((g) => ({ g, topic: h("input", { type: "text", placeholder: t("wk_topic_ph"), onInput: (e) => { e.target.dataset.typed = "1"; } }),
    lp: h("input", { type: "checkbox", checked: true }), qz: h("input", { type: "checkbox", checked: true }), rv: h("input", { type: "checkbox", checked: true }), gs: h("input", { type: "checkbox", checked: true }) }));
  let docsDir = "", topicsKey = "";
  const keep = (r) => { if (r && r.folder) docsDir = r.folder; return r; };
  const wkOut = h("div", { class: "wk-out" });
  const srcWk = await sourcePicker();
  async function fillWeekTopics() {
    const key = `${sel.tri}|${sel.week}`; if (key === topicsKey) return; topicsKey = key;
    for (const row of wk) {
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
  const wkPanel = h("div", { class: "panel" }, h("h3", {}, t("wk_title")), h("p", { class: "muted small" }, t("wk_lead")), ai.ready ? null : aiNeeded(), srcWk ? srcWk.el : null,
    wk.length ? h("div", { class: "wk-grid" },
      h("div", { class: "wk-head" }, t("ch_class")), h("div", { class: "wk-head" }, t("d_topic")), h("div", { class: "wk-head" }, t("d_lp_title")), h("div", { class: "wk-head" }, t("d_quiz_title")), h("div", { class: "wk-head" }, t("rv_title")), h("div", { class: "wk-head" }, t("d_gs_title")),
      wk.flatMap((r) => [h("b", {}, gradeName(r.g)), r.topic, r.lp, r.qz, r.rv, r.gs])) : h("p", { class: "muted" }, t("wk_none")),
    h("div", { class: "row", style: { marginTop: ".8rem" } }, wkBtn), wkOut);

  const aiPromptPanel = await promptEditor();
  // one kind of file at a time: the page stays short and the teacher sees only what they chose
  const panelList = [["wk", wkPanel, "wk_tab"], ["lp", lpPanel, "d_lp_title"], ["quiz", quizPanel, "d_quiz_title"], ["rv", rvPanel, "rv_title"], ["gs", gsPanel, "d_gs_title"], ["tp", tpPanel, "d_tp_title"], ["ai", aiPromptPanel, "docs_ai_tab"]];
  const tabBtns = panelList.map(([id, , key]) => h("button", { class: "seg-btn", role: "tab", "data-tab": id, onClick: () => showTab(id) }, t(key)));
  const tabs = h("div", { class: "seg", role: "tablist" }, tabBtns);
  function showTab(id) {
    memoDocs.tab = id;
    panelList.forEach(([k, el]) => { el.hidden = k !== id; });
    tabBtns.forEach((b) => { b.setAttribute("aria-selected", String(b.dataset.tab === id)); });
  }
  showTab(panelList.some(([k]) => k === memoDocs.tab) ? memoDocs.tab : "wk");
  drawWeeks();
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_docs")), h("p", {}, t("docs_lead")))),
    h("div", { class: "panel sticky-pick" },
      h("div", { class: "pick-row" },
        h("label", {}, h("span", { class: "label" }, t("d_class")), roomSel),
        h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel),
        h("label", {}, h("span", { class: "label" }, t("d_week")), weekSel)), info),
    result, tabs, ...panelList.map(([, el]) => el)));
  await refresh();
}
