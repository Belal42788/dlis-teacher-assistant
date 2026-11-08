// Library > Question bank: every question you saved, by grade and topic.
import { hubTabs } from "../components/hubtabs.js";
import { h, icon, toast, confirmBox, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { gradeName } from "../labels.js";
import { emptyState } from "../components/empty.js";
import { LEVELS } from "../components/bank_pick.js";

const EXAMPLE = "1. What is the CPU?\na) The brain of the computer\nb) A screen\nAnswer: a\n\n2. The ___ stores files permanently.\nAnswer: hard disk";

export async function renderBank(root) {
  const { grades } = await api.get("/api/structure");
  const gradeSel = (value) => h("select", {}, grades.map((g) => h("option", { value: g.id, selected: g.id === value }, gradeName(g))));
  const levelSel = (value = "medium") => h("select", {}, LEVELS.map((l) => h("option", { value: l, selected: l === value }, t(`ai_${l}`))));
  const topicBox = (value = "") => h("input", { type: "text", value, placeholder: t("bk_topic"), maxlength: 80, list: "bk-topics" });
  const topics = h("datalist", { id: "bk-topics" });
  const listBox = h("div", {});
  const info = h("span", { class: "muted small" });

  // ---- filters
  const fGrade = h("select", {}, h("option", { value: "" }, t("bk_all_grades")), grades.map((g) => h("option", { value: g.id }, gradeName(g))));
  const fTopic = h("select", {}, h("option", { value: "" }, t("bk_all_topics")));
  const fLevel = h("select", {}, h("option", { value: "" }, t("bk_all_levels")), LEVELS.map((l) => h("option", { value: l }, t(`ai_${l}`))));
  const fSearch = h("input", { type: "search", placeholder: t("bk_search"), style: { flex: "1", minWidth: "10em" } });
  let timer;
  const query = () => `/api/bank?grade_id=${fGrade.value}&topic=${encodeURIComponent(fTopic.value)}&level=${fLevel.value}&search=${encodeURIComponent(fSearch.value)}`;

  async function load(keepTopic = true) {
    const r = await guarded(() => api.get(query()));
    if (!r) return;
    const cur = keepTopic ? fTopic.value : "";
    fTopic.replaceChildren(h("option", { value: "" }, t("bk_all_topics")), r.topics.map((x) => h("option", { value: x, selected: x === cur }, x)));
    topics.replaceChildren(r.topics.map((x) => h("option", { value: x })));
    info.textContent = r.total ? t("bk_count", { shown: r.found, total: r.total }) : "";
    listBox.replaceChildren(r.total ? (r.items.length ? r.items.map(card) : h("p", { class: "muted" }, t("bk_none_match"))) : emptyState({ icon: "list", title: t("bk_empty_title"), text: t("bk_empty") }));
  }

  function card(it) {
    const body = it.type === "match" ? h("ul", { class: "bk-opts" }, it.pairs.map(([a, b]) => h("li", {}, `${a} ⟷ ${b}`)))
      : it.options.length ? h("ul", { class: "bk-opts" }, it.options.map(([l, x]) => h("li", { class: String(it.answer).trim().toUpperCase().startsWith(l) ? "right" : "" }, `${l.toLowerCase()}) ${x}`)))
        : it.answer ? h("p", { class: "small" }, h("b", {}, `${t("bk_answer")}: `), it.answer) : null;
    return h("div", { class: "bk-card" },
      h("div", { class: "row" }, h("b", { class: "grow" }, it.q),
        h("button", { class: "btn icon ghost", "aria-label": t("edit"), onClick: () => edit(it) }, icon("edit")),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: async () => { if (await confirmBox(t("bk_delete_q"))) { await guarded(() => api.post(`/api/bank/${it.id}/delete`, {})); load(); } } }, icon("trash"))),
      body,
      h("div", { class: "row small muted" }, h("span", { class: "bk-tag" }, t(`qt_${it.type}`)), h("span", { class: "bk-tag" }, t(`ai_${it.level}`)), it.topic ? h("span", { class: "bk-tag" }, it.topic) : null,
        h("span", {}, grades.find((g) => g.id === it.grade_id) ? gradeName(grades.find((g) => g.id === it.grade_id)) : ""),
        it.used ? h("span", {}, t("bk_used_n", { n: it.used }), it.last_used ? ` · ${it.last_used}` : "") : h("span", {}, t("bk_never_used"))));
  }

  function edit(it) {
    const text = h("textarea", { rows: 7, dir: "ltr" }); text.value = it.text.replace(/^1\.\s*/, "1. ");
    const topic = topicBox(it.topic); const level = levelSel(it.level);
    modal({ title: t("edit"), wide: true, body: h("div", {}, text, h("div", { class: "row bk-bar", style: { marginTop: ".6rem" } }, topic, level)),
      actions: [{ label: t("save"), kind: "primary", onClick: async () => { const r = await guarded(() => api.put(`/api/bank/${it.id}`, { text: text.value, topic: topic.value, level: level.value })); if (r) { await load(); return true; } return false; } }] });
  }

  // ---- add
  const aGrade = gradeSel(grades[0]?.id); const aTopic = topicBox(); const aLevel = levelSel();
  const aText = h("textarea", { rows: 8, dir: "ltr", placeholder: EXAMPLE });
  const addBtn = h("button", { class: "btn primary", onClick: async () => {
    addBtn.disabled = true;
    try {
      const r = await guarded(() => api.post("/api/bank", { grade_id: aGrade.value, topic: aTopic.value, level: aLevel.value, text: aText.value }));
      if (r) { toast(t("bk_saved", { n: r.added, skipped: r.skipped })); aText.value = ""; await load(false); }
    } finally { addBtn.disabled = false; }
  } }, icon("plus"), t("bk_save"));

  const refresh = () => { clearTimeout(timer); timer = setTimeout(() => load(true), 200); };
  [fGrade, fLevel].forEach((el) => el.addEventListener("change", () => { fTopic.value = ""; load(false); }));
  fTopic.addEventListener("change", () => load(true)); fSearch.addEventListener("input", refresh);

  root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "bank"),
    h("div", { class: "page-head" }, h("h2", {}, t("bk_title")), h("p", { class: "muted" }, t("bk_lead"))),
    h("div", { class: "panel" }, h("h3", {}, t("bk_add")), h("p", { class: "muted small" }, t("bk_add_hint")),
      h("div", { class: "row bk-bar", style: { marginBottom: ".5rem" } }, aGrade, aTopic, aLevel, topics), aText, h("div", { class: "row", style: { marginTop: ".6rem" } }, h("span", { class: "grow" }), addBtn)),
    h("div", { class: "panel" }, h("div", { class: "row bk-bar", style: { marginBottom: ".7rem" } }, fGrade, fTopic, fLevel, fSearch), info, listBox)));
  await load(false);
}
