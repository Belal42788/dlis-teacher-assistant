import { h, icon, confirmBox, modal, toast } from "./dom.js";
import { api, guarded, inPage, readsFor, warm } from "./api.js";
import { t, setLang, hasKey } from "./i18n.js";
import { applyFontSize, applyDensity } from "./fontsize.js";
import { state } from "./state.js";
import { startWizard } from "./wizard.js";
import { renderToday } from "./pages/today.js";
import { renderClasses } from "./pages/classes.js";
import { renderTimetable } from "./pages/timetable.js";
import { renderCalendar } from "./pages/calendar.js";
import { renderSettings } from "./pages/settings.js";
import { renderDocs } from "./pages/docs.js";
import { renderTasks } from "./pages/tasks.js";
import { renderLog } from "./pages/log.js";
import { renderBehavior } from "./pages/behavior.js";
import { renderSeating } from "./pages/seating.js";
import { renderSources } from "./pages/sources.js";
import { renderLibrary } from "./pages/library.js";
import { renderScheme } from "./pages/scheme.js";
import { renderTools } from "./pages/tools.js";
import { renderGrades } from "./pages/grades.js";
import { renderInsights } from "./pages/insights.js";
import { openQuick } from "./components/quick.js";
import { renderMap } from "./pages/map.js";
import { renderAnnouncements } from "./pages/announcements.js";
import { renderPublish } from "./pages/publish.js";
import { renderProgress } from "./pages/progress.js";
import { renderParentWeek } from "./pages/parentweek.js";
import { renderFollowup } from "./pages/followup.js";
import { renderChat } from "./pages/chat.js";
import { renderHelp } from "./pages/help.js";
import { renderReminders } from "./pages/reminders.js";
import { startReminders } from "./reminders.js";

const root = document.getElementById("app");

// Windows app window without the system title bar: draw a slim one in the school colours.
function tbIcon(inner) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 10 10");
  s.innerHTML = inner;
  return s;
}

function drawTitlebar() {
  if (!state.boot?.frameless || document.getElementById("titlebar")) return;
  const call = (m) => window.pywebview?.api?.[m]?.();
  document.body.classList.add("has-titlebar");
  document.body.prepend(h("div", { id: "titlebar", class: "titlebar", dir: "ltr", onDblclick: (e) => { if (!e.target.closest(".tb-btns")) call("toggle_maximize"); },
    onMousedown: (e) => { if (e.button === 0 && !e.target.closest(".tb-btns")) call("start_drag"); } },
    h("span", { class: "tb-mark" }, h("img", { src: "/resources/logo-mark.png", alt: "" })),
    h("span", { class: "tb-title" }, "DLIS Teacher Assistant"),
    h("span", { class: "tb-btns" },
      h("button", { class: "tb-btn", "aria-label": "Minimize", onClick: () => call("minimize") }, tbIcon('<path d="M1 5h8"/>')),
      h("button", { class: "tb-btn", "aria-label": "Maximize", onClick: () => call("toggle_maximize") }, tbIcon('<rect x="1.5" y="1.5" width="7" height="7"/>')),
      h("button", { class: "tb-btn close", "aria-label": "Close", onClick: () => call("close") }, tbIcon('<path d="M1.5 1.5l7 7M8.5 1.5l-7 7"/>')))));
}
const PAGES = [
  { id: "today", icon: "today", group: "day", render: renderToday },
  { id: "timetable", icon: "timetable", group: "day", render: renderTimetable },
  { id: "calendar", icon: "calendar", group: "day", render: renderCalendar },
  { id: "tasks", icon: "tasks", group: "day", render: renderTasks },
  { id: "reminders", nav: "tasks", render: renderReminders },
  { id: "scheme", icon: "list", group: "prepare", render: renderScheme },
  { id: "docs", icon: "file", group: "prepare", render: renderDocs },
  { id: "tools", icon: "tool", group: "prepare", render: renderTools },
  { id: "library", icon: "folder", group: "prepare", render: renderLibrary },
  { id: "sources", nav: "library", render: renderSources },
  { id: "publish", nav: "library", render: renderPublish },
  { id: "chat", icon: "spark", group: "prepare", render: renderChat },
  { id: "classes", icon: "classes", group: "school", render: renderClasses },
  { id: "log", nav: "classes", render: renderLog },
  { id: "progress", nav: "classes", render: renderProgress },
  { id: "grades", nav: "classes", render: renderGrades },
  { id: "behavior", nav: "classes", render: renderBehavior },
  { id: "seating", nav: "classes", render: renderSeating },
  { id: "insights", nav: "classes", render: renderInsights },
  { id: "announcements", icon: "megaphone", group: "school", need: "online", render: renderAnnouncements },
  { id: "parentweek", nav: "announcements", render: renderParentWeek },
  { id: "followup", icon: "tasks", group: "school", need: "admin", render: renderFollowup },
  { id: "map", icon: "map", group: "school", render: renderMap },
  { id: "settings", icon: "settings", group: "end", render: renderSettings },
  { id: "help", icon: "info", group: "end", render: renderHelp },
];

