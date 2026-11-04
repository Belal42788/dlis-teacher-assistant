import { h, icon, toast, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { gradeName, roomLabel } from "../labels.js";
import { state } from "../state.js";
import { sourcePicker } from "../components/source_pick.js";

// The open conversation stays here while the teacher visits other tabs; every conversation is also saved in the data folder.
const chat = { id: "", messages: [], busy: false, student: null };  // student: { ar, en } chosen for a parent message

export async function renderChat(root) {
  const [ai, structure, pr] = await Promise.all([api.get("/api/ai"), api.get("/api/structure"), api.get("/api/ai/prompts")]);
  const lang = getLang();
  let prompts = pr;
  const src = await sourcePicker((id) => { srcBtn && srcBtn.classList.toggle("has", !!id); }, { exact: true, pagesOnly: true });

  const gradeSel = h("select", { "aria-label": t("chat_grade") }, h("option", { value: "" }, t("chat_any_grade")),
    structure.grades.map((g) => h("option", { value: g.id }, gradeName(g))));
  const input = h("textarea", { rows: 1, class: "chat-input", onInput: () => grow(), onKeydown: (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } } });
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight + 2, window.innerHeight * 0.4) + "px"; };
  const log = h("div", { class: "chat-log", "aria-live": "polite" });
  const sendBtn = h("button", { class: "btn primary", disabled: !ai.ready, onClick: () => send() }, icon("spark"), t("chat_send"));

  function drawLog() {
    if (!chat.messages.length) {
      log.replaceChildren(h("div", { class: "chat-empty" }, icon("spark")));
    } else {
      log.replaceChildren(...chat.messages.map((m) => h("div", { class: `bubble ${m.role}${m.error ? " err" : ""}` },
        h("div", { class: "bubble-text" }, m.content),
        m.role === "assistant" && !m.error ? h("div", { class: "row small" },
          h("button", { class: "btn small ghost", onClick: () => { navigator.clipboard?.writeText(m.content).then(() => toast(t("chat_copied")), () => {}); } }, icon("copy"), t("chat_copy")),
          h("button", { class: "btn small ghost", onClick: () => { input.value = m.content; grow(); input.focus(); } }, t("chat_edit_reply")),
          /\[student\]/i.test(m.content) && chat.student ? h("button", { class: "btn small", onClick: () => {
            const name = /[\u0600-\u06FF]/.test(m.content) ? chat.student.ar : chat.student.en || chat.student.ar;
            navigator.clipboard?.writeText(m.content.replace(/\[student\]/gi, name)).then(() => toast(t("pm_copied")), () => {});
          } }, icon("copy"), t("pm_name_copy")) : null) : null)),
        chat.busy ? h("div", { class: "bubble assistant muted" }, t("ai_writing")) : null);
    }
    log.scrollTop = log.scrollHeight;
    sendBtn.disabled = !ai.ready || chat.busy;
  }

  async function send() {
    const text = input.value.trim();
    if (!text || chat.busy || !ai.ready) return;
    chat.messages = chat.messages.filter((m) => !m.error);
    chat.messages.push({ role: "user", content: text });
    input.value = ""; grow(); chat.busy = true; drawLog();
    try {
      const r = await api.post("/api/ai/chat", { messages: chat.messages.map(({ role, content }) => ({ role, content })), grade_id: gradeSel.value, ...(src && src.value() ? { source_id: src.value(), ...src.extra() } : {}) });
      chat.messages.push({ role: "assistant", content: r.reply });
    } catch (e) {
      chat.messages.push({ role: "assistant", content: e.friendly || e.message, error: true });
    } finally { chat.busy = false; drawLog(); saveChat(); }
  }

  // ---------- ready-made requests: pick what you need (chips), write the topic, the request is written in the box below
  let tplId = null;
  const topic = h("input", { type: "text", placeholder: t("chat_topic_ph"), onInput: () => build() });
  const chips = h("div", { class: "chips", role: "group", "aria-label": t("chat_builder") });
  function build() {
    const tpl = prompts.templates.find((x) => x.id === tplId);
    if (!tpl) return;
    const g = structure.grades.find((x) => x.id === gradeSel.value);
    input.value = tpl.text
      .replaceAll("{topic}", topic.value.trim() || "…")
      .replaceAll("{grade}", g ? gradeName(g).replace(/^.*?(Grade|الصف)/, "$1") : "school")
      .replaceAll("{subject}", state.settings?.subject || "")
      .replace(/\s{2,}/g, " ").trim();
    grow();
  }
  function drawChips() {
    chips.replaceChildren(...prompts.templates.map((x) => h("button", { type: "button", class: `chip${x.id === tplId ? " on" : ""}`,
      onClick: () => { tplId = x.id; drawChips(); build(); if (x.id === "free") input.focus(); else topic.focus(); } }, x[lang === "ar" ? "ar" : "en"] || x.en)));
  }
  drawChips();
  const builderBody = h("div", {}, chips, h("label", { class: "field" }, h("span", { class: "label" }, t("chat_topic")), topic));

  // ---------- message to a parent: the AI never sees the name, it writes [student] and the name is put in here
  const pmRoom = h("select", { "aria-label": t("ch_class"), onChange: () => loadStudents() }, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const pmStudent = h("select", { "aria-label": t("students"), onChange: () => pickStudent() });
  const pmLang = h("select", {}, h("option", { value: "ar" }, "العربية"), h("option", { value: "en" }, "English")); pmLang.value = lang === "ar" ? "ar" : "en";
  const pmWhy = h("select", {}, ["praise", "concern", "absence", "homework", "behaviour", "meeting"].map((k) => h("option", { value: k }, t(`pm_${k}`))));
  const pmNote = h("input", { type: "text", placeholder: t("pm_note_ph") });
  let pmData = { names: [], english: [], auto: [] };
  const pickStudent = () => { const i = +pmStudent.value; chat.student = isNaN(i) || !pmData.names[i] ? null : { ar: pmData.names[i], en: pmData.english[i] || pmData.auto[i] || "" }; };
  async function loadStudents() {
    if (!pmRoom.value) return;
    pmData = await guarded(() => api.get(`/api/rooms/${pmRoom.value}/students`)) || pmData;
    pmStudent.replaceChildren(h("option", { value: "" }, "—"), ...pmData.names.map((n, i) => h("option", { value: i }, n)));
    chat.student = null;
  }
  const pmBtn = h("button", { class: "btn primary", disabled: !ai.ready, onClick: () => {
    if (!chat.student) { toast(t("pm_pick_student"), "error"); return; }
    const why = { praise: "praise the child for good work or progress", concern: "share a gentle concern about the child's progress and ask to work together", absence: "ask about the child's absence and how to help catching up",
      homework: "remind about missing homework", behaviour: "talk about the child's behaviour in class in a kind, constructive way", meeting: "invite the parent to a meeting" }[pmWhy.value];
    const r = structure.rooms.find((x) => x.id === pmRoom.value);
    input.value = `Write a short, warm and polite message from the teacher to the parent of [student] (class ${r ? r.name : ""}). Purpose: ${why}. ${pmNote.value.trim() ? "Details: " + pmNote.value.trim() + ". " : ""}Write it in ${pmLang.value === "ar" ? "Arabic" : "English"}. Use exactly the placeholder [student] for the child's name. Do not invent facts.`;
    send();
  } }, icon("spark"), t("pm_write"));
  const parentBox = structure.rooms.length ? true : null;
  const parentBody = !parentBox ? null : h("div", {}, h("p", { class: "muted small" }, t("pm_lead")),
    h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("ch_class")), pmRoom), h("label", { class: "field" }, h("span", { class: "label" }, t("students")), pmStudent)),
    h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("pm_why")), pmWhy), h("label", { class: "field" }, h("span", { class: "label" }, t("pm_lang")), pmLang)),
    h("label", { class: "field" }, h("span", { class: "label" }, t("pm_note")), pmNote), h("div", { class: "row" }, pmBtn));
  loadStudents();

  // ---------- saved chats (like Claude): a list on the side, every conversation is kept
  const histBox = h("div", { class: "chat-hist" });
  let chats = [];
  async function loadChats() { const r = await guarded(() => api.get("/api/chats")); chats = r ? r.items : []; drawHist(); }
  function drawHist() {
    histBox.replaceChildren(...chats.map((c) => h("div", { class: `chat-item${c.id === chat.id ? " on" : ""}` },
      h("button", { class: "chat-open", dir: "auto", title: c.title, onClick: () => openChat(c.id) }, c.title || t("chat_untitled")),
      h("button", { class: "btn icon ghost chat-del", "aria-label": t("remove"), onClick: async () => {
        if (!(await confirmBox(t("chat_del_confirm")))) return;
        const r = await guarded(() => api.post(`/api/chats/${c.id}/delete`, {})); if (!r) return;
        chats = r.items; if (chat.id === c.id) newChat(); else drawHist();
      } }, icon("trash")))));
  }
  async function saveChat() {
    const body = { messages: chat.messages.filter((m) => !m.error), grade_id: gradeSel.value };
    const r = await guarded(() => chat.id ? api.put(`/api/chats/${chat.id}`, body) : api.post("/api/chats", body));
    if (r) { chat.id = r.id; await loadChats(); }
  }
  async function openChat(id) {
    if (chat.busy) return;
    const c = await guarded(() => api.get(`/api/chats/${id}`)); if (!c) return;
    chat.id = c.id; chat.messages = c.messages || []; gradeSel.value = c.grade_id || ""; chat.student = null;
    drawLog(); drawHist(); input.focus();
  }
  function newChat() { if (chat.busy) return; chat.id = ""; chat.messages = []; input.value = ""; grow(); drawLog(); drawHist(); input.focus(); }

  // ---------- the two helpers sit in a small tray above the box
  let tray = "";
  const trayBox = h("div", { class: "chat-tray", hidden: true });
  const trayBtn = (id, label) => h("button", { type: "button", class: "chat-tool", "data-tray": id, onClick: () => { tray = tray === id ? "" : id; drawTray(); } }, icon("spark"), label);
  const srcBtn = src ? trayBtn("source", t("chat_src")) : null;
  if (srcBtn) srcBtn.classList.toggle("has", !!src.value());
  const srcBody = src ? h("div", {}, h("p", { class: "muted small" }, t("chat_src_hint")), src.el) : null;
  const tools = h("div", { class: "chat-tools" }, trayBtn("builder", t("chat_builder")), parentBox ? trayBtn("parent", t("pm_title")) : null, srcBtn);
  function drawTray() {
    tools.querySelectorAll(".chat-tool").forEach((b) => b.classList.toggle("on", b.dataset.tray === tray));
    trayBox.hidden = !tray;
    trayBox.replaceChildren(...(tray === "builder" ? [builderBody] : tray === "parent" && parentBox ? [parentBody] : tray === "source" && srcBody ? [srcBody] : []));
  }

  sendBtn.replaceChildren(icon("send"));
  sendBtn.classList.add("chat-send"); sendBtn.setAttribute("aria-label", t("chat_send"));
  const composer = h("div", { class: "chat-composer" }, tools, trayBox, h("div", { class: "chat-box" }, input, sendBtn));

  root.replaceChildren(h("div", { class: "page chat-page" },
    ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", {}, h("a", { href: "#/settings" }, t("ai_setup_link")))),
    h("div", { class: "chat-app" },
      h("aside", { class: "chat-side" }, h("button", { class: "btn primary chat-new", onClick: newChat }, icon("plus"), t("chat_new")), histBox),
      h("section", { class: "chat-main" },
        h("div", { class: "chat-top" }, h("h1", {}, t("nav_chat")), h("label", { class: "chat-grade" }, gradeSel)),
        log, composer))));
  drawLog(); grow(); drawTray(); loadChats();
}
