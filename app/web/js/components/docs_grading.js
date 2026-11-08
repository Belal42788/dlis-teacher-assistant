import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { t, getLang } from "../i18n.js";

// The grading sheet box: Word or Excel, with "full mark for everyone except the absent".
export function gradingPanel(ctx) {
  const { sel, run, showResult } = ctx;
  const gsCount = h("span", { class: "muted" });
  // "full mark" for everyone except the absent: the teacher ticks the parts to fill and the students who were absent (left empty)
  const GS_PARTS = ["behavior", "attendance", "classwork", "homework", "quiz"];
  const gsFull = h("input", { type: "checkbox" });
  const gsPart = Object.fromEntries(GS_PARTS.map((k) => [k, h("input", { type: "checkbox", checked: k !== "quiz" })]));
  const gsAbsent = h("div", { class: "gs-absent", "data-nodraft": "1" });   // filled after the page loads, so it is not part of the saved draft
  const gsExtra = () => gsFull.checked ? { fill: GS_PARTS.filter((k) => gsPart[k].checked), absent: [...gsAbsent.querySelectorAll("input:checked")].map((x) => x.value) } : {};
  const gsBtn = h("button", { class: "btn primary", onClick: () => run(gsBtn, async () => {
    showResult(await api.post("/api/docs/grading-sheet", { room_id: sel.room, trimester: sel.tri, week: sel.week, lang: getLang(), ...gsExtra() }));
  }) }, icon("file"), t("d_create_gs"));
  const gsX = h("button", { class: "btn", onClick: () => run(gsX, async () => {
    showResult(await api.post("/api/docs/grading-sheet", { room_id: sel.room, trimester: sel.tri, week: sel.week, lang: getLang(), format: "xlsx", ...gsExtra() }));
  }) }, icon("file"), t("d_create_gs_xlsx"));
  const gsFullBox = h("details", { class: "fold", style: { marginTop: ".6rem" } }, h("summary", {}, t("gs_full_title")),
    h("p", { class: "muted small" }, t("gs_full_lead")),
    h("label", { class: "row" }, gsFull, h("b", {}, t("gs_full_on"))),
    h("div", { class: "row small", style: { flexWrap: "wrap", margin: ".4rem 0" } }, GS_PARTS.map((k) => h("label", { class: "row" }, gsPart[k], t(`gs_part_${k}`)))),
    h("div", { class: "label small" }, t("gs_absent")), gsAbsent);
  const panel = h("div", { class: "panel" }, h("h3", {}, t("d_gs_title")), h("p", { class: "muted small" }, t("d_gs_lead")),
    h("div", { class: "row" }, gsBtn, gsX, gsCount), gsFullBox, h("p", { class: "muted small", style: { marginTop: ".6rem" } }, t("d_gs_lms")));
  const setNames = (names) => gsAbsent.replaceChildren(...names.map((n) => h("label", { class: "row small" }, h("input", { type: "checkbox", value: n }), n)));
  return { el: panel, count: gsCount, setNames };
}
