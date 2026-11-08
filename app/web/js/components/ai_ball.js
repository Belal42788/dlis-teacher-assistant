import { h, icon, toast } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { chat as pageChat } from "../pages/chat.js";

// The floating AI ball: a small chat that is one press away on every page. It never sends student names (the server hides them),
// and "Open the full chat" hands the conversation over to the AI page.
const ball = { id: "", messages: [], busy: false, ready: null };

export function drawAiBall(host, goTo) {
  if (document.getElementById("ai-ball")) return;
  const log = h("div", { class: "ab-log", "aria-live": "polite" });
  const input = h("textarea", { rows: 1, class: "ab-input", placeholder: t("ab_ph"), "aria-label": t("ab_title"),
    onInput: () => grow(), onKeydown: (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } } });
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight + 2, 120) + "px"; };
  const sendBtn = h("button", { class: "btn primary icon", "aria-label": t("chat_send"), onClick: () => send() }, icon("send"));
  const off = h("div", { class: "ab-off", hidden: true }, h("p", {}, t("ab_off")), h("a", { class: "btn small primary", href: "#/help?open=ai", onClick: () => close() }, t("ab_how")));
  const panel = h("div", { class: "ab-panel", id: "ab-panel", role: "dialog", "aria-label": t("ab_title"), hidden: true },
    h("div", { class: "ab-head" }, h("b", {}, icon("spark"), " ", t("ab_title")), h("span", { class: "grow" }),
      h("button", { class: "btn small ghost", onClick: () => { if (!ball.busy) { ball.id = ""; ball.messages = []; draw(); input.focus(); } } }, t("ab_new")),
      h("button", { class: "btn small ghost", onClick: () => { pageChat.id = ball.id; pageChat.messages = ball.messages.slice(); close(); goTo("chat"); } }, t("ab_full")),
      h("button", { class: "btn icon ghost", "aria-label": t("close"), onClick: () => close() }, "✕")),
    log, off, h("div", { class: "ab-box" }, input, sendBtn));
  const btn = h("button", { class: "ai-ball", id: "ai-ball", type: "button", "aria-label": t("ab_title"), "aria-expanded": "false", "aria-controls": "ab-panel", title: t("ab_title"), onClick: () => (panel.hidden ? open() : close()) }, icon("spark"));

  function draw() {
    log.replaceChildren(...(ball.messages.length ? ball.messages.map((m) => h("div", { class: `bubble ${m.role}${m.error ? " err" : ""}` }, h("div", { class: "bubble-text" }, m.content),
      m.role === "assistant" && !m.error ? h("div", { class: "row small" }, h("button", { class: "btn small ghost", onClick: () => { navigator.clipboard?.writeText(m.content).then(() => toast(t("chat_copied")), () => {}); } }, icon("copy"), t("chat_copy"))) : null))
      : [h("div", { class: "chat-empty" }, icon("spark"), h("span", { class: "muted" }, t("ab_hint")))]),
      ball.busy ? h("div", { class: "bubble assistant muted" }, t("ai_writing")) : null);
    log.scrollTop = log.scrollHeight;
    sendBtn.disabled = ball.busy || ball.ready === false;
  }
  async function open() {
    panel.hidden = false; btn.setAttribute("aria-expanded", "true"); btn.classList.add("on");
    try { ball.ready = !!(await api.get("/api/ai")).ready; } catch { ball.ready = null; }
    off.hidden = ball.ready !== false; log.hidden = ball.ready === false; input.disabled = ball.ready === false;
    draw(); if (ball.ready !== false) input.focus();
  }
  function close() { panel.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.classList.remove("on"); }
  async function send() {
    const text = input.value.trim();
    if (!text || ball.busy || ball.ready === false) return;
    ball.messages = ball.messages.filter((m) => !m.error);
    ball.messages.push({ role: "user", content: text });
    input.value = ""; grow(); ball.busy = true; draw();
    try {
      const r = await api.post("/api/ai/chat", { messages: ball.messages.map(({ role, content }) => ({ role, content })) });
      ball.messages.push({ role: "assistant", content: r.reply });
    } catch (e) {
      ball.messages.push({ role: "assistant", content: e.friendly || e.message, error: true });
    } finally {
      ball.busy = false; draw();
      const body = { messages: ball.messages.filter((m) => !m.error), grade_id: "" };   // saved like any chat: it shows in the AI page list
      try { const s = await (ball.id ? api.put(`/api/chats/${ball.id}`, body) : api.post("/api/chats", body)); if (s && s.id) ball.id = s.id; } catch { /* saving is best-effort */ }
    }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) { close(); btn.focus(); } });
  host.append(panel, btn);
}

// On the AI page itself the ball is hidden (it would only repeat the page).
export function showAiBall(pageId) { const b = document.getElementById("ai-ball"); if (!b) return; b.hidden = pageId === "chat"; if (b.hidden) document.getElementById("ab-panel").hidden = true; }
