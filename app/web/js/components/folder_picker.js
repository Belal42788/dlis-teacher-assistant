import { h, icon, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { state } from "../state.js";

// A simple "pick a folder" window that works the same on Windows and Mac.
export async function pickFolder(opts) {
  // Inside the app window, use the computer's own folder window (Explorer / Finder). In a plain browser, use ours.
  if (state.boot?.native_dialog) try {
    const r = await api.post("/api/fs/native", { start: opts.start || "" });
    return r.path || null;
  } catch (e) { /* not available: fall through to the built-in picker */ }
  return pickFolderBuiltin(opts);
}

function pickFolderBuiltin({ title, start = "", confirmLabel, allowNew = true }) {
  return new Promise((resolve) => {
    let current = "";
    const crumb = h("div", { class: "crumb" });
    const list = h("div", { class: "folders", role: "listbox" });
    const quick = h("div", { class: "row", style: { marginBottom: ".8rem" } });
    let result = null;

    async function go(path) {
      const d = await guarded(() => api.get(`/api/fs/list?path=${encodeURIComponent(path || "")}`));
      if (!d) return;
      current = d.path;
      crumb.textContent = d.path;
      list.replaceChildren(
        d.parent ? h("button", { onClick: () => go(d.parent) }, icon("up"), t("folder_up")) : null,
        d.dirs.length ? d.dirs.map((n) => h("button", { onClick: () => go(joinPath(d.path, n)) }, icon("folder"), n))
          : h("div", { class: "muted", style: { padding: "1rem" } }, t("folder_empty")));
      quick.replaceChildren(d.shortcuts.map((s) =>
        h("button", { class: "chip", onClick: () => go(s.path) }, icon("folder"), s.kind ? t(`sc_${s.kind}`) : s.label)));
    }

    function joinPath(base, name) {
      const sep = base.includes("\\") ? "\\" : "/";
      return base.endsWith(sep) ? base + name : base + sep + name;
    }

    const body = h("div", {}, quick, crumb, list,
      allowNew ? h("div", { class: "row", style: { marginTop: ".9rem" } },
        h("input", { type: "text", id: "newfolder", placeholder: t("new_folder_name"), "aria-label": t("new_folder_name"), class: "grow" }),
        h("button", { class: "btn", onClick: async () => {
          const name = body.querySelector("#newfolder").value.trim();
          if (!name) return;
          const d = await guarded(() => api.post("/api/fs/mkdir", { parent: current, name }));
          if (d) { body.querySelector("#newfolder").value = ""; go(d.path); }
        } }, icon("plus"), t("new_folder"))) : null);

    modal({
      title, body, wide: true,
      onClose: () => resolve(result),
      actions: [
        { label: t("cancel") },
        { label: confirmLabel || t("use_this_folder"), kind: "primary", onClick: () => { result = current; } },
      ],
    });
    go(start);
  });
}