let mode = "";          // "wizard" | "app"
let lastHash = "";

async function boot(forceWizardStep) {
  state.boot = await api.get("/api/bootstrap");
  drawTitlebar();
  if (state.boot.language) setLang(state.boot.language);
  if (!state.boot.language) return startWizard(root, () => boot(), "language");
  if (state.boot.folder_missing && !forceWizardStep) return folderMissingScreen(state.boot.folder_missing);
  if (!state.boot.data_folder) return startWizard(root, () => boot(), "folder");
  if (state.boot.data_locked && !forceWizardStep) return dataLockedScreen(state.boot.data_locked, state.boot.data_folder);
  if (!state.boot.setup_done || forceWizardStep) return startWizard(root, () => boot(), forceWizardStep || "about");
  state.settings = state.boot.settings;
  mode = "app";
  drawShell();
  showProblems(state.boot.problems || []);
  if (state.boot.upgraded_from) { const n = h("div", { class: "notice", role: "status" }, icon("info"), h("div", { class: "grow" }, t("upgraded_note")), h("button", { class: "btn small", onClick: () => n.remove() }, t("ok"))); document.body.append(n); }
  api.get("/api/cloud").then((c) => {
    document.querySelectorAll(".nav a[data-need]").forEach((a) => { a.hidden = a.dataset.need === "admin" ? !(c.signed_in && c.role === "admin") : !(c.signed_in && c.role); });
    const today = new Date().toISOString().slice(0, 10);
    if (c.signed_in && (c.role === "teacher" || c.role === "admin") && localStorage.getItem("pushed") !== today) { localStorage.setItem("pushed", today); api.post("/api/status/push", {}).catch(() => {}); }
    const el = document.getElementById("net-chip"); if (!el) return; el.hidden = false;
    el.textContent = c.signed_in ? `● ${t("net_online")}` : `○ ${t("net_offline")}`; el.classList.toggle("on", !!c.signed_in); }).catch(() => {});
  startReminders();
  checkForUpdate();
  await route();
}

// The data folder is not reachable (OneDrive paused, drive unplugged...): never silently start from scratch.
function folderMissingScreen(path) {
  mode = "";
  root.replaceChildren(h("div", { class: "wiz" }, h("div", { class: "wiz-body" }, h("div", { class: "page narrow" },
    h("div", { class: "banner warn" }, icon("warn"), h("div", {}, h("b", {}, t("folder_missing_title")), h("div", { class: "dir-ltr small" }, path), h("p", {}, t("folder_missing_lead")))),
    h("div", { class: "row" },
      h("button", { class: "btn primary", onClick: () => location.reload() }, t("folder_missing_retry")),
      h("button", { class: "btn", onClick: () => boot("folder") }, t("folder_missing_other")))))));
}

// What a page looks like while it loads (only shown when loading is slow).
function skeleton() {
  const bar = (w, hgt = "1rem") => h("div", { class: "skel-bar", style: { width: w, height: hgt } });
  return h("div", { class: "page skeleton", "aria-hidden": "true" }, bar("38%", "1.8rem"), bar("62%"),
    h("div", { class: "skel-card" }, bar("30%"), bar("92%"), bar("84%")),
    h("div", { class: "skel-card" }, bar("26%"), bar("90%"), bar("70%")));
}

