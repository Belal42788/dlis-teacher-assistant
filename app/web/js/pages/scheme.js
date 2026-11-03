import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { gradeName, triName, fmtShort } from "../labels.js";

const memo = { grade: "", tri: "" };

// Scheme of work: one row per week = what will be taught, from which source and pages. Everything else (lesson plans, quizzes, slides) starts from it.
export async function renderScheme(root) {
  const [structure, ov] = await Promise.all([api.get("/api/structure"), api.get("/api/overview")]);
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  if (!structure.grades.length || !tris.length) {
    root.replaceChildren(h("div", { class: "page" }, h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_calendar")))));
    return;
  }
  const gradeSel = h("select", { onChange: () => { memo.grade = gradeSel.value; load(); } }, structure.grades.map((g) => h("option", { value: g.id }, gradeName(g))));
  const triSel = h("select", { onChange: () => { memo.tri = triSel.value; load(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  if (memo.grade && structure.grades.some((g) => g.id === memo.grade)) gradeSel.value = memo.grade; else memo.grade = gradeSel.value;
  triSel.value = memo.tri !== "" && tris.some((x) => String(x.index) === String(memo.tri)) ? memo.tri : (ov.position.state === "in_term" ? ov.position.trimester : tris[0].index);
  memo.tri = triSel.value;
  const body = h("div", {});
  const fileBox = h("div", {});
  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  let rows = [];
  const saveRows = () => api.put("/api/scheme", { grade_id: gradeSel.value, trimester: +triSel.value, weeks: rows.filter((r) => r.w.school_days > 0).map((r) => ({ week: r.w.week, topic: r.topic.value, pages: r.pages.value, source_id: r.src.value, unit: r.unit.value, objectives: r.obj.value })) });
  const showFile = (r) => fileBox.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel)),
    h("div", { class: "row" }, h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: false })) }, icon("file"), t("d_open_file")),
      h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: true })) }, icon("folder"), t("d_open_folder")))));

  async function load() {
    const d = await guarded(() => api.get(`/api/scheme?grade=${gradeSel.value}&tri=${triSel.value}`)); if (!d) return;
    const today = new Date().toISOString().slice(0, 10);
    rows = d.weeks.map((w) => ({
      w, unit: h("input", { type: "text", value: w.unit, maxlength: 80, style: { width: "9em" }, placeholder: t("sc_unit_ph"), "aria-label": t("sc_unit") }),
      obj: h("textarea", { rows: 2, value: w.objectives, placeholder: t("sc_obj_ph"), "aria-label": t("sc_objectives"), style: { minHeight: "0", marginTop: ".3rem" } }),
      topic: h("input", { type: "text", value: w.topic, maxlength: 160, placeholder: t("sc_topic_ph"), "aria-label": t("sc_topic") }),
      pages: h("input", { type: "text", value: w.pages, maxlength: 60, dir: "ltr", style: { width: "7em" }, placeholder: "10-14", "aria-label": t("sc_pages") }),
      src: h("select", { "aria-label": t("sc_source") }, h("option", { value: "" }, t("sc_no_source")), d.sources.map((s) => h("option", { value: s.id, selected: s.id === w.source_id }, s.title))),
    }));
    body.replaceChildren(
      d.sources.length ? null : h("p", { class: "muted small" }, t("sc_no_sources")),
      h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
        h("thead", {}, h("tr", {}, ["sc_week", "sc_unit", "sc_topic", "sc_source", "sc_pages", "sc_status"].map((k) => h("th", {}, t(k))))),
        h("tbody", {}, rows.map((r) => {
          const w = r.w, off = w.school_days === 0, now = w.start <= today && today <= w.end;
          return h("tr", { class: now ? "now" : "" },
            h("td", {}, h("b", {}, w.week), h("div", { class: "muted small" }, `${fmtShort(w.start)} – ${fmtShort(w.end)}`), now ? h("span", { class: "chip on small" }, t("sc_now")) : null),
            off ? h("td", { colspan: 4 }, h("span", { class: "muted" }, w.holiday || t("sc_no_classes"))) : h("td", {}, r.unit),
            ...(off ? [] : [h("td", {}, r.topic, r.obj)]),
            ...(off ? [] : [h("td", {}, r.src), h("td", {}, r.pages)]),
            h("td", {}, w.has_plan ? h("span", { class: "chip on small" }, t("sc_planned")) : null, w.taught.length ? h("span", { class: "chip small", title: w.taught.join(" · ") }, t("sc_taught")) : null));
        })))),
      h("div", { class: "row", style: { marginTop: ".8rem" } },
        h("button", { class: "btn primary", onClick: () => guarded(async () => { await saveRows(); toast(t("saved")); await load(); }) }, icon("check"), t("save")),
        h("button", { class: "btn", onClick: (e) => guarded(async () => { await saveRows(); const r = await api.post("/api/docs/trimester-plan", { grade_id: gradeSel.value, trimester: +triSel.value, lessons: rows.map((x) => x.topic.value) }); showFile(r); }) }, icon("file"), t("sc_word")),
        h("button", { class: "btn", disabled: !ai.ready, onClick: (e) => guarded(async () => {
          const r = await api.post("/api/ai/trimester", { grade_id: gradeSel.value, trimester: +triSel.value, textbooks: "" });
          rows.forEach((x, i) => { if (x.w.school_days > 0 && r.lessons[i] && !x.topic.value.trim()) x.topic.value = r.lessons[i]; });
          toast(t("ai_filled"));
        }) }, icon("spark"), t("sc_ai"))),
      h("p", { class: "muted small" }, t("sc_note")), fileBox);
  }
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_scheme")), h("p", {}, t("sc_lead")))),
    h("div", { class: "panel sticky-pick" }, h("div", { class: "pick-row" }, h("label", {}, h("span", { class: "label" }, t("d_class")), gradeSel), h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel))),
    body));
  await load();
}
