import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

// Messages with the families. A teacher writes to the STUDENT or to the STUDENT'S PARENTS (father and mother share one conversation).
// The administration also sees every conversation and the reports families sent about a message.
const kindName = (k) => (k === "parent_teacher" ? t("ms_kind_parent") : t("ms_kind_student"));
const clock = (iso) => { const d = new Date(iso); if (isNaN(d)) return ""; const today = d.toDateString() === new Date().toDateString(); const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", hour12: true }); return today ? time : `${d.toLocaleDateString(undefined, { day: "numeric", month: "short" })} ${time}`; };
const roleName = (r) => ({ teacher: t("ms_r_teacher"), parent: t("ms_r_parent"), student: t("ms_r_student"), admin: t("ms_r_admin") }[r] || "");

export async function renderMessages(root) {
  let data = await api.get("/api/messages"), sel = null, mode = "talks", reports = null, timer = null, openLoad = 0;
  const page = h("div", { class: "page ms" });
  root.replaceChildren(page);
  const alive = () => root.isConnected && page.isConnected;
  const stop = () => { if (timer) { clearInterval(timer); timer = null; } };

  const badge = () => document.dispatchEvent(new CustomEvent("ms-unread", { detail: data.unread || 0 }));

  function head() {
    const tabs = data.role === "admin" ? h("div", { class: "seg", role: "tablist" },
      h("button", { class: "seg-btn", role: "tab", "aria-selected": String(mode === "talks"), onClick: () => { mode = "talks"; draw(); } }, t("ms_tab_talks")),
      h("button", { class: "seg-btn", role: "tab", "aria-selected": String(mode === "reports"), onClick: () => { mode = "reports"; draw(); } }, t("ms_tab_reports"), reports && reports.open ? h("span", { class: "dot-count" }, reports.open) : null)) : null;
    return h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_messages")), h("p", {}, t("ms_lead"))), tabs);
  }

  function draw() {
    stop();
    if (!data.connected) {
      return page.replaceChildren(head(), h("div", { class: "panel" }, h("p", {}, data.problem === "cloud_offline" ? t("an_offline") : t("an_not_connected")), h("a", { class: "btn", href: "#/settings" }, icon("settings"), t("nav_settings"))));
    }
    if (mode === "reports") return drawReports();
    const list = h("div", { class: "ms-list" }), pane = h("div", { class: "ms-pane" });
    page.replaceChildren(head(), h("div", { class: "ms-wrap" + (sel ? " open" : "") }, h("div", { class: "ms-side panel" }, data.role === "admin" ? null : h("button", { class: "btn primary", onClick: () => { sel = null; newTalk(pane); markOpen(); } }, icon("plus"), t("ms_new")), list), pane));
    fillList(list, pane);
    if (sel) openTalk(pane); else if (!data.threads.length) pane.append(emptyBox()); else pane.append(h("div", { class: "empty-note" }, icon("mail"), t("ms_pick")));
    timer = setInterval(async () => {
      if (!alive()) return stop();
      try { data = await api.get("/api/messages"); fillList(list, pane); badge(); } catch { /* the next round tries again */ }
    }, 15000);
  }
  const markOpen = () => page.querySelector(".ms-wrap")?.classList.toggle("open", true);
  const emptyBox = () => h("div", { class: "empty-note" }, icon("mail"), h("b", {}, t("ms_none")), h("span", {}, data.role === "admin" ? t("ms_none_admin") : t("ms_none_text")));

  function fillList(list, pane) {
    list.replaceChildren(...data.threads.map((th) => h("button", { class: "ms-item" + (th.unread ? " unread" : "") + (th.id === sel ? " on" : ""), onClick: () => { sel = th.id; page.querySelector(".ms-wrap")?.classList.add("open"); fillList(list, pane); openTalk(pane); } },
      h("span", { class: "ms-avatar" }, [...(th.student_name || "?")][0]),
      h("span", { class: "ms-tx" }, h("b", {}, th.student_name || "—", h("span", { class: "chip " + (th.kind === "parent_teacher" ? "" : "indigo") }, kindName(th.kind))),
        h("small", {}, [th.class_name, data.role === "admin" ? th.teacher_name : ""].filter(Boolean).join(" · ")), h("small", { class: "ms-last" }, th.last_body || "—")),
      h("span", { class: "ms-when" }, th.last_at ? clock(th.last_at) : "", th.unread ? h("span", { class: "dot-count" }, "•") : null))));
  }

  // ---- a new conversation: class, student, and who the message is for
  async function newTalk(pane) {
    stop();
    const d = await api.get("/api/messages/students");
    if (!d.classes.length) return pane.replaceChildren(h("div", { class: "empty-note" }, h("b", {}, t("ms_no_classes")), h("span", {}, t("ms_no_classes_text"))));
    const cls = h("select", {}, d.classes.map((c) => h("option", { value: c.class_id }, c.name))), stu = h("select", {});
    let kind = "parent_teacher";
    const cards = h("div", { class: "ms-for" });
    const fillStudents = () => { const c = d.classes.find((x) => x.class_id === cls.value); stu.replaceChildren(...c.students.map((s) => h("option", { value: s.code }, s.name))); paintFor(); };
    const who = () => d.classes.find((x) => x.class_id === cls.value).students.find((s) => s.code === stu.value);
    function paintFor() {
      const s = who(); if (s && !s.student_login && kind === "student_teacher") kind = "parent_teacher";
      cards.replaceChildren(
        h("button", { class: "ms-for-card" + (kind === "student_teacher" ? " on" : ""), disabled: !(s && s.student_login), onClick: () => { kind = "student_teacher"; paintFor(); } }, h("b", {}, t("ms_kind_student")), h("small", {}, s && !s.student_login ? t("ms_kg_no_login") : t("ms_for_student_note"))),
        h("button", { class: "ms-for-card" + (kind === "parent_teacher" ? " on" : ""), onClick: () => { kind = "parent_teacher"; paintFor(); } }, h("b", {}, t("ms_kind_parent")), h("small", {}, t("ms_for_parent_note"))));
    }
    cls.addEventListener("change", fillStudents); stu.addEventListener("change", paintFor); fillStudents();
    pane.replaceChildren(h("div", { class: "panel" }, h("h3", {}, t("ms_new")),
      h("label", { class: "field" }, h("span", { class: "label" }, t("ms_class")), cls), h("label", { class: "field" }, h("span", { class: "label" }, t("ms_student")), stu),
      h("div", { class: "field" }, h("span", { class: "label" }, t("ms_for")), cards),
      h("button", { class: "btn primary", onClick: () => guarded(async () => {
        const r = await api.post("/api/messages/start", { student_code: stu.value, kind });
        data = await api.get("/api/messages"); sel = r.id; draw();
      }) }, icon("send"), t("ms_start"))));
  }

  // ---- one conversation, refreshed every few seconds while it is open
  async function openTalk(pane) {
    const th = data.threads.find((x) => x.id === sel); if (!th) return pane.replaceChildren(h("div", { class: "empty-note" }, icon("mail"), t("ms_pick")));
    const my = ++openLoad, log = h("div", { class: "ms-log", "aria-live": "polite" }), seen = new Map();
    const canWrite = !!th.mine;
    const text = h("textarea", { rows: 2, maxlength: 1000, placeholder: t("ms_write"), "aria-label": t("ms_write") });
    const bubble = (m) => h("div", { class: "ms-bubble" + (m.mine ? " mine" : "") + (m.hidden ? " hidden-msg" : "") },
      h("div", { class: "ms-who" }, h("span", { class: "ms-role " + m.sender_role }, roleName(m.sender_role)), m.mine ? t("ms_you") : (m.sender_name || ""), m.hidden ? h("em", {}, t("ms_hidden")) : null),
      h("p", {}, m.body), h("div", { class: "ms-meta" }, h("span", {}, clock(m.created_at)),
        data.role === "admin" ? h("button", { class: "linkish", onClick: () => guarded(async () => { await api.post(`/api/messages/${m.id}/hide`, { hidden: !m.hidden }); m.hidden = !m.hidden; seen.set(m.id, bubble(m)); renderLog(); }) }, m.hidden ? t("ms_show") : t("ms_hide")) : null));
    const rows = new Map();
    function renderLog() { log.replaceChildren(...[...seen.values()]); log.scrollTop = log.scrollHeight; }
    const add = (list) => { let fresh = false; list.forEach((m) => { if (!rows.has(m.id)) { rows.set(m.id, m); seen.set(m.id, bubble(m)); fresh = true; } }); if (fresh) renderLog(); return fresh; };
    const pull = async () => {
      if (my !== openLoad || !alive()) return stop();
      try {
        const d = await api.get(`/api/messages/${th.id}`);
        if (my !== openLoad) return;
        const fresh = add(d.messages);
        if (!rows.size && !log.firstChild) log.replaceChildren(h("div", { class: "empty-note" }, t("ms_no_msgs")));
        if (fresh && th.mine) { await api.post("/api/messages/read", { thread_id: th.id }); th.unread = false; data.unread = data.threads.filter((x) => x.unread).length; badge(); }
      } catch { /* try again on the next round */ }
    };
    const send = () => guarded(async () => {
      const body = text.value.trim(); if (!body) return;
      const r = await api.post("/api/messages/send", { thread_id: th.id, body }); text.value = ""; add([r.message]);
      data = await api.get("/api/messages"); fillList(page.querySelector(".ms-list"), pane);
    });
    text.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
    pane.replaceChildren(h("div", { class: "ms-chat" },
      h("div", { class: "ms-chat-head" }, h("button", { class: "btn ghost small ms-back", "aria-label": t("back"), onClick: () => { sel = null; page.querySelector(".ms-wrap")?.classList.remove("open"); stop(); draw(); } }, icon("back")),
        h("div", { class: "grow" }, h("b", {}, th.student_name || "—"), h("small", {}, [th.class_name, data.role === "admin" ? th.teacher_name : ""].filter(Boolean).join(" · "))), h("span", { class: "chip " + (th.kind === "parent_teacher" ? "" : "indigo") }, kindName(th.kind))),
      h("div", { class: "banner info ms-note" }, icon("info"), th.kind === "parent_teacher" ? t("ms_parent_note") : t("ms_student_note")),
      log, canWrite ? h("div", { class: "ms-compose" }, text, h("button", { class: "btn primary", onClick: send }, icon("send"), t("ms_send"))) : h("div", { class: "banner info ms-note" }, icon("info"), t("ms_readonly"))));
    log.append(h("div", { class: "empty-note" }, t("ms_loading")));
    await pull();
    stop(); timer = setInterval(pull, 4000);
    const list = setInterval(async () => { if (my !== openLoad || !alive()) return clearInterval(list); try { data = await api.get("/api/messages"); fillList(page.querySelector(".ms-list"), pane); badge(); } catch { /* later */ } }, 15000);
  }

  // ---- reports (administration)
  async function drawReports() {
    reports = await api.get("/api/messages/reports");
    page.replaceChildren(head(), reports.reports.length ? h("div", { class: "ms-reports" }, reports.reports.map((r) => h("div", { class: "panel ms-rep" + (r.status === "done" ? " done" : "") },
      h("div", { class: "row" }, h("b", {}, r.student_name || "—"), h("span", { class: "chip " + (r.kind === "parent_teacher" ? "" : "indigo") }, kindName(r.kind)), h("span", { class: "grow" }), h("span", { class: "muted small" }, clock(r.created_at))),
      h("blockquote", {}, h("div", { class: "ms-who" }, h("span", { class: "ms-role " + r.sender_role }, roleName(r.sender_role)), r.sender_name || ""), r.body, r.hidden ? h("em", { class: "muted" }, ` (${t("ms_hidden")})`) : null),
      r.reason ? h("p", { class: "muted" }, `${t("ms_reason")}: ${r.reason}`) : null,
      r.status === "open" ? h("div", { class: "row" },
        h("button", { class: "btn small", onClick: () => guarded(async () => { await api.post(`/api/reports/${r.id}/done`, {}); toast(t("ms_closed")); drawReports(); }) }, icon("check"), t("ms_keep")),
        h("button", { class: "btn small danger", onClick: () => guarded(async () => { await api.post(`/api/reports/${r.id}/done`, { hide: true }); toast(t("ms_closed")); drawReports(); }) }, icon("trash"), t("ms_hide_close"))) : h("span", { class: "chip green" }, t("ms_done"))))) : h("div", { class: "panel" }, h("p", { class: "muted" }, t("ms_reports_none"))));
  }

  draw();
  if (data.role === "admin" && data.connected) api.get("/api/messages/reports").then((r) => { reports = r; if (mode === "talks" && alive()) draw(); }).catch(() => {});
}
