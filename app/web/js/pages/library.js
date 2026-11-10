import { h, icon, confirmBox, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { hubTabs } from "../components/hubtabs.js";
import { t } from "../i18n.js";
import { emptyState } from "../components/empty.js";
import { roomLabel, fmtDate } from "../labels.js";
import { dateField } from "../components/date3.js";
import { sourceTools } from "../components/source_ui.js";

// My files: every file in one list (what the program made, and the books and slides the teacher added).
// On each file the teacher chooses two things: is it a source for the AI, and do students see it.
export async function renderLibrary(root) {
  const structure = await api.get("/api/structure");
  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  const wanted = new URLSearchParams((location.hash.split("?")[1] || "")).get("share") || "";
  let filter = "all", openForm = wanted;
  const KINDS = ["all", "presentation", "quiz", "revision", "book", "other", "source"];
  const kindLabel = (k) => (k === "all" ? t("lb_all") : k === "source" ? t("lf_only_src") : t(`pb_k_${k}`));
  const canBeSource = (f) => /\.(pdf|docx|pptx)$/i.test(f.name) && !f.private;
  const tools = sourceTools({ ai, reload: () => load() });
  const adder = tools.adder();

  async function load() {
    const [lib, pubs] = await Promise.all([api.get("/api/library"), api.get("/api/publications").catch(() => ({ connected: false }))]);
    const online = pubs.connected && ["admin", "teacher"].includes(pubs.role);
    const list = lib.items.filter((x) => filter === "all" || x.kind === filter || (filter === "source" && x.source));
    const orphans = filter === "all" || filter === "source" ? lib.orphans : [];
    const sel = h("select", { style: { width: "auto" }, onChange: (e) => { filter = e.target.value; load(); } },
      KINDS.map((k) => h("option", { value: k, selected: k === filter }, kindLabel(k))));
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
        h("div", { style: { minWidth: 0 } }, h("b", {}, f.name), h("div", { class: "muted small" }, `${f.kind === "book" ? t("pb_k_book") : f.folder} · ${fmtDate(new Date(f.mtime * 1000).toISOString().slice(0, 10), { day: "numeric", month: "short" })}${f.source ? " · " + t("src_meta", { pages: f.source.pages, date: f.source.added }).split(" · ")[0] + (f.source.topic ? " · " + f.source.topic : "") : ""}`))),
      h("div", { class: "file-chips" },
        f.source ? h("span", { class: "chip small on" }, t("lf_src")) : null,
        f.shared ? h("span", { class: `chip small ${f.shared.public ? "on" : ""}` }, f.shared.public ? t("pb_live") : t("pb_wait")) : f.private ? h("span", { class: "chip small" }, t("lb_private")) : null),
      h("div", { class: "file-acts" },
        h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel })) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small ghost", title: t("d_open_folder"), "aria-label": t("d_open_folder"), onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel, folder: true })) }, icon("folder")),
        f.source && f.source_locked ? h("span", { class: "muted small" }, t("lf_src_auto"))
          : f.source ? h("button", { class: "btn small ghost", onClick: () => post("/api/library/source", { rel: f.rel, on: false }) }, t("lf_src_drop"))
            : canBeSource(f) ? h("button", { class: "btn small", onClick: () => tools.run(async () => { const r = await api.post("/api/library/source", { rel: f.rel, on: true }); const s = r.items.find((x) => x.rel === f.rel)?.source; await load(); if (s) await tools.process(s.id); }) }, icon("spark"), t("lf_src_make")) : null,
        f.shared ? [
          h("button", { class: "btn small", onClick: () => post("/api/library/public", { rel: f.rel, public: !f.shared.public }) }, f.shared.public ? t("pb_unapprove") : t("pb_approve")),
          h("button", { class: "btn small ghost", onClick: async () => { if (await confirmBox(t("lb_unshare_confirm"))) post("/api/library/unshare", { rel: f.rel }); } }, icon("trash"), t("lb_unshare"))]
          : online && !f.private ? h("button", { class: "btn small primary", onClick: () => { openForm = f.rel; load(); } }, icon("send"), t("lb_share")) : null,
        f.source ? tools.buttons(f.source) : null),
      f.source ? h("div", { class: "file-more" }, tools.details(f.source)) : null,
      openForm === f.rel && !f.shared ? h("div", { class: "file-form" }, shareForm(f)) : null);
    // a source with no file behind it (a web page)
    const orphan = (s) => h("div", { class: "pub-row file-row" },
      h("div", { class: "file-main" }, h("span", { class: "file-ico ext-link" }, icon("link")),
        h("div", { style: { minWidth: 0 } }, h("b", {}, s.name), h("div", { class: "muted small" }, `${t("lf_src_only")} · ${t("src_meta", { pages: s.pages, date: s.added })}`))),
      h("div", { class: "file-chips" }, h("span", { class: "chip small on" }, t("lf_src"))),
      h("div", { class: "file-acts" }, tools.buttons(s), tools.removeButton(s)),
      h("div", { class: "file-more" }, tools.details(s)));

    root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "library"),
      h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_library")), h("p", {}, t("lb_lead")))),
      online ? null : h("div", { class: "banner info" }, icon("info"), h("div", {}, t("lb_offline"))),
      ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, t("src_need_ai"), " ", h("a", { href: "#/settings" }, t("ai_setup_link")))),
      adder, tools.status,
      h("div", { class: "row" }, h("span", { class: "label" }, t("pb_kind")), sel),
      list.length || orphans.length ? [...list.map(row), ...orphans.map(orphan)] : emptyState({ icon: "folder", title: t("lb_none_title"), text: t("lb_none"), action: { label: t("nav_docs"), icon: "file", onClick: () => { location.hash = "#/docs"; } } })));
    if (wanted && openForm === wanted) document.querySelector(".pub-row .panel")?.scrollIntoView({ block: "center" });
  }
  await load();
}
