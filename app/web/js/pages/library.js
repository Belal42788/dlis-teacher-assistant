import { h, icon, confirmBox, toast, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { hubTabs } from "../components/hubtabs.js";
import { moreMenu, menuItem } from "../components/lesson_menu.js";
import { t } from "../i18n.js";
import { emptyState } from "../components/empty.js";
import { shortRoomLabel, gradeName, fmtShort, triName } from "../labels.js";
import { dateField } from "../components/date3.js";
import { sourceTools } from "../components/source_ui.js";

// My files. On the right: the grades, and inside the open grade its weeks. In the middle: what sits in that week (files, links, messages), each in its own box
// with a «for students» switch and the teacher's note right under it. The same file can sit in several grades and weeks, each place with its own note and switch.
// The AI needs no switch: every file here can be chosen as a source wherever the AI asks for one.
const view = { g: "", key: "", all: false };   // where the teacher was looking, kept while moving between pages

export async function renderLibrary(root) {
  const [structure, ov] = await Promise.all([api.get("/api/structure"), api.get("/api/overview")]);
  const ai = await guarded(() => api.get("/api/ai")) || { ready: false };
  const cloud = await guarded(() => api.get("/api/cloud")) || {};
  const staff = !!(cloud.signed_in && (cloud.role === "teacher" || cloud.role === "admin"));
  const wanted = new URLSearchParams((location.hash.split("?")[1] || "")).get("share") || "";
  const tools = sourceTools({ ai, reload: () => load() });
  const grades = structure.grades.filter((g) => structure.rooms.some((r) => r.grade_id === g.id));
  const gradeById = (id) => structure.grades.find((g) => g.id === id);
  const roomsOf = (gid) => structure.rooms.filter((r) => gid === "*" || r.grade_id === gid);
  let lib = { items: [], orphans: [], root: "" }, online = false;

  // the weeks of the year
  const weeks = [];   // { t, w, start, end }
  for (const tri of ov.trimesters || []) for (const w of tri.weeks || []) weeks.push({ t: tri.index, w: w.number, start: w.start, end: w.end });
  const pos = ov.position && ov.position.state === "in_term" ? ov.position : null;
  const wkKey = (tt, w) => (tt === null || tt === undefined || w === null || w === undefined ? "none" : `${tt}-${w}`);
  const curKey = pos ? wkKey(pos.trimester, pos.week) : "";
  const parseKey = (v) => (v === "none" ? { t: null, w: null } : { t: +v.split("-")[0], w: +v.split("-")[1] });
  const wkName = (key) => (key === "none" ? t("lf_no_week") : t("cal_week_n", { n: key.split("-")[1] }));
  const wkLabel = (key) => (key === "none" ? t("lf_no_week") : `${triName("T" + (+key.split("-")[0] + 1))} · ${t("cal_week_n", { n: key.split("-")[1] })}`);
  const gradeLabel = (gid) => (gid === "*" ? t("fx_all_grades") : gid ? (gradeById(gid) ? gradeName(gradeById(gid)) : gid) : t("fx_no_grade_opt"));
  const whereLabel = (p) => `${gradeLabel(p.g)} · ${wkName(wkKey(p.t, p.w))}`;

  const all = () => lib.items.flatMap((f) => f.places.map((p) => ({ f, p })));
  const inGrade = (p, gid) => (gid === "none" ? !p.g : p.g === gid || p.g === "*");
  const isOn = (p) => !!(p.shared && p.shared.public);
  const hasKey = (gid, key) => all().some(({ p }) => inGrade(p, gid) && wkKey(p.t, p.w) === key);
  function defaultKey(gid) {
    if (curKey) return curKey;
    const mine = all().filter(({ p }) => inGrade(p, gid) && p.t !== null);
    const last = mine.map(({ p }) => p).sort((a, b) => b.t - a.t || b.w - a.w)[0];
    return last ? wkKey(last.t, last.w) : "none";
  }
  if (!view.g || (view.g !== "none" && !grades.some((g) => g.id === view.g))) { view.g = grades[0] ? grades[0].id : "none"; view.key = ""; }

  async function load() {
    const [l, pubs] = await Promise.all([api.get("/api/library"), api.get("/api/publications").catch(() => ({ connected: false }))]);
    lib = l; online = pubs.connected && ["admin", "teacher"].includes(pubs.role);
    if (!view.key) view.key = view.g === "none" ? "none" : defaultKey(view.g);
    draw();
  }
  const act = (fn) => guarded(async () => { await fn(); await load(); });
  const post = (path, body) => act(() => api.post(path, body));

  // ---------------------------------------------------------------- the box of one thing in one week
  const switchEl = (f, p) => {
    const input = h("input", { type: "checkbox", checked: isOn(p), disabled: !online || f.private, "aria-label": t("lf_for_students"),
      onChange: (e) => { e.target.checked = isOn(p); setVisible(f, p, !isOn(p)); } });
    return h("label", { class: "fx-tg", title: online ? "" : t("lb_offline") }, input, h("span", { class: "trk" }), h("span", {}, t("lf_for_students")));
  };
  async function setVisible(f, p, on) {
    if (!on) { if (await confirmBox(t("lb_unshare_confirm"))) await post("/api/library/visible", { rel: f.rel, pid: p.id, on: false }); else draw(); return; }
    let g = p.g;
    if (!g) {   // no grade yet: ask once, the file stays there
      g = await askGrade(f);
      if (!g) { draw(); return; }
      if (!(await guarded(() => api.post("/api/library/place", { rel: f.rel, pid: p.id, g })))) { draw(); return; }
    }
    let from;
    if (f.kind === "quiz") { from = await askQuizDate(); if (!from) { draw(); return; } }
    const r = await guarded(() => api.post("/api/library/visible", { rel: f.rel, pid: p.id, on: true, visible_from: from, kind: f.kind }));
    if (r) toast(t("lf_shared_now"));
    await load();
  }
  function askGrade(f) {
    return new Promise((resolve) => {
      const sel = h("select", {}, grades.map((g) => h("option", { value: g.id }, gradeName(g))), h("option", { value: "*" }, t("fx_all_grades")));
      let done = false; const finish = (v) => { if (!done) { done = true; resolve(v); } };
      modal({ title: t("fx_grade_ask"), onClose: () => finish(""), body: h("div", {}, h("p", { class: "muted" }, f.name), h("p", { class: "muted small" }, t("fx_grade_ask_lead")), h("label", { class: "field" }, h("span", { class: "label" }, t("fx_grade_label")), sel)),
        actions: [{ label: t("cancel"), onClick: () => finish("") }, { label: t("lb_share"), kind: "primary", onClick: () => finish(sel.value) }] });
    });
  }
  function askQuizDate() {
    return new Promise((resolve) => {
      const from = dateField({ label: t("fx_quiz_date") });
      let done = false; const finish = (v) => { if (!done) { done = true; resolve(v); } };
      modal({ title: t("fx_quiz_date"), onClose: () => finish(""), body: h("div", {}, h("p", { class: "muted small" }, t("pb_quiz_hint")), from),
        actions: [{ label: t("cancel"), onClick: () => finish("") }, { label: t("lb_share"), kind: "primary", onClick: () => { if (!from.value) { toast(t("pb_quiz_hint"), "error"); return false; } finish(from.value); } }] });
    });
  }

  const noteBox = (f, p) => {
    const note = h("textarea", { class: "fx-note", rows: 1, maxlength: 300, placeholder: t("lf_note_ph"), "aria-label": t("lf_note_ph") }, p.note || "");
    const grow = () => { note.style.height = "auto"; note.style.height = Math.max(note.scrollHeight, 38) + "px"; };
    note.addEventListener("input", grow); note.addEventListener("change", () => guarded(async () => { await api.post("/api/library/place", { rel: f.rel, pid: p.id, note: note.value }); p.note = note.value; toast(t("lf_note_saved")); }));
    requestAnimationFrame(grow);
    return note;
  };
  const alsoChips = (f, p) => f.places.filter((q) => q.id !== p.id).map((q) => h("span", { class: "fx-also" }, t("fx_also", { where: whereLabel(q) })));
  const openFile = (f, folder) => guarded(() => api.post("/api/open", { path: lib.root + "/" + f.rel, folder }));
  const readPics = (f) => (f.source && f.source.pending ? h("button", { class: "btn small primary", onClick: () => tools.run(() => tools.process(f.source.id)) }, icon("spark"), t("src_read_pics", { n: f.source.pending })) : null);
  const takeOut = (f, p) => async () => { if (p.shared && !(await confirmBox(t("lb_unshare_confirm")))) return; await post("/api/library/place/delete", { rel: f.rel, pid: p.id }); };
  const whereItem = (f) => menuItem(t("fx_where_btn"), () => whereDialog(f), { icon: "calendar" });
  const removeItem = (f, p) => menuItem(t("lf_week_remove"), takeOut(f, p), { icon: "close" });

  const fileBox = ({ f, p }) => {
    const ext = (f.name || "").split(".").pop().toLowerCase();
    return h("div", { class: `fx-box${isOn(p) ? "" : " off"}${wanted && f.rel === wanted ? " flash" : ""}`, "data-rel": f.rel },
      h("div", { class: "fx-top" }, h("span", { class: `file-ico ext-${ext}` }, icon("file")),
        h("div", { class: "fx-name" }, h("b", {}, f.name), h("div", { class: "muted small" }, [f.kind === "book" ? t("pb_k_book") : f.folder, ...(f.private ? [t("lb_private")] : [])].join(" · "), alsoChips(f, p))),
        f.private ? null : switchEl(f, p)),
      f.private ? null : noteBox(f, p),
      h("div", { class: "fx-ft" }, h("button", { class: "btn small", onClick: () => openFile(f, false) }, icon("file"), t("d_open_file")), readPics(f), h("span", { class: "grow" }),
        moreMenu([menuItem(t("d_open_folder"), () => openFile(f, true), { icon: "folder" }), whereItem(f), removeItem(f, p)])));
  };
  const linkBox = ({ f, p }) => {
    const host = f.url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
    const isYt = /youtube\.com|youtu\.be/i.test(f.url);
    return h("div", { class: `fx-link${isOn(p) ? "" : " off"}`, "data-rel": f.rel },
      h("div", { class: "badge" }, "LINK", h("small", {}, host.slice(0, 22))),
      h("div", { class: "mid" }, h("h3", {}, f.name), h("a", { class: "url", href: f.url, target: "_blank", rel: "noopener noreferrer", dir: "ltr" }, f.url.replace(/^https?:\/\//, "").slice(0, 70)), noteBox(f, p), h("div", {}, alsoChips(f, p))),
      h("div", { class: "side" }, switchEl(f, p), h("a", { class: "btn small", href: f.url, target: "_blank", rel: "noopener noreferrer" }, icon("link"), t("lf_open_link")),
        moreMenu([whereItem(f), removeItem(f, p), ...(isYt && !f.source ? [menuItem(t("fx_read_yt"), () => linkSourceDialog(f), { icon: "spark" })] : []),
          menuItem(t("lf_link_del"), async () => { if (await confirmBox(t("lf_link_del_confirm"))) post("/api/library/link/delete", { rel: f.rel }); }, { icon: "trash", danger: true })])));
  };
  const msgBox = ({ f, p }) => h("div", { class: `fx-msg${isOn(p) ? "" : " off"}`, "data-rel": f.rel },
    h("span", { class: "q", "aria-hidden": "true" }, "“"), h("div", { class: "txt" }, f.text, h("div", {}, alsoChips(f, p))),
    h("div", { class: "side" }, h("span", { class: "lbl" }, t("fx_msg")), switchEl(f, p),
      moreMenu([menuItem(t("fx_edit"), () => messageDialog(f), { icon: "edit" }), whereItem(f), removeItem(f, p),
        menuItem(t("lf_link_del"), async () => { if (await confirmBox(t("fx_msg_del_confirm"))) post("/api/library/message/delete", { rel: f.rel }); }, { icon: "trash", danger: true })])));

  // ---------------------------------------------------------------- dialogs
  function whereDialog(f0) {   // the places of one file: grade and week of each, add a place, take one away
    const body = h("div", {});
    modal({ title: f0.name, body, actions: [{ label: t("close"), kind: "primary" }] });
    const draw1 = async () => {
      const cur = (await api.get("/api/library")).items.find((x) => x.rel === f0.rel);
      if (!cur) return;
      const gradeOpts = (sel) => [h("option", { value: "", selected: !sel }, t("fx_no_grade_opt")), ...grades.map((g) => h("option", { value: g.id, selected: sel === g.id }, gradeName(g))), h("option", { value: "*", selected: sel === "*" }, t("fx_all_grades"))];
      const weekOpts = (sel) => [h("option", { value: "none", selected: sel === "none" }, t("lf_no_week")), ...weeks.map((x) => h("option", { value: wkKey(x.t, x.w), selected: sel === wkKey(x.t, x.w) }, wkLabel(wkKey(x.t, x.w))))];
      const refresh = async () => { await draw1(); await load(); };
      const addG = h("select", {}, gradeOpts(view.g === "none" ? "" : view.g)), addW = h("select", {}, weekOpts(view.key || "none"));
      body.replaceChildren(h("p", { class: "muted small" }, t("lf_weeks_lead")),
        ...cur.places.map((p) => h("div", { class: "row where-row" },
          h("select", { "aria-label": t("fx_grade_label"), onChange: async (e) => { const r = await guarded(() => api.post("/api/library/place", { rel: cur.rel, pid: p.id, g: e.target.value || null })); if (r && r.unshared) toast(t("fx_unshared")); await refresh(); } }, gradeOpts(p.g || "")),
          h("select", { class: "grow", "aria-label": t("lf_weeks_title"), onChange: async (e) => { await guarded(() => api.post("/api/library/place", { rel: cur.rel, pid: p.id, ...parseKey(e.target.value) })); await refresh(); } }, weekOpts(wkKey(p.t, p.w))),
          isOn(p) ? h("span", { class: "chip small on" }, t("lf_live")) : null,
          h("button", { class: "btn small ghost", title: t("lf_week_remove"), "aria-label": t("lf_week_remove"), disabled: cur.places.length === 1 && !p.g && wkKey(p.t, p.w) === "none",
            onClick: async () => { if (p.shared && !(await confirmBox(t("lb_unshare_confirm")))) return; await guarded(() => api.post("/api/library/place/delete", { rel: cur.rel, pid: p.id })); await refresh(); } }, icon("trash")))),
        h("div", { class: "row where-row", style: { marginTop: ".8rem" } }, h("b", {}, t("lf_week_add")), addG, addW,
          h("button", { class: "btn small", onClick: async () => { await guarded(() => api.post("/api/library/place/add", { rel: cur.rel, g: addG.value || null, ...parseKey(addW.value) })); await refresh(); } }, icon("plus"), t("lf_week_add_btn"))));
    };
    draw1();
  }
  function linkSourceDialog(f) {   // a video: its text is pasted, then the AI can use it
    const text = h("textarea", { rows: 5, style: { width: "100%" }, placeholder: t("src_yt_ph"), "aria-label": t("src_yt"), required: true });
    modal({ title: f.name, body: h("div", {}, h("p", { class: "muted small" }, t("lf_link_src_lead")), text),
      actions: [{ label: t("cancel") }, { label: t("lf_link_src_go"), kind: "primary", onClick: () => tools.run(async () => {
        const r = await api.post("/api/library/source", { rel: f.rel, on: true, transcript: text.value });
        const s = r.items.find((x) => x.rel === f.rel)?.source; await load(); if (s) await tools.process(s.id); }) }] });
  }
  const place0 = () => (view.key === "none" ? { t: null, w: null } : parseKey(view.key));
  const target = () => ({ g: view.g === "none" ? null : view.g, ...place0() });

  function messageDialog(f) {   // write a new message, or change one
    const text = h("textarea", { rows: 5, maxlength: 600, style: { width: "100%" }, placeholder: t("fx_msg_ph"), "aria-label": t("fx_msg_ph"), required: true }, f ? f.text : "");
    const left = h("small", { class: "muted" });
    const count = () => { left.textContent = t("fx_msg_left", { n: 600 - text.value.length }); };
    text.addEventListener("input", count); count();
    modal({ title: f ? t("fx_msg_edit") : t("fx_msg_new"), body: h("div", {}, text, left),
      actions: [{ label: t("cancel") }, { label: t("save"), kind: "primary", onClick: async () => {
        if (!text.value.trim()) { text.focus(); return false; }
        return !!(await guarded(async () => { await api.post(f ? "/api/library/message/set" : "/api/library/message", f ? { rel: f.rel, text: text.value } : { text: text.value, ...target() }); toast(t("saved")); await load(); return true; }));
      } }] });
  }
  function linkDialog() {
    const title = h("input", { type: "text", maxlength: 120, placeholder: t("lf_link_title_ph"), "aria-label": t("lf_link_title_ph") });
    const url = h("input", { type: "url", dir: "ltr", placeholder: "https://…", "aria-label": t("src_url"), required: true });
    modal({ title: t("fx_link_title"), body: h("div", { class: "stack" }, h("label", { class: "field" }, h("span", { class: "label" }, t("lf_link_title_ph")), title), h("label", { class: "field" }, h("span", { class: "label" }, t("src_url")), url)),
      actions: [{ label: t("cancel") }, { label: t("lf_link_add"), kind: "primary", onClick: async () => {
        if (!url.value.trim()) { url.focus(); return false; }
        return !!(await guarded(async () => { await api.post("/api/library/link", { title: title.value, url: url.value, ...target() }); toast(t("saved")); await load(); return true; }));
      } }] });
  }

  const readB64 = (file) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] || ""); r.onerror = () => rej(r.error); r.readAsDataURL(file); });
  async function upload(files) {
    let n = 0; const pics = [];
    for (const file of files) {
      if (file.size > 40 * 1024 * 1024) { toast(t("err_file_too_big"), "error"); continue; }
      toast(t("fx_uploading"));
      const r = await guarded(async () => api.post("/api/library/upload", { filename: file.name, data_b64: await readB64(file), ...target() }));
      if (r) { n += 1; const s = (r.items || []).find((x) => x.rel === r.added)?.source; if (s && s.pending > 0 && ai.ready) pics.push(s.id); }
    }
    if (n) toast(t("fx_uploaded"));
    await load();
    for (const id of pics) await tools.process(id);
  }
  function fileDialog() {   // pick files that are already here, or bring a new one
    const picked = new Set();
    const search = h("input", { type: "search", placeholder: t("fx_pick_search"), "aria-label": t("fx_pick_search") });
    const list = h("div", { class: "fx-pick" });
    const addBtn = { label: t("fx_pick_add", { n: 0 }), kind: "primary", disabled: true };
    const m = modal({ title: t("fx_pick_title"), wide: true, body: h("div", {}, h("div", { class: "row" }, search,
      h("label", { class: "btn" }, icon("upload"), t("fx_upload"), h("input", { type: "file", multiple: true, hidden: true, accept: ".docx,.pptx,.xlsx,.pdf", onChange: async (e) => { const fl = [...e.target.files]; if (fl.length) { m.close(); await upload(fl); } } }))), list),
      actions: [{ label: t("cancel") }, { ...addBtn, onClick: async (_e, close) => {
        const t0 = target(); close();
        await act(async () => { for (const rel of picked) await api.post("/api/library/place/add", { rel, ...t0 }); });
      }, close: false }] });
    const btn = () => m.el.querySelector("footer .btn.primary");
    const refreshBtn = () => { const b = btn(); if (b) { b.disabled = !picked.size; b.textContent = t("fx_pick_add", { n: picked.size }); } };
    const draw2 = () => {
      const q = search.value.trim().toLowerCase(), tg = target();
      const rows = lib.items.filter((f) => f.kind !== "message" && (!q || f.name.toLowerCase().includes(q))
        && !f.places.some((p) => (p.g || null) === tg.g && p.t === tg.t && p.w === tg.w));
      list.replaceChildren(rows.length ? rows.map((f) => {
        const where = f.places.filter((p) => p.g || p.t !== null);
        return h("label", { class: "fx-pick-row" }, h("input", { type: "checkbox", checked: picked.has(f.rel), onChange: (e) => { if (e.target.checked) picked.add(f.rel); else picked.delete(f.rel); refreshBtn(); } }),
          h("span", { class: `file-ico ext-${f.kind === "link" ? "link" : f.name.split(".").pop().toLowerCase()}` }, icon(f.kind === "link" ? "link" : "file")),
          h("span", { class: "grow" }, h("b", {}, f.name), where.length ? h("small", { class: "muted" }, " · " + t("fx_pick_elsewhere", { where: whereLabel(where[0]) })) : null));
      }) : h("p", { class: "muted" }, t("fx_pick_none")));
    };
    search.addEventListener("input", draw2); draw2(); refreshBtn();
  }
  function addMenu() {
    const tile = (cls, label, text, desc, fn) => h("button", { class: "fx-tile", type: "button", onClick: () => { m.close(); fn(); } }, h("span", { class: `ic ${cls}` }, text), h("b", {}, label), h("span", {}, desc));
    const m = modal({ title: t("fx_add_to", { where: whereLabel(target()) }), wide: true,
      body: h("div", { class: "fx-tiles" }, tile("a", t("fx_file"), "FILE", t("fx_file_d"), fileDialog), tile("b", t("fx_link"), "LINK", t("fx_link_d"), linkDialog), tile("c", t("fx_msg"), "MSG", t("fx_msg_d"), () => messageDialog(null))),
      actions: [{ label: t("cancel") }] });
  }

  // ---------------------------------------------------------------- the grade and week tree
  function weekRow(gid, key, list) {
    const relevant = list.filter(({ f }) => !f.private), on = relevant.filter(({ p }) => isOn(p)).length;
    const dot = !relevant.length ? "" : on === relevant.length ? "f" : on ? "h" : "";
    return h("button", { class: `fx-w${view.g === gid && view.key === key ? " sel" : ""}`, type: "button", onClick: () => { view.g = gid; view.key = key; draw(); } },
      h("i", { class: dot }), h("span", {}, wkName(key)), key === curKey ? h("em", {}, t("fx_cur_here")) : null, h("small", {}, list.length));
  }
  function weekList(gid) {
    const mine = all().filter(({ p }) => inGrade(p, gid)), by = new Map();
    for (const e of mine) { const k = wkKey(e.p.t, e.p.w); (by.get(k) || by.set(k, []).get(k)).push(e); }
    const i0 = weeks.findIndex((x) => wkKey(x.t, x.w) === curKey), near = new Set();
    for (let i = Math.max(i0, 0); i0 >= 0 && i <= i0 + 2 && i < weeks.length; i++) near.add(wkKey(weeks[i].t, weeks[i].w));
    const rows = []; let lastT = -1;
    for (const x of weeks) {
      const k = wkKey(x.t, x.w);
      if (!(view.all || by.has(k) || near.has(k) || k === view.key)) continue;
      if (x.t !== lastT) { rows.push(h("div", { class: "fx-tri" }, triName("T" + (x.t + 1)))); lastT = x.t; }
      rows.push(weekRow(gid, k, by.get(k) || []));
    }
    if (by.has("none") || view.key === "none") rows.push(weekRow(gid, "none", by.get("none") || []));
    rows.push(h("button", { class: "fx-more", type: "button", onClick: () => { view.all = !view.all; draw(); } }, view.all ? t("fx_fewer_weeks") : t("fx_all_weeks")));
    return h("div", { class: "fx-ws" }, rows);
  }
  function tree() {
    const noGrade = all().filter(({ p }) => !p.g).length;
    return h("div", { class: "fx-tree" },
      grades.map((g) => h("div", {}, h("button", { class: `fx-g${view.g === g.id ? " on" : ""}`, type: "button", onClick: () => { view.g = g.id; view.key = defaultKey(g.id); draw(); } },
        h("span", {}, gradeName(g)), h("small", {}, all().filter(({ p }) => inGrade(p, g.id)).length)), view.g === g.id ? weekList(g.id) : null)),
      noGrade || view.g === "none" ? [h("hr"), h("button", { class: `fx-g muted${view.g === "none" ? " on" : ""}`, type: "button", onClick: () => { view.g = "none"; view.key = "none"; draw(); } }, h("span", {}, t("fx_no_grade")), h("small", {}, noGrade))] : null);
  }

  // ---------------------------------------------------------------- the middle
  function head() {
    if (view.g === "none") return h("div", { class: "fx-head" }, h("h2", {}, t("fx_no_grade")), h("span", { class: "muted" }, t("fx_no_grade_hint")));
    const span = view.key === "none" ? null : weeks.find((x) => wkKey(x.t, x.w) === view.key);
    const rooms = roomsOf(view.g);
    return h("div", { class: "fx-head" },
      h("div", { class: "fx-head-top" }, h("h2", {}, wkName(view.key)), view.key === curKey ? h("span", { class: "chip small on" }, t("lf_week_cur")) : null,
        h("span", { class: "muted" }, span ? `${fmtShort(span.start)} – ${fmtShort(span.end)}` : ""), h("span", { class: "grow" }),
        h("button", { class: "btn primary", onClick: addMenu }, icon("plus"), t("fx_add"), " ⌄")),
      rooms.length ? h("div", { class: "fx-head-rooms muted small" }, t("fx_shown_to"), " ", rooms.map((r) => h("span", { class: "chip small" }, shortRoomLabel(r, structure)))) : null);
  }
  // ---------------------------------------------------------------- the week plan parents see (homework + quiz alerts), kept under the week's header
  const plans = new Map();   // "<grade>|<week key>" -> what the teacher typed, kept while moving around so nothing is lost
  function planBox() {
    const rooms = roomsOf(view.g);
    if (view.g === "none" || view.g === "*" || view.key === "none" || !rooms.length) return null;
    const k = parseKey(view.key), pkey = `${view.g}|${view.key}`;
    const box = h("details", { class: "fx-plan", open: !!view.planOpen });
    box.addEventListener("toggle", () => { view.planOpen = box.open; });
    const lines = (v) => String(v || "").split("\n").map((x) => x.trim()).filter(Boolean);
    const weekLinks = () => all().filter(({ f, p }) => f.kind === "link" && inGrade(p, view.g) && wkKey(p.t, p.w) === view.key && isOn(p)).map(({ f }) => `${f.name}: ${f.url}`);
    async function fetchPlan() {
      const rs = (await Promise.all(rooms.map((r) => guarded(() => api.get(`/api/parent-week?room=${r.id}&tri=${k.t}&week=${k.w}`))))).filter(Boolean);
      if (!rs.length) return null;
      const first = (key) => (rs.find((x) => x[key] && x[key].length) || { [key]: [] })[key];
      return { topics: [...new Set(rs.flatMap((x) => x.topics))], hw: first("homework").join("\n"), qz: first("quiz_alerts").map((a) => (a.date ? `${a.title} | ${a.date}` : a.title)).join("\n"), approved: rs.every((x) => x.approved) };
    }
    const payload = (r, d) => ({ room_id: r.id, trimester: k.t, week: k.w, homework: d.hw, quiz_alerts: d.qz });
    const message = (lang, d) => {
      const L = { ar: { hi: "السلام عليكم ورحمة الله، أولياء الأمور الكرام 🌷", wk: "ملخص الأسبوع", did: "📚 اللي اتشرح:", hw: "📝 الواجب:", mat: "🔗 مصادر مساعدة:", qz: "⏰ اختبارات قادمة:", end: "شكرًا لتعاونكم." },
                  en: { hi: "Dear parents,", wk: "Week summary", did: "📚 This week we learned:", hw: "📝 Homework:", mat: "🔗 Helpful links:", qz: "⏰ Upcoming quizzes:", end: "Thank you for your support." } }[lang];
      const block = (title, items) => (items.length ? [title, ...items.map((x) => "• " + x), ""] : []);
      return [L.hi, `${L.wk} ${k.w}`, "", ...block(L.did, d.topics), ...block(L.hw, lines(d.hw)), ...block(L.mat, weekLinks()), ...block(L.qz, lines(d.qz).map((x) => x.replace(/\s*\|\s*/, " – "))), L.end].join("\n").trim();
    };
    function fill(d) {
      const hw = h("textarea", { rows: 3, placeholder: t("pw_hw_ph"), "aria-label": t("pw_hw") }, d.hw), qz = h("textarea", { rows: 2, placeholder: t("pw_quiz_ph"), "aria-label": t("pw_quiz") }, d.qz);
      hw.addEventListener("input", () => { d.hw = hw.value; }); qz.addEventListener("input", () => { d.qz = qz.value; });
      const run = (fn) => guarded(async () => { for (const r of rooms) await fn(r); plans.delete(pkey); toast(t("saved")); await show(); });
      const copy = (lang) => guarded(async () => { await navigator.clipboard.writeText(message(lang, d)); toast(t("pw_copied")); });
      box.replaceChildren(
        h("summary", {}, h("b", {}, t("fx_plan_title")), d.approved ? h("span", { class: "chip on small" }, t("pb_live")) : (d.hw || d.qz ? h("span", { class: "chip small" }, t("fx_plan_draft")) : null)),
        h("div", { class: "fx-plan-in" },
          h("p", { class: "muted small" }, t("fx_plan_hint")),
          d.topics.length ? h("div", { class: "banner info" }, icon("info"), h("div", {}, h("b", {}, t("pw_taught")), " ", d.topics.join(" · "))) : null,
          h("label", { class: "field" }, h("span", { class: "label" }, t("pw_hw")), hw),
          h("label", { class: "field" }, h("span", { class: "label" }, t("pw_quiz")), qz),
          h("div", { class: "row" },
            h("button", { class: "btn", onClick: () => run((r) => api.put("/api/parent-week", payload(r, d))) }, t("save")),
            staff ? h("button", { class: "btn primary", onClick: () => run((r) => api.post("/api/parent-week/publish", payload(r, d))) }, icon("send"), t("pw_publish")) : h("span", { class: "muted small" }, t("an_not_connected")),
            staff && d.approved ? h("button", { class: "btn ghost", onClick: () => run((r) => api.post("/api/parent-week/unpublish", payload(r, d))) }, t("pb_unapprove")) : null,
            h("span", { class: "grow" }), h("span", { class: "muted small" }, t("pw_msg")),
            h("button", { class: "btn small", onClick: () => copy("ar") }, icon("copy"), "عربي"), h("button", { class: "btn small", onClick: () => copy("en") }, icon("copy"), "English"))));
    }
    async function show() {
      let d = plans.get(pkey);
      if (!d) { d = await fetchPlan(); if (!d) { box.remove(); return; } plans.set(pkey, d); }
      if (box.isConnected || !box.parentNode) fill(d);
    }
    box.append(h("summary", {}, h("b", {}, t("fx_plan_title"))));
    show();
    return box;
  }

  function middle() {
    const here = all().filter(({ p }) => inGrade(p, view.g) && (view.g === "none" || wkKey(p.t, p.w) === view.key)).sort((a, b) => b.f.mtime - a.f.mtime);
    const msgs = here.filter(({ f }) => f.kind === "message"), links = here.filter(({ f }) => f.kind === "link"), files = here.filter(({ f }) => f.kind !== "message" && f.kind !== "link");
    const main = h("div", { class: "fx-main" }, head(), planBox(),
      here.length ? h("div", { class: "fx-stack" }, msgs.map(msgBox), files.length ? h("div", { class: "fx-two" }, files.map(fileBox)) : null, links.map(linkBox))
        : h("div", { class: "fx-empty" }, icon("folder"), h("p", {}, view.g === "none" ? t("lb_none") : t("fx_empty"))));
    if (view.g !== "none") {   // drop files on the week to add them there
      main.addEventListener("dragover", (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); main.classList.add("drop"); } });
      main.addEventListener("dragleave", (e) => { if (e.target === main) main.classList.remove("drop"); });
      main.addEventListener("drop", (e) => { e.preventDefault(); main.classList.remove("drop"); const fl = [...(e.dataTransfer?.files || [])]; if (fl.length) upload(fl); });
    }
    return main;
  }

  function draw() {
    if (!root.isConnected) return;
    const orphans = lib.orphans || [];
    root.replaceChildren(h("div", { class: "page" }, hubTabs("library", "library"),
      h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_library")), h("p", {}, t("lb_lead")))),
      online ? null : h("div", { class: "banner info" }, icon("info"), h("div", {}, t("lb_offline"))),
      ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, t("src_need_ai"), " ", h("a", { href: "#/settings" }, t("ai_setup_link")))),
      tools.status,
      grades.length || lib.items.length ? h("div", { class: "fx-lay" }, tree(), middle())
        : emptyState({ icon: "folder", title: t("lb_none_title"), text: t("lb_none"), action: { label: t("nav_docs"), icon: "file", onClick: () => { location.hash = "#/docs"; } } }),
      orphans.length ? h("details", { class: "wk-group", style: { marginTop: "1rem" } }, h("summary", {}, h("b", {}, t("lf_orphans"))),
        orphans.map((s) => h("div", { class: "pub-row file-row" }, h("div", { class: "file-main" }, h("span", { class: "file-ico ext-link" }, icon("link")),
          h("div", { style: { minWidth: 0 } }, h("b", {}, s.name), h("div", { class: "muted small" }, `${t("lf_src_only")} · ${t("src_meta", { pages: s.pages, date: s.added })}`))),
          h("div", { class: "file-acts" }, tools.buttons(s), tools.removeButton(s)), h("div", { class: "file-more" }, tools.details(s))))) : null));
    const sel = root.querySelector(".fx-w.sel, .fx-g.on"); sel && sel.scrollIntoView({ block: "nearest" });
    const flash = wanted && root.querySelector(`[data-rel="${CSS.escape(wanted)}"]`); if (flash) flash.scrollIntoView({ block: "center" });
  }

  await load();
  if (wanted) {   // opened from «share» on a file elsewhere: go to where that file sits
    const f = lib.items.find((x) => x.rel === wanted), p = f && f.places[0];
    if (p) { view.g = p.g && p.g !== "*" && grades.some((g) => g.id === p.g) ? p.g : (grades[0] ? grades[0].id : "none"); view.key = wkKey(p.t, p.w); draw(); }
  }
}
