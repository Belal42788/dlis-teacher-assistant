"use strict";
// Shared helpers for the portal: the DOM builder, icons, the session, and the calls to the school server (Supabase).
// Everything a person can see is decided by the server's row-level security, never by this page.
export const CFG = window.PORTAL || {};

export function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
export const clear = (el, ...kids) => { el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false).map((k) => (k.nodeType ? k : document.createTextNode(String(k))))); return el; };
export const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

const ICONS = {
  home: '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10M10 20v-5h4v5"/>',
  study: '<path d="M3 7l9-4 9 4-9 4z"/><path d="M7 9.5V15c0 1.4 2.2 3 5 3s5-1.6 5-3V9.5"/><path d="M21 7v6"/>',
  talk: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
  week: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 3v3M16 3v3M8 14h.01M12 14h.01M16 14h.01"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  grades: '<path d="M5 20V10M12 20V4M19 20v-7"/>',
  news: '<path d="M3 10v4h3l7 4V6L6 10z"/><path d="M16 9a4 4 0 010 6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.5 7.5l8.5 6 8.5-6"/>',
  user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.6-4 3.5-6 7-6s6.4 2 7 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  send: '<path d="M4 12l16-8-6 16-3-7z"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  chevron: '<path d="M9 5l7 7-7 7"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  slides: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  quiz: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  revision: '<path d="M4 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H4zM20 5h-6a3 3 0 0 0-3 3"/><path d="M20 5v13h-7"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  logout: '<path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  cal: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 3v3M16 3v3M9 15l2 2 4-4"/>',
  gear: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
};
export function icon(name) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", name === "back" || name === "chevron" || name === "send" ? "i dir" : "i"); s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name] || ""; return s;
}

// ---------------------------------------------------------------- text size (kept on this device)
export const SIZES = [0.9, 1, 1.15, 1.3];
export const getSize = () => { try { const n = localStorage.getItem("size"); return n === null ? 1 : Math.min(SIZES.length - 1, Math.max(0, +n || 0)); } catch { return 1; } };
export function setSize(i) { document.documentElement.style.setProperty("--fs", SIZES[i]); try { localStorage.setItem("size", i); } catch { /* private window */ } }
// the last email typed to sign in, so the next sign in only needs the password
export const lastEmail = { get() { try { return localStorage.getItem("email") || ""; } catch { return ""; } }, set(v) { try { localStorage.setItem("email", v); } catch { /* private window */ } } };

// ---------------------------------------------------------------- language
export const state = { lang: (() => { try { return localStorage.getItem("lang") || "ar"; } catch { return "ar"; } })(), dict: { ar: {}, en: {} } };
export const t = (k) => { const v = state.dict[state.lang][k]; return v === undefined ? k : v; };
export const setLang = (l) => { state.lang = l; try { localStorage.setItem("lang", l); } catch { /* private window */ } document.documentElement.lang = l; document.documentElement.dir = l === "ar" ? "rtl" : "ltr"; };
const loc = () => (state.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");
export const fmtDay = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString(loc(), { day: "numeric", month: "short" }); };
export const fmtTime = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleTimeString(loc(), { hour: "numeric", minute: "2-digit", hour12: true }); };
export const fmtWhen = (iso) => { const d = new Date(iso); if (isNaN(d)) return ""; const same = d.toDateString() === new Date().toDateString(); return same ? fmtTime(iso) : `${fmtDay(iso)} ${fmtTime(iso)}`; };

// ---------------------------------------------------------------- session + server calls
export class NetErr extends Error {}
const mem = {};
export const store = {
  get() { try { return JSON.parse(localStorage.getItem("sess") || "null"); } catch { return mem.sess || null; } },
  set(v) { mem.sess = v; try { v ? localStorage.setItem("sess", JSON.stringify(v)) : localStorage.removeItem("sess"); } catch { /* private window: kept in memory */ } },
};
export async function raw(method, path, body, token, extra) {
  if (!CFG.url || !CFG.key) throw new Error("notSet");
  let res;
  try {
    res = await fetch(CFG.url + path, { method, headers: { apikey: CFG.key, "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}), ...(extra || {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new NetErr(); }
  const text = await res.text(); let data = null; try { data = text ? JSON.parse(text) : null; } catch { /* not json */ }
  if (!res.ok) { const e = new Error((data && (data.msg || data.message || data.error_description)) || "error"); e.status = res.status; e.code = (data && (data.error_code || data.code)) || ""; throw e; }
  return data;
}
const jwtSub = (tok) => { try { return JSON.parse(atob(tok.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).sub || ""; } catch { return ""; } };
export async function auth(path, body) {
  const j = await raw("POST", "/auth/v1/" + path, body);
  if (j && j.access_token) store.set({ access: j.access_token, refresh: j.refresh_token, exp: Date.now() + (j.expires_in || 3000) * 1000 - 60000, uid: jwtSub(j.access_token), email: (j.user && j.user.email) || (store.get() || {}).email || "" });
  return j;
}
export async function token() {
  const s = store.get(); if (!s) throw new Error("signedout");
  if (Date.now() < s.exp) return s.access;
  try { await auth("token?grant_type=refresh_token", { refresh_token: s.refresh }); } catch (e) { if (e instanceof NetErr) throw e; store.set(null); throw new Error("signedout"); }
  return store.get().access;
}
export const api = async (method, path, body, extra) => raw(method, path, body, await token(), extra);
export const me = () => store.get() || {};
export const errText = (e) => (e instanceof NetErr ? t("net") : e.message === "notSet" ? t("notSet") : e.message);

// ---------------------------------------------------------------- small pieces
export function toast(text, bad) {
  let box = document.getElementById("toasts"); if (!box) { box = h("div", { id: "toasts", "aria-live": "polite" }); document.body.append(box); }
  const n = h("div", { class: "toast" + (bad ? " bad" : "") }, text); box.append(n); setTimeout(() => n.remove(), 3500);
}
export const say = (box, text, bad) => clear(box, h("div", { class: "note" + (bad ? " bad" : "") }, text));
