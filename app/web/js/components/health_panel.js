// Settings > App health: how the app and the data folder are doing, the backups that exist (with a restore button), the last errors.
import { h, icon, toast, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";

const when = (iso) => new Date(iso).toLocaleString(getLang() === "ar" ? "ar-EG" : "en-GB", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
const mb = (n) => (n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${n} MB`);

// A short text with no student names, for the teacher to paste to IT or to Claude.
function report(d) {
  return [`DLIS Teacher Assistant ${d.app_version} (${d.platform})`, `Data version ${d.data_version} of ${d.latest_data_version}${d.locked ? ` — LOCKED (${d.locked})` : ""}`,
    `${d.rooms} classes, ${d.students} students, ${d.files} files, ${d.folder_mb} MB, ${d.free_mb ?? "?"} MB free`,
    `Last weekly backup: ${d.last_auto_backup || "never"}`, d.problems.length ? `Damaged files: ${d.problems.map((p) => p.file).join(", ")}` : "Damaged files: none",
    "Last errors:", ...(d.errors.length ? d.errors : ["none"])].join("\n");
}

export function healthPanel({ reloadApp }) {
  const box = h("div", {});
  const load = async () => {
    const d = await guarded(() => api.get("/api/health"));
    if (d) draw(d);
  };
  const restore = async (b) => {
    const ok = await confirmBox(t("hl_restore_q", { when: when(b.when) }), { okLabel: t("hl_restore_go"), danger: false });
    if (!ok) return;
    const r = await guarded(() => api.post("/api/health/restore", { id: b.id }));
    if (r) { toast(t("hl_restore_done", { n: r.restored })); reloadApp(false); }
  };
  function draw(d) {
    const low = d.free_mb !== null && d.free_mb < 500;
    const bad = d.locked || d.problems.length || low;
    const row = (k, v) => h("div", { class: "hl-row" }, h("span", { class: "muted" }, k), h("b", { }, v));
    box.replaceChildren(
      h("div", { class: "panel" }, h("h3", {}, t("hl_title")), h("p", { class: "muted" }, t("hl_lead")),
        h("div", { class: `banner ${bad ? "warn" : "ok"}` }, icon(bad ? "warn" : "check"),
          h("div", {}, d.locked ? t("hl_locked") : d.problems.length ? t("hl_problems", { n: d.problems.length }) : low ? t("hl_low_space") : t("hl_ok"))),
        h("div", { class: "hl-grid" },
          row(t("hl_version"), `v${d.app_version}`), row(t("hl_data_version"), `${d.data_version}`),
          row(t("hl_counts"), t("hl_counts_v", { c: d.rooms, s: d.students })), row(t("hl_size"), mb(d.folder_mb)), row(t("hl_files"), String(d.files)),
          row(t("hl_free"), d.free_mb === null ? "—" : mb(d.free_mb)), row(t("hl_last_backup"), d.last_auto_backup ? when(d.last_auto_backup) : t("hl_never"))),
        h("div", { class: "folder-box dir-ltr small", style: { marginTop: ".7rem" } }, d.data_folder),
        h("div", { class: "row", style: { marginTop: ".8rem" } },
          h("button", { class: "btn small", onClick: async () => { try { await navigator.clipboard.writeText(report(d)); toast(t("hl_copied")); } catch { toast(t("hl_copy_failed"), "error"); } } }, icon("file"), t("hl_copy")),
          h("button", { class: "btn small ghost", onClick: load }, t("hl_refresh")))),
      h("div", { class: "panel" }, h("h3", {}, t("hl_backups")), h("p", { class: "muted small" }, t("hl_backups_hint")),
        d.backups.length ? h("ul", { class: "hl-list" }, d.backups.map((b) => h("li", {},
          h("div", { class: "grow" }, h("b", {}, when(b.when)), h("div", { class: "small muted" }, `${t(`hl_kind_${b.kind}`)} · ${(b.size / 1024).toFixed(0)} KB${b.usable ? "" : ` · ${t("hl_empty")}`}`)),
          h("button", { class: "btn small", disabled: !!d.locked || !b.usable, onClick: () => restore(b) }, t("hl_restore"))))) : h("p", { class: "muted" }, t("hl_backups_none"))),
      h("div", { class: "panel" }, h("h3", {}, t("hl_errors")),
        d.errors.length ? h("pre", { class: "hl-log dir-ltr small" }, d.errors.join("\n")) : h("p", { class: "muted" }, t("hl_no_errors"))));
  }
  box.append(h("div", { class: "skel-bar", style: { width: "60%", height: "1.2rem" } }));
  load();
  return box;
}
