"use strict";
// The family portal: sign in, then Home / Study / Talk. One page, no build step.
import { h, clear, icon, t, state, setLang, api, raw, auth, store, me, NetErr, errText, say, CFG } from "./core.js";
import "./i18n.js";
import { S, kid, kidName, loadAccount, forget, refreshUnread } from "./data.js";
import { viewHome, viewWeek, viewFiles, viewGrades, viewNews } from "./study.js";
import { viewMessages } from "./talk.js";

const app = document.getElementById("app");
const NAV = [["home", "home"], ["study", "study"], ["talk", "talk"]];
const SUBS = { study: [["week", "week"], ["files", "folder"], ["grades", "grades"]], talk: [["messages", "mail"], ["news", "news"]] };
const route = { tab: "home", sub: { study: "week", talk: "messages" } };
let leave = [], poll = null;
const onLeave = (fn) => leave.push(fn);
const stopAll = () => { leave.forEach((f) => f()); leave = []; };
const dot = () => h("span", { class: "dot", "data-b": "1", hidden: !S.unread }, S.unread);
const paintBadge = () => document.querySelectorAll("[data-b]").forEach((b) => { b.textContent = S.unread; b.hidden = !S.unread; });
const school = () => (state.lang === "ar" ? CFG.schoolAr : CFG.schoolEn) || t("school");

function setTitle() { document.title = `DLIS · ${t("app")}`; }

// ---------------------------------------------------------------- sign in / sign up
function loginScreen(signup, note) {
  stopAll(); clearInterval(poll); setTitle();
  const em = h("input", { type: "email", autocomplete: "username", dir: "ltr", id: "em" }), pw = h("input", { type: "password", autocomplete: signup ? "new-password" : "current-password", dir: "ltr", id: "pw" });
  const code = h("input", { type: "text", dir: "ltr", autocapitalize: "characters", autocomplete: "off", placeholder: "XXXX-XXXX", id: "cd" });
  const msg = h("div", {}); if (note) say(msg, note, true);
  const go = async () => {
    try {
      if (signup) {
        if (pw.value.length < 8) return say(msg, t("pw8"), true);
        if (!code.value.trim()) return say(msg, t("badCode"), true);
        await auth("signup", { email: em.value.trim(), password: pw.value });
        if (!store.get()) await auth("token?grant_type=password", { email: em.value.trim(), password: pw.value });
        try { await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); } catch (e) { S.flash = e instanceof NetErr ? t("net") : t("badCode"); }
      } else await auth("token?grant_type=password", { email: em.value.trim(), password: pw.value });
      boot();
    } catch (e) { say(msg, signup && e.status === 422 ? e.message : e.code === "email_not_confirmed" ? t("unconfirmed") : e.status === 429 || /rate_limit/.test(e.code) ? t("rate") : e.status === 400 || e.status === 401 ? t("badLogin") : errText(e), true); }
  };
  const form = h("form", { class: "card", onsubmit: (ev) => { ev.preventDefault(); go(); } },
    h("h1", {}, signup ? t("signup") : t("login")), h("p", { class: "lead" }, t("welcomeText")),
    h("label", { class: "f", for: "em" }, t("email")), em, h("label", { class: "f", for: "pw" }, t("pass")), pw,
    signup ? [h("label", { class: "f", for: "cd" }, t("code")), code, h("div", { class: "hint" }, t("codeHint"))] : null, msg,
    h("button", { class: "btn primary", type: "submit" }, signup ? t("signup") : t("login")),
    h("div", { class: "links" }, h("button", { type: "button", class: "link", onclick: () => loginScreen(!signup) }, signup ? t("haveAcc") : t("noAcc")),
      signup ? null : h("button", { type: "button", class: "link", onclick: async () => { if (!em.value.trim()) return; try { await raw("POST", "/auth/v1/recover", { email: em.value.trim() }); } catch { /* same message either way */ } say(msg, t("sent")); } }, t("forgot"))));
  clear(app, h("div", { class: "top" }, h("div", { class: "brand" }, h("span", { class: "mark" }, h("img", { src: "img/logo-mark.png", alt: "" })), h("div", {}, h("b", {}, t("app")), h("small", {}, school()))), h("span", { class: "grow" }),
    h("button", { class: "pill", id: "lang", onclick: () => { setLang(state.lang === "ar" ? "en" : "ar"); loginScreen(signup); } }, t("lang"))),
    h("main", {}, h("div", { class: "login" }, h("img", { class: "logo", src: "img/logo.png", alt: "DLIS" }), form)));
}

// ---------------------------------------------------------------- the page after sign in
function signOut() { store.set(null); forget(); S.kids = []; S.role = ""; S.cur = 0; loginScreen(false); }
function go(tab, sub) { route.tab = tab; if (sub) route.sub[tab] = sub; render(); window.scrollTo(0, 0); }

