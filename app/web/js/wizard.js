import { h, icon } from "./dom.js";
import { api, guarded, ApiError } from "./api.js";
import { t, setLang } from "./i18n.js";
import { state } from "./state.js";
import { DAYS, dayName, subjectLabel } from "./labels.js";
import { pickFolder } from "./components/folder_picker.js";
import { classPicker } from "./components/class_picker.js";
import { timetableEditor } from "./components/timetable_editor.js";
import { calendarEditor } from "./components/calendar_editor.js";
import { importOldDialog } from "./pages/settings.js";

// First-run guide: language -> folder -> about you -> classes -> timetable -> calendar -> done.
const ORDER = ["language", "folder", "account", "about", "classes", "timetable", "calendar", "done"];

export function startWizard(root, onFinished, startAt) {
  let idx = Math.max(0, ORDER.indexOf(startAt || "language"));
  const view = { collect: null, next: null, nextLabel: null, hideBack: false, skippable: false };

  async function show(step) {
    document.getElementById("toasts").replaceChildren();
    idx = ORDER.indexOf(step);
    Object.assign(view, { collect: null, next: null, nextLabel: null, hideBack: false, skippable: false });
    const body = await STEPS[step](view);
    draw(step, body);
  }

  function draw(step, body) {
    const shown = ORDER.slice(1, -1); // steps users see numbered
    root.replaceChildren(h("div", { class: "wiz" },
      h("div", { class: "wiz-top" },
        h("span", { class: "mark" }, h("img", { src: "/resources/logo-mark.png", alt: "" })), h("b", {}, t("app_name")),
        step !== "language" && step !== "done" ? h("ol", { class: "steps", "aria-label": t("steps") },
          shown.map((s, i) => h("li", { class: i + 1 === ORDER.indexOf(step) ? "now" : i + 1 < ORDER.indexOf(step) ? "done" : "", "aria-current": s === step ? "step" : null },
            h("b", {}, i + 1 < ORDER.indexOf(step) ? "✓" : i + 1), t(`step_${s}`)))) : null),
      h("div", { class: "wiz-body" }, h("div", { class: "wiz-card" }, body)),
      step === "language" ? h("div", {}) : h("div", { class: "wiz-foot" },
        view.hideBack ? h("span") : h("button", { class: "btn", onClick: () => show(ORDER[Math.max(1, idx - 1)]) }, icon("back"), t("back")),
        h("div", { class: "row" },
          view.skippable ? h("button", { class: "btn ghost", onClick: () => show(ORDER[idx + 1]) }, t("skip_for_now")) : null,
          view.next ? h("button", { class: "btn primary big", onClick: async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            const res = await guarded(async () => ({ r: await view.next() }));
            if (!res) btn.disabled = false;
            else if (res.r !== "stop") show(ORDER[idx + 1]);
          } }, view.nextLabel || t("next")) : null))));
    window.scrollTo(0, 0);
  }

  const STEPS = {
    async language() {
      const choose = async (lang) => { await api.put("/api/prefs", { language: lang }); setLang(lang); state.boot.language = lang; show("folder"); };
      return h("div", {},
        h("img", { class: "hero-logo", src: "/resources/logo.png", alt: "DLIS" }),
        h("h1", {}, "مرحبًا · Welcome"),
        h("p", { class: "lead" }, "اختر اللغة · Choose your language"),
        h("div", { class: "lang-pick" },
          h("button", { lang: "ar", onClick: () => choose("ar") }, "العربية"),
          h("button", { lang: "en", onClick: () => choose("en") }, "English")));
    },

    async folder(v) {
      v.hideBack = true;
      let chosen = state.boot.data_folder || state.boot.suggested_folder;
      const box = h("div", { class: "folder-box" }, chosen);
      v.nextLabel = t("use_this_folder");
      v.next = async () => {
        state.boot = await api.post("/api/data-folder", { path: chosen });
        if (state.boot.has_data && state.boot.setup_done) { onFinished(); return "stop"; }
      };
      return h("div", {},
        h("h1", {}, t("folder_title")),
        h("p", { class: "lead" }, t("folder_lead")),
        box,
        h("div", { class: "row", style: { margin: "1rem 0" } },
          h("button", { class: "btn", onClick: async () => {
            const p = await pickFolder({ title: t("choose_folder"), start: chosen });
            if (p) { chosen = p; box.textContent = p; }
          } }, icon("folder"), t("choose_other_folder"))),
        h("div", { class: "banner info" }, icon("info"), h("div", {}, t("folder_cloud_tip"))));
    },

    // Work with the school server (sign in) or on this computer only (offline). Asked once; it can be changed in Settings.
    async account(v) {
      const c = await api.get("/api/cloud");
      const form = h("div", { class: "panel", hidden: true });
      const email = h("input", { type: "email", dir: "ltr", value: c.email, autocomplete: "username" }), pass = h("input", { type: "password", dir: "ltr", autocomplete: "current-password" });
      const code = h("input", { type: "text", dir: "ltr", placeholder: "DLIS-…" });
      const known = c.configured;
      form.append(...(known ? [c.school ? h("p", {}, h("b", {}, c.school)) : null] : [h("label", { class: "field" }, h("span", { class: "label" }, t("cl_code")), code), h("p", { class: "muted small" }, t("cl_code_ask"))]),
        h("label", { class: "field" }, h("span", { class: "label" }, t("cl_email")), email), h("label", { class: "field" }, h("span", { class: "label" }, t("cl_pass")), pass),
        h("button", { class: "btn primary", onClick: (e) => { const b = e.currentTarget; b.disabled = true;
          guarded(async () => { if (!known) await api.post("/api/cloud/join", { code: code.value }); await api.post("/api/cloud/login", { email: email.value, password: pass.value }); show("about"); }).then((r) => { if (r === undefined) b.disabled = false; }); } }, t("cl_login")));
      return h("div", {},
        h("h1", {}, t("ac_title")), h("p", { class: "lead" }, t("ac_lead")),
        h("div", { class: "row" },
          h("button", { class: "btn primary big", onClick: () => { form.hidden = false; } }, icon("user"), t("ac_online")),
          h("button", { class: "btn big", onClick: () => guarded(async () => { await api.put("/api/cloud", { mode: "offline" }); show("about"); }) }, icon("folder"), t("ac_offline"))),
        h("p", { class: "muted small" }, t("ac_note")), form);
    },

    async about(v) {
      const s = state.boot.settings || (await api.get("/api/settings"));
      const subjects = state.boot.subjects;
      const known = subjects.some((x) => x.en === s.subject);
      const name = h("input", { type: "text", value: s.teacher_name, autocomplete: "name", "aria-required": "true" });
      const school = h("input", { type: "text", value: s.school_name });
      const subjSel = h("select", {}, h("option", { value: "" }, t("choose_subject")),
        subjects.map((x) => h("option", { value: x.en }, subjectLabel(x.en, subjects))), h("option", { value: "__other" }, t("other_subject")));
      subjSel.value = s.subject ? (known ? s.subject : "__other") : "";
      const other = h("input", { type: "text", value: known ? "" : s.subject, placeholder: t("type_subject"), style: { marginTop: ".5rem", display: subjSel.value === "__other" ? "" : "none" } });
      subjSel.addEventListener("change", () => { other.style.display = subjSel.value === "__other" ? "" : "none"; });
      const days = new Set(s.working_days);
      const dayBox = h("div", { class: "row", role: "group", "aria-label": t("working_days") });
      const drawDays = () => dayBox.replaceChildren(...DAYS.map((d) => h("button", { class: `chip${days.has(d) ? " on" : ""}`, "aria-pressed": String(days.has(d)),
        onClick: () => { days.has(d) ? days.delete(d) : days.add(d); drawDays(); } }, dayName(d))));
      drawDays();
      v.next = async () => {
        const subject = subjSel.value === "__other" ? other.value.trim() : subjSel.value;
        if (!name.value.trim()) { name.focus(); throw new ApiError({ error: "need_name" }, 400); }
        if (!subject) { subjSel.focus(); throw new ApiError({ error: "need_subject" }, 400); }
        if (!days.size) throw new ApiError({ error: "need_days" }, 400);
        state.settings = await api.put("/api/settings", { teacher_name: name.value.trim(), school_name: school.value.trim(), subject, working_days: [...days] });
        state.boot.settings = state.settings;
      };
      return h("div", {},
        h("h1", {}, t("about_title")), h("p", { class: "lead" }, t("about_lead")),
        h("div", { class: "panel" },
          h("div", { class: "grid2" },
            h("label", { class: "field" }, h("span", { class: "label" }, t("your_name")), name),
            h("label", { class: "field" }, h("span", { class: "label" }, t("your_subject")), subjSel, other)),
          h("label", { class: "field" }, h("span", { class: "label" }, t("school_name")), school),
          h("div", {}, h("span", { class: "label" }, t("working_days")), dayBox, h("span", { class: "hint" }, t("working_days_hint")))));
    },

    async classes(v) {
      state.structure = await api.get("/api/structure");
      const picker = classPicker({ presets: state.structure.presets, existing: state.structure.rooms });
      v.next = async () => {
        if (!picker.count()) throw new ApiError({ error: "need_class" }, 400);
        state.structure = await api.post("/api/structure/build", { selection: picker.value() });
      };
      const importLink = h("button", { class: "btn ghost", onClick: () => importOldDialog(async () => show("classes")) }, icon("upload"), t("import_old_link"));
      return h("div", {},
        h("h1", {}, t("classes_title")), h("p", { class: "lead" }, t("classes_lead")),
        h("div", { class: "panel" }, picker.el), h("div", { style: { marginTop: "1rem" } }, importLink));
    },

    async timetable(v) {
      state.structure = await api.get("/api/structure");
      const [tt, settings] = [await api.get("/api/timetable"), await api.get("/api/settings")];
      const ed = timetableEditor({ timetable: tt, structure: state.structure, workingDays: settings.working_days });
      v.skippable = true;
      v.next = async () => { await api.put("/api/timetable", ed.value()); };
      return h("div", {}, h("h1", {}, t("timetable_title")), h("p", { class: "lead" }, t("timetable_lead")), h("div", { class: "panel" }, ed.el));
    },

    async calendar(v) {
      let cal = await api.get("/api/calendar");
      const fresh = !cal.trimesters.some((x) => x.start);
      if (fresh) cal = await api.get("/api/school-calendar"); // everyone at DLIS uses the same official calendar
      const ed = calendarEditor({ calendar: cal });
      v.skippable = true;
      v.next = async () => { await api.put("/api/calendar", ed.value()); };
      return h("div", {}, h("h1", {}, t("calendar_title")), h("p", { class: "lead" }, t("calendar_lead")),
        fresh ? h("div", { class: "banner ok" }, icon("check"), h("div", {}, t("school_cal_loaded"))) : null, h("div", { class: "panel" }, ed.el));
    },

    async done(v) {
      await api.post("/api/setup/finish");
      v.hideBack = true;
      return h("div", {},
        h("h1", {}, t("done_title")), h("p", { class: "lead" }, t("done_lead")),
        h("div", { class: "row" },
          h("button", { class: "btn primary big", onClick: () => { location.hash = "#/today"; onFinished(); } }, t("go_to_today")),
          h("button", { class: "btn big", onClick: () => { location.hash = "#/classes"; onFinished(); } }, t("add_students_now"))));
    },
  };

  show(ORDER[idx]);
}
