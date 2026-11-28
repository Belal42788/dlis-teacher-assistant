"use strict";
// The family portal: sign in, then Home / Study / Talk. One page, no build step.
import { h, clear, icon, t, state, setLang, raw, api, auth, store, me, NetErr, errText, say, toast, CFG } from "./core.js";
import "./i18n.js";
import { S, kid, kidName, loadAccount, forget, refreshUnread } from "./data.js";
import { viewHome, viewWeek, viewFiles, viewGrades, viewNews } from "./study.js";
import { viewMessages } from "./talk.js";
import { viewCalendar } from "./calendar.js";
import { lastSeen, isNew } from "./fresh.js";
import { pubs, news } from "./data.js";

const app = document.getElementById("app");
const NAV = [["home", "home"], ["study", "study"], ["talk", "talk"]];
const SUBS = { study: [["week", "week"], ["files", "folder"], ["grades", "grades"], ["calendar", "cal"]], talk: [["messages", "mail"], ["news", "news"]] };
const route = { tab: "home", sub: { study: "week", talk: "messages" } };
let leave = [], poll = null;
const onLeave = (fn) => leave.push(fn);
const stopAll = () => { leave.forEach((f) => f()); leave = []; };
const dot = () => h("span", { class: "dot", "data-b": "1", hidden: !S.unread }, S.unread);
const fresh = (name) => h("span", { class: "dot new", "data-n": name, hidden: true });
// the green numbers for what was published since this device last opened Files / Announcements
async function paintNew() {
  if (!S.kids.length) return;
  const k = kid(), set = (name, n) => document.querySelectorAll(`[data-n="${name}"]`).forEach((b) => { b.textContent = n; b.hidden = !n; });
  try {
    const [files, notes] = await Promise.all([pubs(k), news()]);
    const nf = files.filter((p) => isNew(p, lastSeen(k.code, "files"))).length, nn = notes.filter((a) => isNew(a, lastSeen("all", "news"))).length;
    set("files", nf); set("study", nf); set("news", nn);
  } catch { /* the marks are a courtesy: no marks if the server is slow */ }
}
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
        try { const r = await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); if (typeof r === "string" && r.startsWith("!")) S.flash = r === "!locked" ? t("locked") : t("badCode"); } catch (e) { S.flash = e instanceof NetErr ? t("net") : t("badCode"); }
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

