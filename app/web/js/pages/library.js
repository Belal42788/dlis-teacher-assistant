import { h, icon, confirmBox, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { hubTabs } from "../components/hubtabs.js";
import { t } from "../i18n.js";
import { roomLabel, fmtDate } from "../labels.js";
import { dateField } from "../components/date3.js";

// My files: everything the program made, in one place. From here the teacher decides what students can see.
export async function renderLibrary(root) {
  const structure = await api.get("/api/structure");
  const wanted = new URLSearchParams((location.hash.split("?")[1] || "")).get("share") || "";
  let filter = "all", openForm = wanted;
  const KINDS = ["all", "presentation", "quiz", "revision", "other"];

  async function load() {
    const [lib, pubs] = await Promise.all([api.get("/api/library"), api.get("/api/publications").catch(() => ({ connected: false }))]);
    const online = pubs.connected && ["admin", "teacher"].includes(pubs.role);
    const list = lib.items.filter((x) => filter === "all" || x.kind === filter);
    const sel = h("select", { style: { width: "auto" }, onChange: (e) => { filter = e.target.value; load(); } },
      KINDS.map((k) => h("option", { value: k, selected: k === filter }, k === "all" ? t("lb_all") : t(`pb_k_${k}`))));
    const act = (fn) => guarded(async () => { await fn(); await load(); });
    const post = (path, body) => act(() => api.post(path, body));

    function shareForm(f) {
      const room = h("select", {}, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
      const pub = h("input", { type: "checkbox", checked: f.kind !== "quiz" });
      const from = dateField({ label: t("pb_from") });
      return h("div", { class: "panel", style: { marginTop: ".5rem" } },
        h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("pb_class")), room),
          f.kind === "quiz" ? h("div", { class: "field" }, h("span", { class: "label" }, t("pb_from")), from) : null),
        f.kind === "quiz" ? h("p", { class: "muted small" }, t("pb_quiz_hint")) : null,
        h("label", { class: "row" }, pub, t("lb_public_now")),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onClick: () => act(async () => { await api.post("/api/library/share", { rel: f.rel, class_id: room.value, public: pub.checked, visible_from: from.value || undefined, kind: f.kind }); openForm = ""; toast(t("lb_shared")); }) }, icon("send"), t("lb_share")),
          h("button", { class: "btn ghost", onClick: () => { openForm = ""; load(); } }, t("cancel"))));
    }
    const row = (f) => h("div", { class: "pub-row file-row" },
      h("div", { class: "file-main" }, h("span", { class: `file-ico ext-${(f.name || "").split(".").pop().toLowerCase()}` }, icon("file")),
        h("div", { style: { minWidth: 0 } }, h("b", {}, f.name), h("div", { class: "muted small" }, `${f.folder} · ${fmtDate(new Date(f.mtime * 1000).toISOString().slice(0, 10), { day: "numeric", month: "short" })}`))),
      f.shared ? h("span", { class: `chip small ${f.shared.public ? "on" : ""}` }, f.shared.public ? t("pb_live") : t("pb_wait")) : f.private ? h("span", { class: "chip small" }, t("lb_private")) : null,
      h("div", { class: "file-acts" },
        h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel })) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small ghost", title: t("d_open_folder"), "aria-label": t("d_open_folder"), onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel, folder: true })) }, icon("folder")),
        f.shared ? [
          h("button", { class: "btn small", onClick: () => post("/api/library/public", { rel: f.rel, public: !f.shared.public }) }, f.shared.public ? t("pb_unapprove") : t("pb_approve")),
          h("button", { class: "btn small ghost", onClick: async () => { if (await confirmBox(t("lb_unshare_confirm"))) post("/api/library/unshare", { rel: f.rel }); } }, icon("trash"), t("lb_unshare"))]
          : online && !f.private ? h("button", { class: "btn small primary", onClick: () => { openForm = f.rel; load(); } }, icon("send"), t("lb_share")) : null),
      openForm === f.rel && !f.shared ? h("div", { class: "file-form" }, shareForm(f)) : null);

    root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "library"),
      h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_library")), h("p", {}, t("lb_lead")))),
      online ? null : h("div", { class: "banner info" }, icon("info"), h("div", {}, t("lb_offline"))),
      h("div", { class: "row" }, h("span", { class: "label" }, t("pb_kind")), sel),
      list.length ? list.map(row) : h("p", { class: "muted" }, t("lb_none"))));
    if (wanted && openForm === wanted) document.querySelector(".pub-row .panel")?.scrollIntoView({ block: "center" });
  }
  await load();
}
