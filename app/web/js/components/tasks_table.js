import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { fmtShort, triName } from "../labels.js";

const RANK = { high: 0, medium: 1, low: 2 };

export function sortedOpen(data) {
  const open = [...data.auto, ...data.tasks.filter((x) => !x.done)];
  const key = (x) => [x.deadline && x.deadline < data.today ? 0 : 1, RANK[x.importance] ?? 1, x.deadline || "9999"];
  return open.sort((a, b) => { const ka = key(a), kb = key(b); return ka[0] - kb[0] || ka[1] - kb[1] || String(ka[2]).localeCompare(String(kb[2])); });
}

// One tidy table, used by the Tasks page and the Today page.
// opts: { limit, showDone, onChange(newData) }
export function tasksTable(data, opts = {}) {
  const act = async (fn) => { const r = await guarded(fn); if (r) opts.onChange && opts.onChange(r); };
  const when = (x) => {
    if (x.done || !x.deadline) return h("span", { class: "muted small" }, x.done ? "" : t("t_no_deadline"));
    const diff = Math.round((new Date(x.deadline + "T00:00:00Z") - new Date(data.today + "T00:00:00Z")) / 86400000);
    const txt = diff < 0 ? t("t_days_late", { n: -diff }) : diff === 0 ? t("t_today") : diff === 1 ? t("t_tomorrow") : fmtShort(x.deadline);
    return h("span", { class: `due ${diff < 0 ? "late" : diff <= 1 ? "soon" : ""}` }, icon("clock"), txt);
  };
  const badge = (k) => h("span", { class: `imp ${k}` }, t(`imp_${k}`));

  const row = (x) => {
    const late = !x.done && x.deadline && x.deadline < data.today;
    if (x.auto) {
      return h("tr", { class: `auto${late ? " late-row" : ""}` },
        h("td", { class: "c-chk" }, h("span", { class: "auto-ic" }, icon("file"))),
        h("td", {}, h("b", {}, t("t_auto_lp", { grade: x.grade, tri: triName(`T${x.trimester + 1}`), n: x.week })), h("div", { class: "small muted" }, `${t("t_auto_hint")} · ${t("t_skip_hint")}: «${t("t_skip")}»`)),
        h("td", {}, badge(x.importance)), h("td", {}, when(x)),
        h("td", { class: "c-act" }, h("div", { class: "c-act-in" },
          h("a", { class: "btn small primary", href: `#/docs?grade=${x.grade_id}&tri=${x.trimester}&week=${x.week}` }, t("t_write")),
          h("button", { class: "btn small ghost", onClick: () => act(() => api.post("/api/tasks/dismiss", { id: x.id })) }, t("t_skip")))));
    }
    return h("tr", { class: `${x.done ? "done" : ""}${late ? " late-row" : ""}` },
      h("td", { class: "c-chk" }, h("input", { type: "checkbox", checked: x.done, "aria-label": t("t_done"), onChange: (e) => act(() => api.post(`/api/tasks/${x.id}/update`, { done: e.target.checked })) })),
      h("td", {}, h("b", {}, x.title)), h("td", {}, badge(x.importance)), h("td", {}, when(x)),
      h("td", { class: "c-act" }, h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => act(() => api.post(`/api/tasks/${x.id}/delete`, {})) }, icon("trash"))));
  };

  const table = (rows) => h("div", { class: "paper" }, h("table", { class: "tasks-table" },
    h("thead", {}, h("tr", {}, h("th", { class: "c-chk" }, ""), h("th", {}, t("t_col_task")), h("th", {}, t("t_importance")), h("th", {}, t("t_deadline")), h("th", { class: "c-act" }, ""))),
    h("tbody", {}, rows.map(row))));

  const open = sortedOpen(data);
  const shown = opts.limit ? open.slice(0, opts.limit) : open;
  const done = data.tasks.filter((x) => x.done);
  return h("div", {},
    open.length ? table(shown) : h("div", { class: "paper empty" }, h("h3", {}, t("t_none"))),
    opts.limit && open.length > shown.length ? h("p", { class: "small", style: { marginTop: ".5rem" } }, h("a", { href: "#/tasks" }, t("tasks_see_all", { n: open.length }))) : null,
    opts.showDone && done.length ? h("details", { class: "more" }, h("summary", {}, `${t("t_done_section")} (${done.length})`), table(done)) : null);
}
