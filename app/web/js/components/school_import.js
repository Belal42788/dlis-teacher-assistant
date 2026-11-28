// Classes > "Import the whole school": one file, every row says the class. A preview first (which classes, how many students),
// then the import.
import { h, icon, toast, modal, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

export function schoolImportDialog(done) {
  let source = null, preview = null;
  const out = h("div", {});
  const text = h("textarea", { rows: 5, placeholder: t("si_paste_ph"), "aria-label": t("si_paste") });
  const file = h("input", { type: "file", accept: ".xlsx,.csv,.txt,.xls", hidden: true });
  const addClasses = h("input", { type: "checkbox", checked: true }), replace = h("input", { type: "checkbox", checked: true });
  let importBtn;

  async function look() {
    if (!source) return;
    const r = await guarded(() => api.post("/api/students/import-all/preview", source));
    preview = r || null;
    if (importBtn) importBtn.disabled = !preview;
    if (!preview) return out.replaceChildren();
    out.replaceChildren(
      h("p", {}, h("b", {}, t("si_found", { n: preview.students, c: preview.classes.length }))),
      h("table", { class: "si-table" }, h("thead", {}, h("tr", {}, h("th", {}, t("si_class")), h("th", {}, t("si_count")), h("th", {}, t("si_english")), h("th", {}, ""))),
        h("tbody", {}, preview.classes.map((c) => h("tr", {}, h("td", {}, c.name), h("td", {}, c.count), h("td", {}, c.english || "—"), h("td", { class: "small" }, c.in_app ? t("si_have") : t("si_new")))))),
      preview.unknown.length ? h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("si_unknown"), h("div", { class: "small dir-ltr" }, preview.unknown.slice(0, 8).join(" · ")))) : null);
  }
  file.addEventListener("change", async () => {
    const f = file.files[0]; file.value = ""; if (!f) return;
    source = { filename: f.name, data_b64: await readFileB64(f) }; text.value = ""; look();
  });
  text.addEventListener("input", () => { source = text.value.trim() ? { text: text.value } : null; if (!source) { preview = null; out.replaceChildren(); } });
  text.addEventListener("change", look);

  modal({
    title: t("si_title"), wide: true,
    body: h("div", {},
      h("p", { class: "muted" }, t("si_lead")),
      h("div", { class: "row" }, h("button", { class: "btn", onClick: () => file.click() }, icon("upload"), t("si_choose")), file, h("span", { class: "muted small" }, t("si_or"))),
      text, out,
      h("label", { class: "row small" }, addClasses, t("si_add_classes")), h("label", { class: "row small" }, replace, t("si_replace"))),
    actions: [
      { label: t("cancel") },
      { label: t("si_import"), kind: "primary", onClick: async (_e, close) => {
        if (!source) { toast(t("si_need_file"), "error"); return false; }
        const r = await guarded(() => api.post("/api/students/import-all", { ...source, add_classes: addClasses.checked, replace: replace.checked }));
        if (!r) return false;
        toast(t("si_done", { n: r.students, c: r.rooms })); done && done(r);
      } }],
  });
  const btn = [...document.querySelectorAll(".modal footer button")].find((b) => b.textContent === t("si_import"));
  importBtn = btn || null;
}