function topBar() {
  const kids = S.kids;
  const who = kids.length > 1 ? h("select", { class: "pill", "aria-label": t("children"), onchange: (ev) => { S.cur = +ev.target.value; forget(); render(); } }, kids.map((k, i) => h("option", { value: i, selected: i === S.cur }, kidName(k))))
    : kids.length ? h("span", { class: "pill" }, icon("user"), kidName(kid())) : null;
  return h("header", { class: "top" },
    h("div", { class: "brand" }, h("span", { class: "mark" }, h("img", { src: "img/logo-mark.png", alt: "" })), h("div", {}, h("b", {}, t("app")), h("small", {}, school()))),
    kids.length ? h("nav", { class: "tabs", role: "tablist" }, NAV.map(([id, ic]) => h("button", { class: "tab", role: "tab", "aria-selected": route.tab === id ? "true" : "false", onclick: () => go(id) }, icon(ic), t(id), id === "talk" ? dot() : null))) : h("span", { class: "grow tabs" }),
    h("div", { class: "tools" }, who, h("button", { class: "pill role" + (S.role === "student" ? " student" : ""), title: t("account"), onclick: () => go("account") }, icon("user"), S.role === "student" ? t("student") : t("parent")),
      h("button", { class: "pill", id: "lang", onclick: () => { setLang(state.lang === "ar" ? "en" : "ar"); render(); } }, t("lang"))));
}
function subBar() {
  const subs = SUBS[route.tab]; if (!subs) return null;
  return h("nav", { class: "sub" }, subs.map(([id, ic]) => h("button", { "aria-current": route.sub[route.tab] === id ? "page" : "false", onclick: () => go(route.tab, id) }, icon(ic), t(id), id === "messages" ? dot() : null)));
}
const addKidBox = () => {
  const code = h("input", { type: "text", dir: "ltr", autocapitalize: "characters", placeholder: "XXXX-XXXX", "aria-label": t("code") }), msg = h("div", {});
  return h("div", { class: "card" }, h("h2", {}, icon("plus"), t("addKid")), h("p", { class: "muted" }, S.kids.length ? t("addKidText") : t("noKids")), code, msg,
    h("button", { class: "btn primary", style: "margin-top:.6rem", onclick: async () => { try { await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); forget(); S.flash = ""; await loadAccount(); render(); } catch (e) { say(msg, e instanceof NetErr ? t("net") : t("badCode"), true); } } }, t("add")));
};
function account(box) {
  const s = me();
  clear(box, h("div", { class: "card" }, h("h2", {}, icon("user"), t("account")), h("p", {}, t("signedAs"), " ", h("b", { dir: "ltr" }, s.email || "—"), " ", h("span", { class: "chip " + (S.role === "student" ? "indigo" : "green") }, S.role === "student" ? t("studentAcc") : t("parentAcc"))),
    S.kids.length ? [h("div", { class: "sec" }, S.role === "student" ? t("myself") : t("children")), S.kids.map((k) => h("div", { class: "row" }, h("span", { class: "avatar" }, kidName(k)[0] || "?"), h("div", { class: "tx" }, h("b", {}, kidName(k)))))] : null,
    h("button", { class: "btn", style: "margin-top:.8rem", onclick: signOut }, icon("logout"), t("out"))),
    S.role === "parent" ? addKidBox() : null);
}

async function render() {
  stopAll(); setTitle();
  const body = h("main", {}, h("p", { class: "muted" }, t("loading")));
  clear(app, topBar(), subBar(), body);
  try {
    if (!S.kids.length && S.role === "parent") { clear(body, S.flash ? h("div", { class: "note bad" }, S.flash) : null, addKidBox()); if (route.tab === "account") account(body); return; }
    const ctx = { onLeave, badge: paintBadge };
    if (route.tab === "account") return account(body);
    if (route.tab === "home") { await refreshUnread(); paintBadge(); return await viewHome(body, go); }
    const view = { week: viewWeek, files: viewFiles, grades: viewGrades, messages: viewMessages, news: viewNews }[route.sub[route.tab]];
    await view(body, ctx);
  } catch (e) {
    if (e.message === "signedout") return loginScreen(false);
    clear(body, h("div", { class: "note bad" }, errText(e)), h("button", { class: "btn", onclick: () => { forget(); render(); } }, t("retry")));
  }
}

async function boot() {
  clear(app, h("main", {}, h("p", { class: "muted" }, t("loading"))));
  try { await loadAccount(); } catch (e) { if (e.message === "signedout") return loginScreen(false); return clear(app, h("main", {}, h("div", { class: "note bad" }, errText(e)), h("button", { class: "btn", onclick: boot }, t("retry")))); }
  if (S.role !== "parent" && S.role !== "student") { store.set(null); return loginScreen(false, t("staffAccount")); }
  route.tab = "home";
  render();
  clearInterval(poll); poll = setInterval(async () => { if (!store.get() || document.hidden) return; await refreshUnread().catch(() => {}); paintBadge(); }, 20000);
}

setLang(state.lang);
if (store.get()) boot(); else loginScreen(false);
