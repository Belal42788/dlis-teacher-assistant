// Library > Question bank: topic cards (how much of each topic you have and how much was used), grade tabs, an "add questions" menu
// (paste, write, or ask the AI) and the exam builder: tick questions from any topic or any old quiz, arrange them, make one exam file.
import { hubTabs } from "../components/hubtabs.js";
import { h, icon, toast, confirmBox, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { gradeName, triName, fmtShort } from "../labels.js";
import { emptyState } from "../components/empty.js";
import { menuItem } from "../components/lesson_menu.js";
import { LEVELS } from "../components/bank_pick.js";

const EXAMPLE = "1. What is the CPU?\na) The brain of the computer\nb) A screen\nAnswer: a\n\n2. The ___ stores files permanently.\nAnswer: hard disk";
const NONE = "__none__";   // the topic filter for questions saved without a topic

export async function renderBank(root) {
  const [{ grades }, ov, ai] = await Promise.all([api.get("/api/structure"), api.get("/api/overview"), api.get("/api/ai")]);
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  const gname = (id) => { const g = grades.find((x) => x.id === id); return g ? gradeName(g) : ""; };
  let grade = "", topic = null, level = "", quiz = "", search = "";   // topic: null = every topic, "" = the ones saved without a topic
  let info = { cards: [], total: 0, used: 0, quizzes: [] };
  let basket = (await guarded(() => api.get("/api/bank/basket"))) || { ids: [], items: [], grade_id: "" };

  const gradeSel = (value) => h("select", { required: true, "data-label": t("chat_grade") }, grades.map((g) => h("option", { value: g.id, selected: g.id === value }, gradeName(g))));
  const levelSel = (value = "medium") => h("select", { "aria-label": t("bk_level") }, LEVELS.map((l) => h("option", { value: l, selected: l === value }, t(`ai_${l}`))));
  const topicList = h("datalist", { id: "bk-topics" });
  const topicBox = (value = "") => h("input", { type: "text", value, placeholder: t("bk_topic"), "aria-label": t("bk_topic"), maxlength: 80, list: "bk-topics" });

  const tabs = h("div", { class: "row bk-tabs", role: "tablist" });
  const cards = h("div", { class: "bk-topics" });
  const listBox = h("div", {});
  const count = h("span", { class: "muted small" });
  const basketBar = h("div", { class: "bk-basket", hidden: true });
  const fLevel = h("select", { "aria-label": t("bk_level") }, h("option", { value: "" }, t("bk_all_levels")), LEVELS.map((l) => h("option", { value: l }, t(`ai_${l}`))));
  const fQuiz = h("select", { "aria-label": t("bk_from_quiz") });
  const fSearch = h("input", { type: "search", placeholder: t("bk_search"), "aria-label": t("bk_search"), style: { flex: "1", minWidth: "10em" } });

  // ---------- the pieces of the page
  function drawTabs() {
    tabs.replaceChildren(...[["", t("bk_all_grades")], ...grades.map((g) => [g.id, gradeName(g)])].map(([id, label]) =>
      h("button", { type: "button", role: "tab", class: `chip${grade === id ? " on" : ""}`, "aria-selected": String(grade === id), onClick: () => { grade = id; topic = null; quiz = ""; refresh(); } }, label)));
  }
  const levelBar = (lv, total) => h("div", { class: "bk-lv", role: "img", "aria-label": LEVELS.map((l) => `${t(`ai_${l}`)} ${lv[l]}`).join(" · ") },
    LEVELS.map((l) => (lv[l] ? h("span", { class: `lv-${l}`, style: { flex: String(lv[l]) } }) : null)), total ? null : h("span", { class: "lv-none" }));
  const coverBar = (used, total) => h("div", { class: "bk-cover", role: "img", "aria-label": t("bk_cover", { used, total }) }, h("span", { style: { width: `${total ? Math.round((used / total) * 100) : 0}%` } }));
  function topicCard(c, label, on, pick) {
    return h("button", { type: "button", class: `bk-topic${on ? " on" : ""}`, "aria-pressed": String(on), onClick: pick },
      h("b", {}, label), h("span", { class: "small muted" }, t("bk_n_questions", { n: c.total })),
      levelBar(c.levels, c.total), coverBar(c.used, c.total), h("span", { class: "small muted" }, t("bk_cover", { used: c.used, total: c.total })));
  }
  function drawCards() {
    topicList.replaceChildren(info.cards.filter((c) => c.topic).map((c) => h("option", { value: c.topic })));
    const all = info.cards.reduce((a, c) => { LEVELS.forEach((l) => { a.levels[l] += c.levels[l]; }); return a; }, { total: info.total, used: info.used, levels: { easy: 0, medium: 0, hard: 0 } });
    cards.replaceChildren(
      topicCard(all, t("bk_all_topics"), topic === null, () => { topic = null; refreshList(); drawCards(); }),
      ...info.cards.map((c) => topicCard(c, c.topic || t("bk_no_topic"), topic === c.topic, () => { topic = c.topic; refreshList(); drawCards(); })));
    fQuiz.replaceChildren(h("option", { value: "" }, t("bk_any_quiz")), info.quizzes.map((x) => h("option", { value: x.quiz, selected: x.quiz === quiz }, `${x.quiz} (${x.count})`)));
  }
  const query = () => `/api/bank?grade_id=${grade}&topic=${topic === null ? "" : topic === "" ? NONE : encodeURIComponent(topic)}&level=${fLevel.value}&search=${encodeURIComponent(fSearch.value)}&quiz=${encodeURIComponent(fQuiz.value)}`;

  async function refreshTopics() {
    const r = await guarded(() => api.get(`/api/bank/topics?grade_id=${grade}`));
    if (!r) return;
    info = r;
    if (topic !== null && !info.cards.some((c) => c.topic === topic)) topic = null;
    drawCards();
  }
  async function refreshList() {
    const r = await guarded(() => api.get(query()));
    if (!r) return;
    count.textContent = r.total ? t("bk_count", { shown: r.found, total: r.total }) : "";
    listBox.replaceChildren(r.total ? (r.items.length ? r.items.map(card) : h("p", { class: "muted" }, t("bk_none_match")))
      : emptyState({ icon: "list", title: t("bk_empty_title"), text: t("bk_empty") }));
  }
  async function refresh() { drawTabs(); await refreshTopics(); await refreshList(); }

  // ---------- one question
  function card(it) {
    const inExam = basket.ids.includes(it.id);
    const body = it.type === "match" ? h("ul", { class: "bk-opts" }, it.pairs.map(([a, b]) => h("li", {}, `${a} ⟷ ${b}`)))
      : it.options.length ? h("ul", { class: "bk-opts" }, it.options.map(([l, x]) => h("li", { class: String(it.answer).trim().toUpperCase().startsWith(l) ? "right" : "" }, `${l.toLowerCase()}) ${x}`)))
        : it.answer ? h("p", { class: "small" }, h("b", {}, `${t("bk_answer")}: `), it.answer) : null;
    return h("div", { class: `bk-card${inExam ? " in-exam" : ""}` },
      h("div", { class: "row" }, h("b", { class: "grow" }, it.q),
        h("button", { class: `chip small${inExam ? " on" : ""}`, type: "button", "aria-pressed": String(inExam), onClick: () => toggle(it) }, icon(inExam ? "check" : "plus"), inExam ? t("bk_in_exam") : t("bk_to_exam")),
        h("button", { class: "btn icon ghost", "aria-label": t("edit"), onClick: () => edit(it) }, icon("edit")),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: async () => { if (await confirmBox(t("bk_delete_q"))) { await guarded(() => api.post(`/api/bank/${it.id}/delete`, {})); await reloadBasket(); refresh(); } } }, icon("trash"))),
      body,
      h("div", { class: "row small muted" }, h("span", { class: "bk-tag" }, t(`qt_${it.type}`)), h("span", { class: "bk-tag" }, t(`ai_${it.level}`)), it.topic ? h("span", { class: "bk-tag" }, it.topic) : null,
        h("span", {}, gname(it.grade_id)),
        it.used ? h("span", {}, t("bk_used_n", { n: it.used }), it.last_used ? ` · ${it.last_used}` : "") : h("span", {}, t("bk_never_used"))));
  }

  function edit(it) {
    const text = h("textarea", { rows: 7, dir: "ltr", required: true, "data-label": t("bk_add") }); text.value = it.text.replace(/^1\.\s*/, "1. ");
    const tp = topicBox(it.topic); const lv = levelSel(it.level);
    modal({ title: t("edit"), wide: true, body: h("div", {}, text, h("div", { class: "row bk-bar", style: { marginTop: ".6rem" } }, tp, lv)),
      actions: [{ label: t("save"), kind: "primary", onClick: async () => { const r = await guarded(() => api.put(`/api/bank/${it.id}`, { text: text.value, topic: tp.value, level: lv.value })); if (r) { await reloadBasket(); await refresh(); return true; } return false; } }] });
  }

  // ---------- add questions: paste / write, or ask the AI
  const afterAdd = async (r) => { toast(t("bk_saved", { n: r.added, skipped: r.skipped })); await refresh(); };
  function addPaste() {
    const g = gradeSel(grade || grades[0]?.id), tp = topicBox(topic || ""), lv = levelSel();
    const text = h("textarea", { rows: 9, dir: "ltr", placeholder: EXAMPLE, required: true, "data-label": t("bk_add") });
    modal({ title: t("bk_paste_title"), wide: true, body: h("div", {}, h("p", { class: "muted small" }, t("bk_add_hint")), h("div", { class: "row bk-bar", style: { marginBottom: ".5rem" } }, g, tp, lv), text),
      actions: [{ label: t("cancel") }, { label: t("bk_save"), kind: "primary", onClick: async () => {
        const r = await guarded(() => api.post("/api/bank", { grade_id: g.value, topic: tp.value, level: lv.value, text: text.value }));
        if (!r) return false; await afterAdd(r); return true; } }] });
  }
  function addAi() {
    const g = gradeSel(grade || grades[0]?.id), tp = h("input", { type: "text", required: true, "data-label": t("bk_topic"), placeholder: t("ai_topic_q"), maxlength: 120, value: topic || "", style: { flex: "1 1 14em" } });
    const kind = h("select", { "aria-label": t("bk_ai_type") }, ["mcq", "tf", "match", "essay", "fill"].map((k) => h("option", { value: k }, t(`qt_${k}`))));
    const n = h("input", { type: "number", min: 1, max: 20, value: 5, required: true, "data-label": t("bk_ai_count"), style: { width: "5em" } });
    const lv = levelSel();
    const out = h("textarea", { rows: 9, dir: "ltr", required: true, "data-label": t("bk_ai_result") });
    const go = h("button", { class: "btn primary", disabled: !ai.ready, onClick: async () => {
      go.disabled = true;
      try {
        const r = await guarded(() => api.post("/api/ai/quiz", { grade_id: g.value, topic: tp.value.trim(), difficulty: lv.value, sections: [{ type: kind.value, count: +n.value, options: 4, topic: tp.value.trim() }] }));
        if (r) out.value = r.text;
      } finally { go.disabled = !ai.ready; }
    } }, icon("spark"), t("bk_ai_go"));
    modal({ title: t("bk_ai_title"), wide: true, body: h("div", {},
      ai.ready ? h("p", { class: "muted small" }, t("bk_ai_lead")) : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, h("a", { href: "#/settings" }, t("ai_setup_link")))),
      h("div", { "data-form": "" }, h("div", { class: "row bk-bar", style: { marginBottom: ".5rem" } }, g, tp, kind, h("label", { class: "row small" }, t("bk_ai_count"), n), lv), h("div", { class: "row", style: { marginBottom: ".6rem" } }, go)),
      h("p", { class: "muted small" }, t("bk_ai_review")), out),
    actions: [{ label: t("cancel") }, { label: t("bk_save"), kind: "primary", onClick: async () => {
      const r = await guarded(() => api.post("/api/bank", { grade_id: g.value, topic: tp.value, level: lv.value, text: out.value }));
      if (!r) return false; await afterAdd(r); return true; } }] });
  }
  const addMenu = h("details", { class: "lesson-more bk-addmenu" },
    h("summary", { class: "btn primary" }, icon("plus"), t("bk_add_menu")),
    h("div", { class: "menu" }, menuItem(t("bk_add_paste"), addPaste, { icon: "edit" }), menuItem(t("bk_add_ai"), addAi, { icon: "spark" })));

  // ---------- the exam basket
  async function reloadBasket() { const r = await guarded(() => api.get("/api/bank/basket")); if (r) { basket = r; drawBasket(); } }
  async function setBasket(ids) {
    const r = await guarded(() => api.put("/api/bank/basket", { ids }));
    if (r) { basket = r; drawBasket(); refreshList(); }
    return r;
  }
  async function toggle(it) {
    if (basket.ids.includes(it.id)) { await setBasket(basket.ids.filter((i) => i !== it.id)); return; }
    if (basket.ids.length && basket.grade_id && basket.grade_id !== it.grade_id) {
      if (!(await confirmBox(t("bk_basket_other_grade"), { danger: false, okLabel: t("bk_start_new") }))) return;
      await setBasket([it.id]); return;
    }
    await setBasket([...basket.ids, it.id]);
  }
  function drawBasket() {
    basketBar.hidden = !basket.ids.length;
    basketBar.replaceChildren(icon("list"), h("b", { class: "grow" }, t("bk_basket_n", { n: basket.ids.length }), basket.grade_id ? ` · ${gname(basket.grade_id)}` : ""),
      h("button", { class: "btn ghost small", onClick: async () => { if (await confirmBox(t("bk_basket_clear_q"), { danger: false, okLabel: t("bk_basket_clear") })) setBasket([]); } }, t("bk_basket_clear")),
      h("button", { class: "btn primary", onClick: openExam }, icon("file"), t("bk_basket_open")));
  }

  function openExam() {
    if (!tris.length) { toast(t("d_need_calendar"), "error"); return; }
    let order = [...basket.ids];
    const itemOf = (id) => basket.items.find((x) => x.id === id);
    const list = h("div", { class: "bk-pick" });
    const triSel = h("select", { "aria-label": t("d_trimester") }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
    const weekSel = h("select", { "aria-label": t("d_week") });
    const pos = ov.position;
    triSel.value = pos.state === "in_term" && tris.some((x) => x.index === pos.trimester) ? pos.trimester : tris[0].index;
    const fillWeeks = () => { const tr = tris.find((x) => x.index === +triSel.value) || tris[0]; weekSel.replaceChildren(tr.weeks.map((w) => h("option", { value: w.number }, `${t("week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}`))); };
    fillWeeks(); triSel.addEventListener("change", fillWeeks);
    if (pos.state === "in_term" && pos.week && [...weekSel.options].some((o) => +o.value === pos.week)) weekSel.value = pos.week;
    const no = h("input", { type: "number", min: 1, max: 99, value: 1, required: true, "data-label": t("d_quiz_n"), style: { width: "5em" } });
    const withAns = h("input", { type: "checkbox" }), two = h("input", { type: "checkbox" });
    const done = h("div", {});
    const draw = () => {
      list.replaceChildren(...(order.length ? order.map((id, i) => {
        const it = itemOf(id);
        return h("div", { class: "bk-row" }, h("b", { class: "bk-n" }, String(i + 1)), h("span", { class: "grow" }, it ? it.q : id),
          it ? h("span", { class: "bk-tag" }, t(`qt_${it.type}`)) : null, it && it.topic ? h("span", { class: "bk-tag" }, it.topic) : null,
          h("button", { class: "btn icon ghost", "aria-label": t("bk_move_up"), disabled: i === 0, onClick: () => move(i, -1) }, icon("up")),
          h("button", { class: "btn icon ghost", "aria-label": t("bk_move_down"), disabled: i === order.length - 1, onClick: () => move(i, 1) }, icon("down")),
          h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { order.splice(i, 1); sync(); } }, icon("trash")));
      }) : [h("p", { class: "muted" }, t("bk_exam_empty"))]));
    };
    const sync = async () => { const r = await setBasket(order); if (r) order = [...r.ids]; draw(); };
    const move = (i, d) => { [order[i], order[i + d]] = [order[i + d], order[i]]; sync(); };
    draw();
    const m = modal({ title: t("bk_exam_title"), wide: true,
      body: h("div", {}, h("p", { class: "muted small" }, t("bk_exam_lead")), list,
        h("div", { class: "row bk-bar", style: { margin: ".7rem 0" } }, triSel, weekSel, h("label", { class: "row small" }, t("d_quiz_n"), no)),
        h("div", { class: "row" }, h("label", { class: "row small" }, withAns, t("d_with_answers")), h("label", { class: "row small" }, two, t("d_two_versions"))), done),
      actions: [{ label: t("close") }, { label: t("bk_exam_make"), kind: "primary", onClick: async () => {
        if (!order.length) { toast(t("bk_exam_empty"), "error"); return false; }
        const r = await guarded(() => api.post("/api/bank/exam", { ids: order, trimester: +triSel.value, week: +weekSel.value, number: +no.value || 1, with_answers: withAns.checked, versions: two.checked ? 2 : 1, clear: true }));
        if (!r) return false;
        const open = (p, folder) => guarded(() => api.post("/api/open", { path: p, folder }));
        done.replaceChildren(h("div", { class: "banner ok", style: { marginTop: ".7rem" } }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("bk_exam_made")), h("div", { class: "dir-ltr small" }, r.rel)),
          h("div", { class: "row" }, h("button", { class: "btn small primary", "data-nocheck": "", onClick: () => open(r.path, false) }, icon("file"), t("d_open_file")),
            h("button", { class: "btn small", onClick: () => open(r.path, true) }, icon("folder"), t("d_open_folder")))));
        order = []; draw(); await reloadBasket(); refresh();
        return false;
      } }] });
    return m;
  }

  // ---------- go
  const refreshSoon = (() => { let timer; return () => { clearTimeout(timer); timer = setTimeout(refreshList, 200); }; })();
  fLevel.addEventListener("change", refreshList); fQuiz.addEventListener("change", () => { quiz = fQuiz.value; refreshList(); }); fSearch.addEventListener("input", refreshSoon);
  root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "bank"),
    h("div", { class: "page-head row" }, h("div", { class: "grow" }, h("h2", {}, t("bk_title")), h("p", { class: "muted" }, t("bk_lead"))), addMenu),
    topicList, tabs,
    h("div", { class: "panel" }, h("h3", {}, t("bk_topics_title")), h("p", { class: "muted small" }, t("bk_topics_hint")), cards,
      h("div", { class: "row small muted bk-legend" }, LEVELS.map((l) => h("span", {}, h("i", { class: `lv-dot lv-${l}` }), t(`ai_${l}`))), h("span", {}, h("i", { class: "cv-dot" }), t("bk_cover_legend")))),
    h("div", { class: "panel" }, h("div", { class: "row bk-bar", style: { marginBottom: ".7rem" } }, fLevel, fQuiz, fSearch), count, listBox),
    basketBar));
  drawBasket();
  await refresh();
}
