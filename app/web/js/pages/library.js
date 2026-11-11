import { h, icon, confirmBox, toast, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { hubTabs } from "../components/hubtabs.js";
import { t } from "../i18n.js";
import { emptyState } from "../components/empty.js";
import { roomLabel, fmtDate, fmtShort, triName } from "../labels.js";
import { dateField } from "../components/date3.js";
import { sourceTools } from "../components/source_ui.js";

// My files: one page, split by weeks. A file sits in the week(s) it is taught (the same file can be in two weeks, each with its own note),
// and on each one the teacher ticks «for students» and writes a note for them: what is in the file, how far we got.
// A file can also be an AI source (it is read once); that is a second switch on the same row.
export async function renderLibrary(root) {
  const [structure, ov] = await Promise.all([api.get("/api/structure"), api.get("/api/overview")]);
  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  const wanted = new URLSearchParams((location.hash.split("?")[1] || "")).get("share") || "";
  let filter = "all", openForm = wanted;
  const openGroups = new Set(["cur", "none"]);
  const KINDS = ["all", "presentation", "quiz", "revision", "book", "link", "other", "source"];
  const kindLabel = (k) => (k === "all" ? t("lb_all") : k === "source" ? t("lf_only_src") : t(`pb_k_${k}`));
  const canBeSource = (f) => /\.(pdf|docx|pptx)$/i.test(f.name) && !f.private;
  const tools = sourceTools({ ai, reload: () => load() });
  // a link (a video, a playlist, a site) joins the list like a file
  const linkTitle = h("input", { type: "text", maxlength: 120, placeholder: t("lf_link_title_ph"), "aria-label": t("lf_link_title_ph"), style: { flex: "1", minWidth: "10em" } });
  const linkUrl = h("input", { type: "url", dir: "ltr", placeholder: "https://…", "aria-label": t("src_url"), style: { flex: "2", minWidth: "12em" } });
  const adder = tools.adder(h("div", { class: "row", style: { marginTop: ".6rem" } }, linkTitle, linkUrl,
    h("button", { class: "btn", onClick: () => { if (!linkUrl.value.trim()) { linkUrl.focus(); return; } return guarded(async () => { const r = await api.post("/api/library/link", { title: linkTitle.value, url: linkUrl.value }); linkTitle.value = ""; linkUrl.value = ""; adder.open = false; toast(t("saved")); await load(); }); } }, icon("link"), t("lf_link_add"))));

  // the weeks of the year, for the pickers and the group titles
  const weeks = [];   // { t, w, start, end }
  for (const tri of ov.trimesters || []) for (const w of tri.weeks || []) weeks.push({ t: tri.index, w: w.number, start: w.start, end: w.end });
  const pos = ov.position && ov.position.state === "in_term" ? ov.position : null;
  const wkKey = (tt, w) => (tt === null || tt === undefined || w === null || w === undefined ? "none" : `${tt}-${w}`);
  const curKey = pos ? wkKey(pos.trimester, pos.week) : "";
  const wkLabel = (tt, w) => `${triName("T" + (tt + 1))} · ${t("cal_week_n", { n: w })}`;
  const weekOptions = (sel) => [h("option", { value: "none", selected: sel === "none" }, t("lf_no_week")),
    ...weeks.map((x) => h("option", { value: wkKey(x.t, x.w), selected: sel === wkKey(x.t, x.w) }, wkLabel(x.t, x.w)))];
  const parseKey = (v) => (v === "none" ? { t: null, w: null } : { t: +v.split("-")[0], w: +v.split("-")[1] });

  async function load() {
    const [lib, pubs] = await Promise.all([api.get("/api/library"), api.get("/api/publications").catch(() => ({ connected: false }))]);
    const online = pubs.connected && ["admin", "teacher"].includes(pubs.role);
    const act = (fn) => guarded(async () => { await fn(); await load(); });
    const post = (path, body) => act(() => api.post(path, body));
    const sel = h("select", { style: { width: "auto" }, onChange: (e) => { filter = e.target.value; load(); } },
      KINDS.map((k) => h("option", { value: k, selected: k === filter }, kindLabel(k))));

    // one row per (file, week)
    const rows = [];
    for (const f of lib.items) {
      if (!(filter === "all" || f.kind === filter || (filter === "source" && f.source))) continue;
      for (const p of f.places) rows.push({ f, p, key: wkKey(p.t, p.w) });
    }
    const groups = new Map();
    for (const r of rows) (groups.get(r.key) || groups.set(r.key, []).get(r.key)).push(r);
    const order = [...groups.keys()].filter((k) => k !== "none" && k !== curKey).sort((a, b) => { const [ta, wa] = a.split("-").map(Number), [tb, wb] = b.split("-").map(Number); return tb - ta || wb - wa; });
    if (curKey) order.unshift(curKey);
    if (groups.has("none")) order.push("none");

    function shareForm(f, p) {
      const room = h("select", {}, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
      const pub = h("input", { type: "checkbox", checked: f.kind !== "quiz" });
      const from = dateField({ label: t("pb_from") });
      return h("div", { class: "panel", style: { marginTop: ".5rem" } },
        h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("pb_class")), room),
          f.kind === "quiz" ? h("div", { class: "field" }, h("span", { class: "label" }, t("pb_from")), from) : null),
        f.kind === "quiz" ? h("p", { class: "muted small" }, t("pb_quiz_hint")) : null,
        h("label", { class: "row" }, pub, t("lb_public_now")),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onClick: () => act(async () => { await api.post("/api/library/share", { rel: f.rel, pid: p.id, class_id: room.value, public: pub.checked, visible_from: from.value || undefined, kind: f.kind }); openForm = ""; toast(t("lf_shared_now")); }) }, icon("send"), t("lb_share")),
          h("button", { class: "btn ghost", onClick: () => { openForm = ""; load(); } }, t("cancel"))));
    }

    // the dialog with this file's weeks (move it, add it to another week, take it out of one)
    function weeksDialog(f0) {
      const body = h("div", {});
      const m = modal({ title: f0.name, body, actions: [{ label: t("close"), kind: "primary" }] });
      const draw = async () => {
        const cur = (await api.get("/api/library")).items.find((x) => x.rel === f0.rel);
        if (!cur) return;
        const used = new Set(cur.places.map((p) => wkKey(p.t, p.w)));
        const add = h("select", {}, weeks.filter((x) => !used.has(wkKey(x.t, x.w))).map((x) => h("option", { value: wkKey(x.t, x.w) }, wkLabel(x.t, x.w))));
        body.replaceChildren(h("p", { class: "muted small" }, t("lf_weeks_lead")),
          ...cur.places.map((p) => h("div", { class: "row", style: { marginBottom: ".4rem" } },
            h("select", { style: { flex: "1" }, onChange: async (e) => { await guarded(() => api.post("/api/library/place", { rel: cur.rel, pid: p.id, ...parseKey(e.target.value) })); await draw(); load(); } }, weekOptions(wkKey(p.t, p.w))),
            p.shared ? h("span", { class: "chip small on" }, t("lf_live")) : null,
            h("button", { class: "btn small ghost", title: t("lf_week_remove"), "aria-label": t("lf_week_remove"), disabled: cur.places.length === 1 && wkKey(p.t, p.w) === "none",
              onClick: async () => { if (p.shared && !(await confirmBox(t("lb_unshare_confirm")))) return; await guarded(() => api.post("/api/library/place/delete", { rel: cur.rel, pid: p.id })); await draw(); load(); } }, icon("trash")))),
          h("div", { class: "row", style: { marginTop: ".8rem" } }, h("b", {}, t("lf_week_add")), add,
            h("button", { class: "btn small", disabled: !add.options.length, onClick: async () => { await guarded(() => api.post("/api/library/place/add", { rel: cur.rel, ...parseKey(add.value) })); await draw(); load(); } }, icon("plus"), t("lf_week_add_btn"))));
      };
      draw();
      return m;
    }

    // a link becomes an AI source: a web page is read from the address; a video needs its text pasted
    function linkSourceDialog(f) {
      const text = h("textarea", { rows: 5, style: { width: "100%" }, placeholder: t("src_yt_ph"), "aria-label": t("src_yt") });
      modal({ title: f.name, body: h("div", {}, h("p", { class: "muted small" }, t("lf_link_src_lead")), text),
        actions: [{ label: t("cancel") }, { label: t("lf_link_src_go"), kind: "primary", onClick: () => tools.run(async () => {
          const r = await api.post("/api/library/source", { rel: f.rel, on: true, transcript: text.value });
          const s = r.items.find((x) => x.rel === f.rel)?.source; await load(); if (s) await tools.process(s.id); }) }] });
    }

    const row = ({ f, p }) => {
      const note = h("input", { type: "text", maxlength: 300, class: "file-note", value: p.note || "", placeholder: t("lf_note_ph"), "aria-label": t("lf_note_ph"),
        onChange: () => guarded(async () => { await api.post("/api/library/place", { rel: f.rel, pid: p.id, note: note.value }); p.note = note.value; toast(t("lf_note_saved")); }) });
      const shareBox = h("label", { class: `share-tick ${p.shared ? "on" : ""}`, title: online ? "" : t("lb_offline") },
        h("input", { type: "checkbox", checked: !!p.shared, disabled: !online || f.private,
          onChange: async (e) => {
            if (p.shared) { e.target.checked = true; if (await confirmBox(t("lb_unshare_confirm"))) post("/api/library/unshare", { rel: f.rel, pid: p.id }); return; }
            e.target.checked = false;
            if (structure.rooms.length === 1 && f.kind !== "quiz") post("/api/library/share", { rel: f.rel, pid: p.id, class_id: structure.rooms[0].id, public: true, kind: f.kind }).then(() => toast(t("lf_shared_now")));
            else { openForm = f.rel + "|" + p.id; load(); }
          } }), t("lf_for_students"));
      const mine = openForm === f.rel + "|" + p.id || (wanted && openForm === wanted && !p.shared && f.places[0] === p);
      return h("div", { class: "pub-row file-row" },
        h("div", { class: "file-main" }, h("span", { class: `file-ico ext-${f.kind === "link" ? "link" : (f.name || "").split(".").pop().toLowerCase()}` }, icon(f.kind === "link" ? "link" : "file")),
          h("div", { style: { minWidth: 0 } }, h("b", {}, f.name), h("div", { class: "muted small" }, `${f.kind === "link" ? f.url.replace(/^https?:\/\/(www\.)?/, "").slice(0, 40) : f.kind === "book" ? t("pb_k_book") : f.folder} · ${fmtDate(new Date(f.mtime * 1000).toISOString().slice(0, 10), { day: "numeric", month: "short" })}${f.source ? " · " + t("src_meta", { pages: f.source.pages, date: f.source.added }).split(" · ")[0] + (f.source.topic ? " · " + f.source.topic : "") : ""}`))),
        h("div", { class: "file-chips" },
          f.source ? h("span", { class: "chip small on" }, t("lf_src")) : null,
          f.private ? h("span", { class: "chip small" }, t("lb_private")) : null,
          p.shared ? h("span", { class: `chip small ${p.shared.public ? "on" : ""}` }, p.shared.public ? t("lf_live") : t("lf_wait")) : null),
        h("div", { class: "file-acts" },
          f.private ? null : shareBox,
          p.shared && !p.shared.public ? h("button", { class: "btn small primary", onClick: () => post("/api/library/public", { rel: f.rel, pid: p.id, public: true }) }, t("pb_approve")) : null,
          p.shared && p.shared.public ? h("button", { class: "btn small ghost", onClick: () => post("/api/library/public", { rel: f.rel, pid: p.id, public: false }) }, t("pb_unapprove")) : null,
          h("button", { class: "btn small", onClick: () => weeksDialog(f) }, icon("calendar"), t("lf_weeks_btn")),
          f.kind === "link" ? h("a", { class: "btn small", href: f.url, target: "_blank", rel: "noopener noreferrer" }, icon("link"), t("lf_open_link")) : h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel })) }, icon("file"), t("d_open_file")),
          f.kind === "link" ? h("button", { class: "btn small ghost", title: t("lf_link_del"), "aria-label": t("lf_link_del"), onClick: async () => { if (await confirmBox(t("lf_link_del_confirm"))) post("/api/library/link/delete", { rel: f.rel }); } }, icon("trash"))
            : h("button", { class: "btn small ghost", title: t("d_open_folder"), "aria-label": t("d_open_folder"), onClick: () => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel, folder: true })) }, icon("folder")),
          f.source && f.source_locked ? h("span", { class: "muted small" }, t("lf_src_auto"))
            : f.source ? h("button", { class: "btn small ghost", onClick: () => post("/api/library/source", { rel: f.rel, on: false }) }, t("lf_src_drop"))
              : f.kind === "link" ? h("button", { class: "btn small", onClick: () => linkSourceDialog(f) }, icon("spark"), t("lf_src_make"))
              : canBeSource(f) ? h("button", { class: "btn small", onClick: () => tools.run(async () => { const r = await api.post("/api/library/source", { rel: f.rel, on: true }); const s = r.items.find((x) => x.rel === f.rel)?.source; await load(); if (s) await tools.process(s.id); }) }, icon("spark"), t("lf_src_make")) : null,
          f.source ? tools.buttons(f.source) : null),
        f.private ? null : h("div", { class: "file-note-row" }, note),
        f.source ? h("div", { class: "file-more" }, tools.details(f.source)) : null,
        mine && !p.shared ? h("div", { class: "file-form" }, shareForm(f, p)) : null);
    };
    // a source with no file behind it (a web page)
    const orphan = (s) => h("div", { class: "pub-row file-row" },
      h("div", { class: "file-main" }, h("span", { class: "file-ico ext-link" }, icon("link")),
        h("div", { style: { minWidth: 0 } }, h("b", {}, s.name), h("div", { class: "muted small" }, `${t("lf_src_only")} · ${t("src_meta", { pages: s.pages, date: s.added })}`))),
      h("div", { class: "file-chips" }, h("span", { class: "chip small on" }, t("lf_src"))),
      h("div", { class: "file-acts" }, tools.buttons(s), tools.removeButton(s)),
      h("div", { class: "file-more" }, tools.details(s)));

    const group = (key) => {
      const list = (groups.get(key) || []).sort((a, b) => b.f.mtime - a.f.mtime);
      const [tt, w] = key === "none" ? [null, null] : key.split("-").map(Number);
      const span = weeks.find((x) => x.t === tt && x.w === w);
      const title = key === "none" ? t("lf_no_week") : wkLabel(tt, w);
      const gid = key === curKey ? "cur" : key;
      return h("details", { class: `wk-group${key === curKey ? " cur" : ""}`, open: openGroups.has(gid) || (key === curKey && !openGroups.has("closed-cur")),
        onToggle: (e) => { if (e.target.open) openGroups.add(gid); else { openGroups.delete(gid); if (gid === "cur") openGroups.add("closed-cur"); } } },
        h("summary", {}, h("b", {}, title), key === curKey ? h("span", { class: "chip small on" }, t("lf_week_cur")) : null,
          span ? h("span", { class: "muted small" }, `${fmtShort(span.start)} – ${fmtShort(span.end)}`) : null,
          h("span", { class: "muted small grow", style: { textAlign: "end" } }, t("lf_n_files", { n: list.length }))),
        list.length ? list.map(row) : h("p", { class: "muted small", style: { padding: ".4rem .8rem" } }, t("lf_week_empty")),
        key === "none" && list.length ? h("p", { class: "muted small", style: { padding: ".2rem .8rem" } }, t("lf_no_week_hint")) : null);
    };
    const orphans = filter === "all" || filter === "source" ? lib.orphans : [];

    root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "library"),
      h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_library")), h("p", {}, t("lb_lead")))),
      online ? null : h("div", { class: "banner info" }, icon("info"), h("div", {}, t("lb_offline"))),
      ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, t("src_need_ai"), " ", h("a", { href: "#/settings" }, t("ai_setup_link")))),
      adder, tools.status,
      h("div", { class: "row" }, h("span", { class: "label" }, t("pb_kind")), sel),
      order.length || orphans.length ? [...order.map(group), orphans.length ? h("details", { class: "wk-group", open: true }, h("summary", {}, h("b", {}, t("lf_orphans"))), orphans.map(orphan)) : null]
        : emptyState({ icon: "folder", title: t("lb_none_title"), text: t("lb_none"), action: { label: t("nav_docs"), icon: "file", onClick: () => { location.hash = "#/docs"; } } })));
    if (wanted && openForm.startsWith(wanted)) document.querySelector(".file-form")?.scrollIntoView({ block: "center" });
  }
  await load();
}
