import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { renderSlides } from "./slides.js";
import { docsShared } from "../components/docs_shared.js";
import { lessonPanel } from "../components/docs_lesson.js";
import { quizPanel } from "../components/docs_quiz.js";
import { certsPanel } from "../components/docs_certs.js";
import { gradingPanel } from "../components/docs_grading.js";
import { revisionPanel } from "../components/docs_revision.js";
import { weekPanel } from "../components/docs_week.js";
import { roomLabel, gradeName, fmtShort, triName } from "../labels.js";

const memoDocs = { tab: "wk" };

// "Create files": three steps (class and week, what to make, fill it in). Each kind of file is its own panel in components/docs_*.js;
// this page picks the class and week, keeps them in `sel`, and hands each panel what it needs.
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

  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  const catalog = await guarded(() => api.get("/api/tools")) || { groups: [], tools: [] };
  const shared = docsShared(ai);
  const ctx = { root, structure, rooms, used, sel, gradeOf, ai, ...shared };
  const lesson = await lessonPanel(ctx);
  const quiz = await quizPanel(ctx);
  const revision = await revisionPanel(ctx);
  const grading = gradingPanel(ctx);
  const certs = certsPanel(ctx);
  const week = await weekPanel(ctx);
  const result = shared.result;

  // the week's topic comes from the scheme of work: shown here, and put in the topic boxes that are still empty
  const planBox = h("div", { class: "plan-line small", style: { marginTop: ".4rem" } });
  async function planLine() {
    const g = gradeOf();
    const r = await guarded(() => api.get(`/api/slides/topics?grade=${g.id}&tri=${sel.tri}`));
    const w = r && r.weeks.find((x) => x.week === sel.week);
    if (!w || !w.topic) { planBox.replaceChildren(icon("info"), " ", t("pl_none"), " ", h("a", { href: "#/scheme" }, t("pl_open"))); return; }
    if (w.curriculum) lesson.setObjectives(w.curriculum);
    planBox.replaceChildren(icon("list"), " ", t("pl_from"), " ", h("b", {}, w.unit ? `${w.unit} · ${w.topic}` : w.topic), w.pages ? ` · ${t("sc_pages")} ${w.pages}` : "", " ", h("a", { href: "#/scheme" }, t("pl_edit")));
    for (const el of [lesson.topic, quiz.topic, revision.topic]) { if (!el.value.trim() || el.dataset.auto === el.value) { el.value = w.topic; el.dataset.auto = w.topic; } }
  }
  // the student names are loaded once per class and shared by the two boxes that list them
  async function loadNames() {
    const r = await guarded(() => api.get(`/api/rooms/${sel.room}/students`));
    const names = (r && r.names) || [];
    grading.setNames(names); certs.setNames(names);
  }
  async function refresh() {
    const c = await guarded(() => api.get(`/api/docs/context?room=${sel.room}&tri=${sel.tri}&week=${sel.week}`));
    if (!c) return;
    const notes = Object.entries(c.day_notes).map(([d, n]) => `${t(`day_${d}`)}: ${n}`);
    info.replaceChildren(`${gradeName(gradeOf())} · ${c.range}`, notes.length ? h("div", {}, icon("info"), " ", notes.join(" · ")) : null);
    grading.count.textContent = t("students_n", { n: c.students });
    loadNames();
    week.fillTopics();
    planLine();
    lesson.applyContext(c);
  }

  const pickPanel = h("div", { class: "panel sticky-pick" },
    h("div", { class: "pick-row" },
      h("label", {}, h("span", { class: "label" }, t("d_class")), roomSel),
      h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel),
      h("label", {}, h("span", { class: "label" }, t("d_week")), weekSel)), info, planBox);
  const slidesBox = h("div", {});   // the slide maker lives here as one more thing to make; it opens the first time it is chosen
  const panelList = [["wk", week.el, "wk_tab"], ["lp", lesson.el, "d_lp_title"], ["quiz", quiz.el, "d_quiz_title"], ["rv", revision.el, "rv_title"], ["sl", slidesBox, "hub_make_slides"], ["gs", grading.el, "d_gs_title"], ["ct", certs.el, "ct_title"]];
  // Two views. The hub shows everything at once as big tiles: the school's files, then the AI tools. A tile opens its work view;
  // the class, term and week are picked there (they start on the current week), so the teacher never has to choose before knowing what to make.
  const KIND_ICON = { wk: "spark", lp: "file", quiz: "list", rv: "check", sl: "slides", gs: "tasks", ct: "user" };
  const lang = getLang(), L = (o) => (o && (o[lang] || o.en)) || "";
  const hub = h("div", { class: "cr-hub" },
    h("section", {}, h("h2", {}, t("cr_official")), h("p", { class: "muted" }, t("cr_official_hint")),
      h("div", { class: "opts kinds" }, panelList.map(([id, , key]) =>
        h("button", { class: "opt", "data-kind-opt": id, onClick: () => { showTab(id); go(2); } }, icon(KIND_ICON[id] || "file"), h("b", {}, t(key)), h("small", {}, t(`dz_hint_${id}`)))))),
    h("section", {}, h("h2", {}, t("cr_tools")), h("p", { class: "muted" }, t("cr_tools_hint")),
      catalog.groups.map((g) => h("div", { class: "cr-group" }, h("h3", {}, L(g.name)),
        h("div", { class: "opts tiles" }, catalog.tools.filter((x) => x.group === g.id).map((x) =>
          h("a", { class: "opt", href: `#/tools?tool=${x.id}`, "data-tool-opt": x.id }, icon("spark"), h("b", {}, L(x.name)), h("small", {}, L(x.desc)))))))));
  const summary = h("div", { class: "dz-sum" });
  const work = h("div", { class: "cr-work" }, h("div", { class: "row" }, h("button", { class: "btn", "data-back-hub": "", onClick: () => go(1) }, icon("back"), " ", t("cr_back")), h("span", { class: "grow" }), summary),
    pickPanel, ...panelList.map(([, el]) => el), result);
  function showTab(id) {
    memoDocs.tab = id;
    panelList.forEach(([k, el]) => { el.hidden = k !== id; });
    pickPanel.hidden = id === "sl";   // the slide maker has its own topic and class boxes
    if (id === "sl" && !slidesBox.dataset.ready) { slidesBox.dataset.ready = "1"; guarded(() => renderSlides(slidesBox, { embedded: true })); }
    const kind = panelList.find(([k]) => k === id);
    summary.replaceChildren(h("span", { class: "chip" }, kind ? t(kind[2]) : ""));
  }
  function go(n) {
    hub.hidden = n !== 1; work.hidden = n !== 2;
    window.scrollTo?.(0, 0);
  }
  showTab(panelList.some(([k]) => k === memoDocs.tab) ? memoDocs.tab : "wk");
  drawWeeks();
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_docs")), h("p", {}, t("docs_lead")))),
    hub, work));
  go(1);
  await refresh();
}