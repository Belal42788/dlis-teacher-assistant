import { hubTabs } from "../components/hubtabs.js";
import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { renderSlides } from "./slides.js";
import { docsShared } from "../components/docs_shared.js";
import { lessonPanel } from "../components/docs_lesson.js";
import { quizPanel } from "../components/docs_quiz.js";
import { certsPanel } from "../components/docs_certs.js";
import { gradingPanel } from "../components/docs_grading.js";
import { revisionPanel } from "../components/docs_revision.js";
import { weekPanel } from "../components/docs_week.js";
import { roomLabel, gradeName, fmtShort, triName } from "../labels.js";

const memoDocs = { tab: "wk", step: 1 };

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
  // one kind of file at a time: the page stays short and the teacher sees only what they chose
  const panelList = [["wk", week.el, "wk_tab"], ["lp", lesson.el, "d_lp_title"], ["quiz", quiz.el, "d_quiz_title"], ["rv", revision.el, "rv_title"], ["sl", slidesBox, "hub_make_slides"], ["gs", grading.el, "d_gs_title"], ["ct", certs.el, "ct_title"]];
  // three steps: 1) class and week, 2) what to make, 3) fill it in and make it. Each step shows one thing.
  const KIND_ICON = { wk: "spark", lp: "file", quiz: "list", rv: "check", sl: "slides", gs: "tasks", ct: "user" };
  const stepNames = [t("dz_step1"), t("dz_step2"), t("dz_step3")];
  const stepBar = h("div", { class: "steps", role: "list" });
  const step1 = h("div", {}, pickPanel, h("div", { class: "foot" }, h("span", { class: "grow" }), h("button", { class: "btn pri", "data-step-next": "", onClick: () => go(2) }, t("dz_next"), " ", icon("chevron"))));
  const step2 = h("div", { class: "panel" },
    h("div", { class: "opts" }, panelList.map(([id, , key]) =>
      h("button", { class: "opt", "data-kind-opt": id, onClick: () => { showTab(id); go(3); } }, icon(KIND_ICON[id] || "file"), h("b", {}, t(key)), h("small", {}, t(`dz_hint_${id}`))))),
    h("div", { class: "foot" }, h("button", { class: "btn", onClick: () => go(1) }, icon("back"), " ", t("dz_back"))));
  const summary = h("div", { class: "dz-sum" });
  const step3 = h("div", {}, summary, ...panelList.map(([, el]) => el), result);
  function showTab(id) {
    memoDocs.tab = id;
    panelList.forEach(([k, el]) => { el.hidden = k !== id; });
    if (id === "sl" && !slidesBox.dataset.ready) { slidesBox.dataset.ready = "1"; guarded(() => renderSlides(slidesBox, { embedded: true })); }
  }
  function go(n) {
    memoDocs.step = n;
    step1.hidden = n !== 1; step2.hidden = n !== 2; step3.hidden = n !== 3;
    stepBar.replaceChildren(...stepNames.map((name, i) => h("button", { class: `st${i + 1 === n ? " on" : i + 1 < n ? " ok" : ""}`, role: "listitem", disabled: i + 1 > n,
      onClick: () => go(i + 1) }, h("i", {}, i + 1 < n ? "✓" : String(i + 1)), name)));
    if (n === 3) {
      const kind = panelList.find(([k]) => k === memoDocs.tab);
      summary.replaceChildren(h("span", { class: "chip" }, kind ? t(kind[2]) : ""), " ",
        memoDocs.tab === "sl" ? "" : memoDocs.tab === "ct" ? (roomSel.selectedOptions[0]?.textContent || "") : `${roomSel.selectedOptions[0]?.textContent || ""} · ${weekSel.selectedOptions[0]?.textContent || ""}`,
        h("button", { class: "btn sm", onClick: () => go(2) }, t("dz_change")));
    }
    window.scrollTo?.(0, 0);
  }
  showTab(panelList.some(([k]) => k === memoDocs.tab) ? memoDocs.tab : "wk");
  drawWeeks();
  root.replaceChildren(h("div", { class: "page" }, hubTabs("create", "docs"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_docs")), h("p", {}, t("docs_lead")))),
    stepBar, step1, step2, step3));
  go(memoDocs.step || 1);
  await refresh();
}