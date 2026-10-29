import { h, icon, toast, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, setLang, getLang } from "../i18n.js";
import { state } from "../state.js";
import { DAYS, dayName, subjectLabel } from "../labels.js";
import { pickFolder } from "../components/folder_picker.js";
import { segTabs } from "../components/seg.js";
import { aiPanel } from "../components/ai_panel.js";
import { reminderPanel } from "../components/reminder_panel.js";

// Shared with the first-run guide.
export async function importOldDialog(done) {
  const folder = await pickFolder({ title: t("import_pick_folder"), confirmLabel: t("check_this_folder"), allowNew: false });
  if (!folder) return;
  const preview = await guarded(() => api.post("/api/import/legacy", { path: folder, dry_run: true }));
  if (!preview) return;
  modal({
    title: t("import_old_title"),
    body: h("div", {}, h("p", {}, t("import_found")),
      h("ul", {}, [`import_stat_rooms|${preview.rooms}`, `import_stat_grades|${preview.grades}`, `import_stat_students|${preview.students}`, `import_stat_dups|${preview.duplicates_removed}`]
        .map((s) => { const [k, n] = s.split("|"); return h("li", {}, t(k, { n })); })),
      h("p", { class: "muted small" }, t("import_safe"))),
    actions: [{ label: t("cancel") }, { label: t("import_now"), kind: "primary", onClick: async () => {
      const r = await guarded(() => api.post("/api/import/legacy", { path: folder }));
      if (!r) return false;
      toast(t("import_done")); done && done();
    } }],
  });
}

export async function renderSettings(root, { reloadApp }) {
  const [settings, boot] = await Promise.all([api.get("/api/settings"), api.get("/api/bootstrap")]);
  state.settings = settings; state.boot = boot;
  const subjects = boot.subjects;
  const known = subjects.some((x) => x.en === settings.subject);

  const name = h("input", { type: "text", value: settings.teacher_name });
  const school = h("input", { type: "text", value: settings.school_name });
  const subjSel = h("select", {}, h("option", { value: "" }, t("choose_subject")),
    subjects.map((x) => h("option", { value: x.en }, subjectLabel(x.en, subjects))), h("option", { value: "__other" }, t("other_subject")));
  subjSel.value = settings.subject ? (known ? settings.subject : "__other") : "";
  const other = h("input", { type: "text", value: known ? "" : settings.subject, placeholder: t("type_subject"), style: { marginTop: ".5rem", display: subjSel.value === "__other" ? "" : "none" } });
  subjSel.addEventListener("change", () => { other.style.display = subjSel.value === "__other" ? "" : "none"; });
  const days = new Set(settings.working_days);
  const dayBox = h("div", { class: "row" });
  const drawDays = () => dayBox.replaceChildren(...DAYS.map((d) => h("button", { class: `chip${days.has(d) ? " on" : ""}`, "aria-pressed": String(days.has(d)), onClick: () => { days.has(d) ? days.delete(d) : days.add(d); drawDays(); } }, dayName(d))));
  drawDays();

  const backupOut = h("div", { class: "small", style: { marginTop: ".6rem" } });

  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_settings")))),

    ...segTabs("settings", [
    ["me", t("about_you"), h("div", {}, h("div", { class: "panel" }, h("h3", {}, t("about_you")),
      h("div", { class: "grid2" },
        h("label", { class: "field" }, h("span", { class: "label" }, t("your_name")), name),
        h("label", { class: "field" }, h("span", { class: "label" }, t("your_subject")), subjSel, other)),
      h("label", { class: "field" }, h("span", { class: "label" }, t("school_name")), school),
      h("div", { style: { marginBottom: "1rem" } }, h("span", { class: "label" }, t("working_days")), dayBox),
      h("button", { class: "btn primary", onClick: async () => {
        const subject = subjSel.value === "__other" ? other.value.trim() : subjSel.value;
        if (!days.size) return toast(t("err_need_days"), "error");
        const r = await guarded(() => api.put("/api/settings", { teacher_name: name.value.trim(), school_name: school.value.trim(), subject, working_days: [...days] }));
        if (r) { state.settings = r; toast(t("saved")); reloadApp(false); }
      } }, t("save"))),

    h("div", { class: "panel" }, h("h3", {}, t("language")),
      h("div", { class: "row" }, [["ar", "العربية"], ["en", "English"]].map(([code, label]) =>
        h("button", { class: `chip${getLang() === code ? " on" : ""}`, "aria-pressed": String(getLang() === code), lang: code, onClick: async () => {
          await api.put("/api/prefs", { language: code }); setLang(code); state.boot.language = code; reloadApp(false);
        } }, label)))))],

    ["data", t("data_folder"), h("div", { class: "panel" }, h("h3", {}, t("data_folder")),
      h("p", { class: "muted" }, t("data_folder_hint")),
      h("div", { class: "folder-box", style: { marginBottom: ".9rem" } }, boot.data_folder),
      boot.conflicts.length ? h("div", { class: "banner warn" }, icon("warn"), h("div", {}, h("b", {}, t("conflicts_found", { n: boot.conflicts.length })), h("div", { class: "small" }, t("conflicts_help")),
        h("ul", { class: "small dir-ltr" }, boot.conflicts.slice(0, 5).map((c) => h("li", {}, c))))) : null,
      h("div", { class: "row" },
        h("button", { class: "btn", onClick: async () => {
          const p = await pickFolder({ title: t("choose_folder"), start: boot.data_folder });
          if (!p || p === boot.data_folder) return;
          const r = await guarded(() => api.post("/api/data-folder", { path: p }));
          if (r) { state.boot = r; toast(t("folder_changed")); reloadApp(true); }
        } }, icon("folder"), t("change_folder")),
        h("button", { class: "btn", onClick: async () => {
          const r = await guarded(() => api.post("/api/backup"));
          if (r) backupOut.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", {}, t("backup_done"), h("div", { class: "dir-ltr small" }, `Exports/${r.name}`))));
        } }, icon("download"), t("backup_now")),
        h("button", { class: "btn", onClick: () => importOldDialog(() => reloadApp(false)) }, icon("upload"), t("import_old_link"))),
      backupOut,
      h("h3", { style: { marginTop: "1.4rem" } }, t("df_title")), h("p", { class: "muted" }, t("df_lead")),
      h("ul", { class: "df-list" }, ["docs", "slides", "sheets", "students", "data", "backup"].map((k) => h("li", {}, h("b", {}, t(`df_${k}_h`)), h("div", { class: "small muted" }, t(`df_${k}`))))),
      h("p", { class: "small" }, t("df_benefit")))],

    ["rem", t("rem_title"), reminderPanel()],

    ["ai", t("ai_title"), aiPanel()]]),

    h("div", { class: "about" }, h("img", { src: "/resources/logo.png", alt: "DLIS" }), h("p", { class: "muted small" }, `${t("app_name")} · v${boot.version}`))));
}