// "A newer version is out": one quiet notice, never blocks anything, and "Later" hides it for that version.
function checkForUpdate() {
  api.get("/api/update").then((u) => {
    if (!u.available) return;
    const box = h("div", { class: "notice", role: "status" }, icon("info"),
      h("div", { class: "grow" }, h("b", {}, t("upd_title", { v: u.version })), u.notes ? h("div", { class: "small" }, u.notes) : null),
      h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open-url", { url: u.url })) }, t("upd_get")),
      h("button", { class: "btn small", onClick: () => { api.post("/api/update/dismiss", { version: u.version }).catch(() => {}); box.remove(); } }, t("upd_later")));
    document.body.append(box);
  }).catch(() => {});
}

// The folder was made by a newer app, or its upgrade stopped: nothing is saved, so nothing can be damaged.
function dataLockedScreen(why, path) {
  mode = "";
  root.replaceChildren(h("div", { class: "wiz" }, h("div", { class: "wiz-body" }, h("div", { class: "page narrow" },
    h("div", { class: "banner warn" }, icon("warn"), h("div", {}, h("b", {}, t(why === "newer" ? "locked_newer_title" : "locked_failed_title")), h("div", { class: "dir-ltr small" }, path), h("p", {}, t(why === "newer" ? "locked_newer_lead" : "locked_failed_lead")))),
    h("div", { class: "row" },
      h("button", { class: "btn primary", onClick: () => location.reload() }, t("folder_missing_retry")),
      h("button", { class: "btn", onClick: () => boot("folder") }, t("folder_missing_other")))))));
}

function showProblems(list) {
  if (!list.length) return;
  const files = [...new Set(list.map((p) => p.file))].join(", ");
  const lost = list.some((p) => !p.restored);
  const box = h("div", { class: `notice ${lost ? "bad" : ""}`, role: "alert" }, icon("warn"),
    h("div", { class: "grow" }, h("b", {}, t(lost ? "problem_lost" : "problem_restored")), h("div", { class: "small dir-ltr" }, files)),
    h("button", { class: "btn small", onClick: () => box.remove() }, t("ok")));
  document.body.append(box);
}

function feedbackDialog() {
  const text = h("textarea", { rows: 5, maxlength: 1500, placeholder: t("fb_ph") });
  const page = shownPage;
  modal({ title: t("fb_title"), body: h("div", {}, h("p", { class: "muted small" }, t("fb_lead")), text),
    actions: [
      { label: t("fb_export"), onClick: async () => { const r = await guarded(() => api.post("/api/feedback/export", {})); if (r) await guarded(() => api.post("/api/open", { path: r.path })); return false; }, close: false },
      { label: t("save"), kind: "primary", onClick: async () => { if (!text.value.trim()) return false; const r = await guarded(() => api.post("/api/feedback", { page, text: text.value })); if (!r) return false; toast(t("saved")); } }] });
}

// Ctrl+K (or Cmd+K) opens the quick search from anywhere inside the app
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.code === "KeyK" || String(e.key).toLowerCase() === "k") && mode === "app") { e.preventDefault(); openQuick(PAGES); }
});