// ---------------------------------------------------------------- the link in the "forgot password" email
// The email opens this page with #access_token=...&type=recovery in the address; we keep that session only to set the new password.
function newPasswordScreen(access, refresh, expires) {
  stopAll(); clearInterval(poll); setTitle();
  const p1 = h("input", { type: "password", autocomplete: "new-password", dir: "ltr", id: "np1" }), p2 = h("input", { type: "password", autocomplete: "new-password", dir: "ltr", id: "np2" }), msg = h("div", {});
  const form = h("form", { class: "card", onsubmit: async (ev) => {
    ev.preventDefault();
    if (p1.value.length < 8) return say(msg, t("pw8"), true);
    if (p1.value !== p2.value) return say(msg, t("passDiff"), true);
    try { await raw("PUT", "/auth/v1/user", { password: p1.value }, access); await auth("token?grant_type=refresh_token", { refresh_token: refresh }); toast(t("passSaved")); boot(); } catch (e) { say(msg, e.status === 401 || e.status === 403 ? t("linkOld") : errText(e), true); }
  } }, h("h1", {}, t("newPassTitle")), h("p", { class: "lead" }, t("newPassLead")),
    h("label", { class: "f", for: "np1" }, t("newPass")), p1, h("label", { class: "f", for: "np2" }, t("newPass2")), p2, msg, h("button", { class: "btn primary", type: "submit" }, t("savePass")));
  clear(app, h("div", { class: "top" }, h("div", { class: "brand" }, h("span", { class: "mark" }, h("img", { src: "img/logo-mark.png", alt: "" })), h("div", {}, h("b", {}, t("app")), h("small", {}, school())))),
    h("main", {}, h("div", { class: "login" }, h("img", { class: "logo", src: "img/logo.png", alt: "DLIS" }), form)));
  store.set({ access, refresh, exp: Date.now() + (expires || 3000) * 1000 - 60000, uid: "", email: "" });
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
    kids.length ? h("nav", { class: "tabs", role: "tablist" }, NAV.map(([id, ic]) => h("button", { class: "tab", role: "tab", "aria-selected": route.tab === id ? "true" : "false", onclick: () => go(id) }, icon(ic), t(id), id === "talk" ? dot() : id === "study" ? fresh("study") : null))) : h("span", { class: "grow tabs" }),
    h("div", { class: "tools" }, who, h("button", { class: "pill role" + (S.role === "student" ? " student" : ""), title: t("account"), onclick: () => go("account") }, icon("user"), S.role === "student" ? t("student") : t("parent")),
      h("button", { class: "pill", id: "lang", onclick: () => { setLang(state.lang === "ar" ? "en" : "ar"); render(); } }, t("lang"))));
}
function subBar() {
  const subs = SUBS[route.tab]; if (!subs) return null;
  return h("nav", { class: "sub" }, subs.map(([id, ic]) => h("button", { "aria-current": route.sub[route.tab] === id ? "page" : "false", onclick: () => go(route.tab, id) }, icon(ic), t(id), id === "messages" ? dot() : id === "files" ? fresh("files") : id === "news" ? fresh("news") : null)));
}
const addKidBox = () => {
  const code = h("input", { type: "text", dir: "ltr", autocapitalize: "characters", placeholder: "XXXX-XXXX", "aria-label": t("code") }), msg = h("div", {});
  return h("div", { class: "card" }, h("h2", {}, icon("plus"), t("addKid")), h("p", { class: "muted" }, S.kids.length ? t("addKidText") : t("noKids")), code, msg,
    h("button", { class: "btn primary", style: "margin-top:.6rem", onclick: async () => { try { const r = await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); if (typeof r === "string" && r.startsWith("!")) return say(msg, r === "!locked" ? t("locked") : t("badCode"), true); forget(); S.flash = ""; await loadAccount(); render(); } catch (e) { say(msg, e instanceof NetErr ? t("net") : t("badCode"), true); } } }, t("add")));
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
    if (route.tab === "home") { await refreshUnread(); paintBadge(); await viewHome(body, go); return paintNew(); }
    const view = { week: viewWeek, files: viewFiles, grades: viewGrades, messages: viewMessages, news: viewNews, calendar: viewCalendar }[route.sub[route.tab]];
    await view(body, ctx); paintNew();
  } catch (e) {
    if (e.message === "signedout") return loginScreen(false);
    clear(body, h("div", { class: "note bad" }, errText(e)), h("button", { class: "btn", onclick: () => { forget(); render(); } }, t("retry")));
  }
}

const bootScreen = () => h("div", { class: "boot" }, h("img", { src: "img/logo-mark.png", alt: "" }), h("span", {}, "DLIS"), h("i", {}));
async function boot() {
  clear(app, bootScreen());
  try { await loadAccount(); } catch (e) { if (e.message === "signedout") return loginScreen(false); return clear(app, h("main", {}, h("div", { class: "note bad" }, errText(e)), h("button", { class: "btn", onclick: boot }, t("retry")))); }
  if (S.role !== "parent" && S.role !== "student") { store.set(null); return loginScreen(false, t("staffAccount")); }
  route.tab = "home";
  render();
  clearInterval(poll); poll = setInterval(async () => { if (!store.get() || document.hidden) return; await refreshUnread().catch(() => {}); paintBadge(); paintNew(); }, 20000);
}

setLang(state.lang);
const link = new URLSearchParams(location.hash.replace(/^#/, ""));
if (link.get("type") === "recovery" && link.get("access_token")) {
  const [a, r, e] = [link.get("access_token"), link.get("refresh_token"), +link.get("expires_in")];
  history.replaceState(null, "", location.pathname + location.search); newPasswordScreen(a, r, e);
} else if (link.get("error_code") || link.get("error")) { history.replaceState(null, "", location.pathname + location.search); loginScreen(false, t("linkOld")); }
else if (store.get()) boot(); else loginScreen(false);
