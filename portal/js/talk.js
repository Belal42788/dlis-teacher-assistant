"use strict";
// Messages: the conversations of the child (parents' talk and the student's talk), a chat with fast refresh, new message, and the report button.
import { h, clear, icon, t, api, me, fmtWhen, errText, toast } from "./core.js";
import { S, kid, kidName, teachers, threadsFor, markRead, MY_KIND } from "./data.js";

const kindLabel = (k) => (k === "parent_teacher" ? t("talkParent") : t("talkStudent"));
const kindNote = (k) => (k === "parent_teacher" ? t("talkParentNote") : t("talkStudentNote"));
const roleName = (r) => t(r) === r ? "" : t(r);
const initial = (s) => ([...(s || "?")][0] || "?").toUpperCase();

export async function viewMessages(box, ctx) {
  const k = kid();
  let data = await threadsFor(k), team = await teachers(k), sel = null, picking = false;
  const teacherOf = (th) => team.find((x) => x.id === th.teacher_id) || { id: th.teacher_id, name: "", subjects: [] };
  const teacherName = (th) => teacherOf(th).name || (data.last[th.id] && data.last[th.id].sender_role === "teacher" && data.last[th.id].sender_name) || t("teacher");
  const root = h("div", { class: "talk" }), side = h("div", { class: "threads card" }), pane = h("div", { class: "chat", style: "display:none" });
  root.append(side, pane); clear(box, root);

  const drawSide = () => {
    root.classList.toggle("open", !!sel || picking);
    clear(side, h("div", { class: "head" }, h("h2", {}, icon("talk"), t("messages")), h("span", { class: "grow" }), h("button", { class: "btn primary small", onclick: () => { picking = true; sel = null; drawSide(); drawPane(); } }, icon("plus"), t("newMsg"))),
      data.threads.length ? data.threads.map((th) => {
        const last = data.last[th.id], un = data.unread[th.id];
        return h("button", { class: "thread" + (un ? " unread" : ""), "aria-current": sel === th.id ? "true" : "false", onclick: () => { sel = th.id; picking = false; drawSide(); drawPane(); } },
          h("span", { class: "avatar" }, initial(teacherName(th))), h("span", { class: "tx" }, h("b", {}, teacherName(th), h("span", { class: "chip " + (th.kind === "parent_teacher" ? "" : "indigo") }, th.kind === "parent_teacher" ? t("parent") : t("student"))),
            h("small", {}, last ? last.body : "—")), un ? h("span", { class: "dot" }, "•") : null);
      }) : h("div", { class: "empty" }, icon("mail"), h("b", {}, t("noThreads")), h("span", {}, t("noThreadsText"))));
  };

  const drawPick = () => {
    pane.style.display = "";
    clear(pane, h("div", { class: "chat-head" }, h("button", { class: "btn ghost small", onclick: () => { picking = false; drawSide(); drawPane(); } }, icon("back"), t("back")), h("div", { class: "tx" }, h("b", {}, t("chooseTeacher")), h("small", {}, `${t("forWho")} ${kidName(k)} · ${S.role === "student" ? t("talkStudent") : t("talkParent")}`))),
      h("div", { class: "pick", style: "padding:.6rem" }, team.length ? team.map((m) => h("div", { class: "row", onclick: () => start(m) }, h("span", { class: "avatar" }, initial(m.name)), h("div", { class: "tx" }, h("b", {}, m.name || t("teacher")), h("small", {}, m.subjects.join("، "))), icon("chevron"))) : h("div", { class: "empty" }, h("b", {}, t("noTeachers")))));
  };
  async function start(m) {
    const have = data.threads.find((x) => x.teacher_id === m.id && x.kind === MY_KIND());
    if (have) { sel = have.id; picking = false; drawSide(); return drawPane(); }
    try {
      const made = await api("POST", "/rest/v1/threads?select=id,kind,teacher_id,last_at", { kind: MY_KIND(), teacher_id: m.id, student_code: k.code }, { Prefer: "return=representation" });
      data = await threadsFor(k); sel = made[0].id; picking = false; drawSide(); drawPane();
    } catch (e) { toast(errText(e), true); }
  }

  let stop = null;
  const drawPane = () => {
    if (stop) { stop(); stop = null; }
    if (picking) return drawPick();
    const th = data.threads.find((x) => x.id === sel);
    if (!th) { pane.style.display = "none"; return; }
    pane.style.display = "";
    const mine = th.kind === MY_KIND(), log = h("div", { class: "log", "aria-live": "polite" }), seen = new Set();
    const tn = teacherName(th), who = th.kind === "parent_teacher" ? t("parent") : t("student");
    const bubble = (m) => {
      const own = m.sender_id === me().uid, rn = roleName(m.sender_role), nm = m.sender_role === "teacher" || m.sender_role === "admin" ? (m.sender_name || tn) : "";
      const rep = h("div", { class: "report-box", hidden: true });
      const b = h("div", { class: "bubble" + (own ? " mine" : "") },
        h("div", { class: "who" }, h("span", { class: "r " + (m.sender_role || "") }, rn || "—"), own ? t("you") : nm),
        h("p", {}, m.body),
        h("div", { class: "meta" }, h("span", {}, fmtWhen(m.created_at)), own ? null : h("button", { onclick: () => { rep.hidden = !rep.hidden; } }, icon("flag"), t("report"))), rep);
      const why = h("input", { type: "text", maxlength: "200", placeholder: t("reportWhy") });
      rep.append(why, h("button", { class: "btn small", onclick: async () => {
        try { await api("POST", "/rest/v1/message_reports", { message_id: m.id, reason: why.value.trim() }); toast(t("reportDone")); rep.hidden = true; }
        catch (e) { toast(e.status === 409 ? t("reportAgain") : errText(e), true); }
      } }, t("reportSend")), h("button", { class: "btn ghost small", onclick: () => { rep.hidden = true; } }, t("cancel")));
      return b;
    };
    let last = "";
    const add = (rows) => {
      const near = log.scrollHeight - log.scrollTop - log.clientHeight < 80, fresh = rows.filter((m) => !seen.has(m.id));
      if (!fresh.length) return false;
      if (!seen.size) log.replaceChildren();
      fresh.forEach((m) => { seen.add(m.id); log.append(bubble(m)); last = m.created_at; });
      if (near || fresh.some((m) => m.sender_id === me().uid) || fresh.length === rows.length) log.scrollTop = log.scrollHeight;
      return fresh.some((m) => m.sender_id !== me().uid);
    };
    const text = h("textarea", { rows: "1", maxlength: "1000", placeholder: t("writeHere"), "aria-label": t("writeHere") });
    const send = async () => {
      const body = text.value.trim(); if (!body) return;
      text.disabled = true;
      try { const r = await api("POST", "/rest/v1/messages", { thread_id: th.id, body }, { Prefer: "return=representation" }); text.value = ""; add(r); data = await threadsFor(k); drawSide(); }
      catch (e) { toast(e instanceof Error && e.status ? t("sendFail") : errText(e), true); }
      text.disabled = false; text.focus();
    };
    text.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(); } });
    clear(pane,
      h("div", { class: "chat-head" }, h("button", { class: "btn ghost small only-phone", "aria-label": t("back"), onclick: () => { sel = null; drawSide(); drawPane(); } }, icon("back")), h("span", { class: "avatar" }, initial(tn)),
        h("div", { class: "tx" }, h("b", {}, tn), h("small", {}, teacherOf(th).subjects.join("، "))), h("span", { class: "chip " + (th.kind === "parent_teacher" ? "" : "indigo") }, kindLabel(th.kind))),
      h("div", { class: "note lock-note" }, icon("info"), kindNote(th.kind)),
      log,
      mine ? h("div", { class: "compose" }, text, h("button", { class: "btn primary", onclick: send }, icon("send"), t("sendBtn"))) : h("div", { class: "note lock-note" }, icon("lock"), t("readOnly").replace("{who}", who)),
      h("div", { class: "foot-note" }, icon("info"), t("watched")));
    log.append(h("div", { class: "empty" }, t("loading")));
    let busy = false;
    const pull = async (first) => {
      if (busy) return; busy = true;
      try {
        const rows = await api("GET", `/rest/v1/messages?select=id,sender_id,sender_role,sender_name,body,created_at&thread_id=eq.${th.id}${last ? "&created_at=gt." + encodeURIComponent(last) : ""}&order=created_at.asc&limit=300`);
        if (first && !rows.length) log.replaceChildren(h("div", { class: "empty" }, icon("mail"), h("b", {}, t("noMsgs"))));
        const incoming = add(rows);
        if (first || incoming) { await markRead(th.id).catch(() => {}); data.unread[th.id] = false; data.count = Object.values(data.unread).filter(Boolean).length; S.unread = Math.max(0, data.count); ctx.badge(); drawSide(); }
      } catch (e) { if (first) log.replaceChildren(h("div", { class: "note bad" }, errText(e))); }
      busy = false;
    };
    pull(true);
    const timer = setInterval(() => pull(false), 3000);
    stop = () => clearInterval(timer);
    ctx.onLeave(() => stop && stop());
  };

  drawSide(); drawPane();
  // the list itself refreshes now and then (new conversations, previews, the unread dots)
  const every = setInterval(async () => { try { const fresh = await threadsFor(k); data = fresh; S.unread = fresh.count; ctx.badge(); drawSide(); } catch { /* try again next time */ } }, 12000);
  ctx.onLeave(() => clearInterval(every));

}
