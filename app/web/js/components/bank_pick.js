// Question bank helpers used by the quiz box in Create: save what is typed, or pick saved questions for a new quiz.
import { h, icon, toast, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

export const LEVELS = ["easy", "medium", "hard"];

export async function saveToBank({ gradeId, topic, level, text }) {
  const r = await guarded(() => api.post("/api/bank", { grade_id: gradeId, topic, level, text }));
  if (r) toast(t("bk_saved", { n: r.added, skipped: r.skipped }));
  return r;
}

// start: how many questions the quiz already has, so the new ones are numbered after them.
export async function pickFromBank({ gradeId, start, onPick }) {
  const filters = await guarded(() => api.get(`/api/bank?grade_id=${encodeURIComponent(gradeId)}`));
  if (!filters) return;
  if (!filters.total) { toast(t("bk_none_for_grade"), "error"); return; }
  const topic = h("select", {}, h("option", { value: "" }, t("bk_all_topics")), filters.topics.map((x) => h("option", { value: x }, x)));
  const level = h("select", {}, h("option", { value: "" }, t("bk_all_levels")), LEVELS.map((l) => h("option", { value: l }, t(`ai_${l}`))));
  const count = h("input", { type: "number", min: 1, max: 50, value: 5, style: { width: "5em" } });
  const list = h("div", { class: "bk-pick" });
  const ticked = new Set();
  const query = () => `/api/bank?grade_id=${encodeURIComponent(gradeId)}&topic=${encodeURIComponent(topic.value)}&level=${level.value}`;
  const draw = async () => {
    const r = await guarded(() => api.get(query()));
    if (!r) return;
    list.replaceChildren(r.items.length ? r.items.map((it) => h("label", { class: "bk-row" },
      h("input", { type: "checkbox", checked: ticked.has(it.id), onChange: (e) => { e.target.checked ? ticked.add(it.id) : ticked.delete(it.id); } }),
      h("span", { class: "grow" }, it.q || it.text), h("span", { class: "bk-tag" }, t(`qt_${it.type}`)), it.used ? h("span", { class: "muted small" }, t("bk_used_n", { n: it.used })) : null))
      : h("p", { class: "muted" }, t("bk_none_match")));
  };
  topic.addEventListener("change", draw); level.addEventListener("change", draw);
  const finish = async (body, close) => {
    const r = await guarded(() => api.post("/api/bank/pick", { grade_id: gradeId, topic: topic.value, level: level.value, start, ...body }));
    if (r) { onPick(r); close(); }
    return false;
  };
  const m = modal({ title: t("bk_pick_title"), wide: true,
    body: h("div", {}, h("p", { class: "muted small" }, t("bk_pick_hint")),
      h("div", { class: "row bk-bar", style: { marginBottom: ".6rem" } }, topic, level,
        h("label", { class: "row small" }, t("bk_how_many"), count),
        h("button", { class: "btn small primary", onClick: () => finish({ count: +count.value || 5 }, m.close) }, icon("spark"), t("bk_random"))), list),
    actions: [{ label: t("bk_add_ticked"), kind: "primary", onClick: async (_e, close) => (ticked.size ? finish({ ids: [...ticked] }, close) : (toast(t("bk_tick_first"), "error"), false)), close: false }] });
  draw();
}