const GROUPS = ["day", "prepare", "school"];
let openGroup = "day";
// The bar on top has the three groups; the pages of the open group are listed under it, so every page is visible without scrolling anything.
function setGroup(g) {
  openGroup = g;
  document.querySelectorAll(".tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.group === g)));
  document.querySelectorAll(".sub a").forEach((a) => a.classList.toggle("off", a.dataset.group !== g));
}
function drawShell() {
  const s = state.settings;
  const link = (p) => h("a", { href: `#/${p.id}`, "data-page": p.id, "data-group": p.group, "data-need": p.need || null, hidden: p.need ? true : null, title: t(`nav_${p.id}`) }, icon(p.icon), h("span", {}, t(`nav_${p.id}`)));
  root.replaceChildren(h("div", { class: "shell" },
    h("header", { class: "top" },
      h("div", { class: "brand" }, h("span", { class: "mark" }, h("img", { src: "/resources/logo-mark.png", alt: "" })), h("div", {}, h("b", {}, t("app_name")), h("small", {}, s.school_name))),
      h("div", { class: "tabs", role: "tablist", "aria-label": t("main_menu") }, GROUPS.map((g) => h("button", { class: "tab", role: "tab", type: "button", "data-group": g, "aria-selected": "false", onClick: () => setGroup(g) }, t(`grp_${g}`)))),
      h("div", { class: "tools" },
        h("button", { class: "quick-btn", type: "button", "aria-label": t("qk_btn"), onClick: () => openQuick(PAGES) }, icon("search"), h("span", {}, t("qk_btn")), h("kbd", {}, "Ctrl K")),
        h("a", { class: "net-chip", href: "#/settings", id: "net-chip", hidden: true }),
        h("div", { class: "nav" }, PAGES.filter((p) => p.group === "end").map(link)),
        h("div", { class: "who" }, h("b", {}, s.teacher_name || "—"), s.subject || ""))),
    h("nav", { class: "nav sub", "aria-label": t("main_menu") }, PAGES.filter((p) => p.icon && GROUPS.includes(p.group)).map(link)),
    h("main", { class: "main", id: "main", tabindex: "-1" }),
    h("button", { class: "fb-btn", "aria-label": t("fb_title"), onClick: feedbackDialog }, t("fb_btn"))));
  setGroup(openGroup);
}

// What was typed on a page is kept while the teacher visits another tab, and comes back when they return.
const DRAFT_PAGES = new Set(["docs", "tasks", "reminders", "log", "chat", "tools"]);
const drafts = new Map();
const fieldsOf = (main) => [...main.querySelectorAll("input, textarea, select")].filter((el) => el.type !== "password" && el.type !== "file" && el.type !== "button" && !el.closest("[data-nodraft]"));
function saveDraft(pageId) {
  const main = document.getElementById("main");
  if (!main || !pageId || !DRAFT_PAGES.has(pageId)) return;
  const fields = fieldsOf(main);
  if (!fields.length) return;
  drafts.set(pageId, {
    scroll: main.scrollTop,
    values: fields.map((el) => (el.type === "checkbox" || el.type === "radio" ? el.checked : el.value)),
    open: [...main.querySelectorAll("details")].map((d) => d.open),
  });
}
function restoreDraft(pageId) {
  const d = drafts.get(pageId), main = document.getElementById("main");
  if (!d || !main) return;
  const fields = fieldsOf(main);
  if (fields.length !== d.values.length) return;
  fields.forEach((el, i) => {
    const v = d.values[i];
    if (el.type === "checkbox" || el.type === "radio") { if (el.checked !== v) el.checked = v; return; }
    if (el.value === v || v === "") return;
    if (el.tagName === "SELECT" && location.hash.includes("?")) return; // opened from a link that picked a class/week
    el.value = v;
    if (el.tagName === "SELECT") { if (el.value === v) el.dispatchEvent(new Event("change", { bubbles: true })); }
    else el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  main.querySelectorAll("details").forEach((el, i) => { if (d.open[i] !== undefined) el.open = d.open[i]; });
  main.scrollTop = d.scroll;
}
applyFontSize();
applyDensity();
let shownPage = null;

// What each page reads first, so the very first visit can also be prepared. After a page has been opened once, what it
// really read is remembered and used instead.
const SEED = {
  today: ["/api/tasks", "/api/log/last", "/api/log"], tasks: ["/api/tasks", "/api/weekly"],
  tools: ["/api/tools"], library: ["/api/library", "/api/publications"], chat: ["/api/chats"],
  announcements: ["/api/announcements"], followup: ["/api/cloud"], map: ["/api/map", "/api/structure"],
  timetable: ["/api/timetable", "/api/structure"], calendar: ["/api/calendar", "/api/school-calendar", "/api/overview"], classes: ["/api/structure"],
};
const prepare = (id) => { const own = readsFor(id); warm(own.length ? own : (SEED[id] || [])); };
function listenForTabs() {
  // pointing at, pressing or focusing a menu entry starts its reads, so by the time the click lands they are on their way
  const go = (e) => { const a = e.target.closest?.(".nav a[data-page]"); if (a) prepare(a.dataset.page); };
  ["pointerover", "pointerdown", "focusin"].forEach((ev) => document.addEventListener(ev, go, { passive: true }));
}
listenForTabs();
// when a page has appeared, the pages next to it in the same bar get ready while the computer is idle
function prepareNeighbours(page) {
  const idle = window.requestIdleCallback || ((f) => setTimeout(f, 400));
  idle(() => { [...document.querySelectorAll(`.sub a[data-group="${page.group}"]`)].forEach((a, i) => setTimeout(() => prepare(a.dataset.page), i * 150)); });
}

// Safety net for screen readers: a box with no label of its own is named after the text on its row, so it is never read as just "checkbox".
function nameLooseControls(root) {
  root.querySelectorAll("input:not([type=hidden]):not([aria-label]), select:not([aria-label]), textarea:not([aria-label])").forEach((el) => {
    if (el.labels && el.labels.length) return;
    const row = el.closest("label, tr, .row, .list-row, .task, .c-act-in") || el.parentElement;
    const txt = row ? row.textContent.replace(/\s+/g, " ").trim().slice(0, 50) : "";
    if (txt) el.setAttribute("aria-label", txt);
  });
}

async function route() {
  if (mode !== "app") return;
  saveDraft(shownPage);
  const id = (location.hash.replace(/^#\//, "") || "today").split("?")[0];
  const page = PAGES.find((p) => p.id === id) || PAGES[0];
  state.isDirty = null;
  document.querySelectorAll(".nav a").forEach((a) => { if (a.dataset.page === (page.nav || page.id)) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  const owner = PAGES.find((p) => p.id === (page.nav || page.id));
  if (owner && GROUPS.includes(owner.group)) setGroup(owner.group);
  const main = document.getElementById("main");
  lastHash = `#/${page.id}`;
  document.title = hasKey(`nav_${page.id}`) ? `${t(`nav_${page.id}`)} · ${t("app_name")}` : t("app_name");   // the window title says where you are
  try {
    // if the teacher starts typing while the page is still loading, their new text wins over the old draft
    let typed = false;
    const mark = (e) => { if (e.isTrusted) typed = true; };
    main.addEventListener("input", mark, true); main.addEventListener("change", mark, true);
    main.classList.add("busy");
    inPage(page.id);
    const slow = setTimeout(() => document.body.classList.add("slow-nav"), 150);   // a thin progress line, only if loading is not instant
    const skel = setTimeout(() => { if (main.classList.contains("busy")) main.replaceChildren(skeleton()); }, 450);   // still loading after almost half a second: grey blocks, not the old page
    try { await page.render(main, { reloadApp }); } finally { clearTimeout(slow); clearTimeout(skel); document.body.classList.remove("slow-nav"); main.classList.remove("busy"); main.removeEventListener("input", mark, true); main.removeEventListener("change", mark, true); }
    if (shownPage !== page.id) main.scrollTop = 0; // a new tab starts at the top, not where the last one was scrolled to
    shownPage = page.id;
    nameLooseControls(main);
    prepareNeighbours(page);
    api.note("/api/usage", { page: page.id }).catch(() => {});
    if (!typed) restoreDraft(page.id);
  } catch (e) {
    console.error(e);
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "banner holiday" }, icon("warn"), h("div", {}, h("b", {}, t("err_page")), h("div", {}, e.friendly || e.message)))));
  }
}

// Leaving a page with unsaved changes asks first.
let suppress = 0;
window.addEventListener("hashchange", async () => {
  if (suppress > 0) { suppress--; return; }
  if (state.isDirty && state.isDirty()) {
    const target = location.hash;
    suppress++; location.hash = lastHash;
    const leave = await confirmBox(t("unsaved_confirm"), { okLabel: t("leave_page"), danger: false });
    if (!leave) return;
    state.isDirty = null; suppress++; location.hash = target;
    return route();
  }
  route();
});

async function reloadApp(full) {
  if (full) return boot();
  state.boot = await api.get("/api/bootstrap");
  state.settings = state.boot.settings;
  drawShell(); route();
}

// Lets the launcher know the window is still open (so closing the browser tab quits the app).
setInterval(() => api.get("/api/ping").catch(() => {}), 8000);

boot().catch((e) => {
  console.error(e);
  root.replaceChildren(h("div", { class: "wiz-body" }, h("div", { class: "wiz-card" }, h("h1", {}, "DLIS Teacher Assistant"), h("p", { class: "lead" }, String(e.message || e)))));
});
