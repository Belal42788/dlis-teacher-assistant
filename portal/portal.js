"use strict";
// DLIS parents' portal: sign in, link a child with the activation code, then see grades, shared files, the week plan and announcements.
// Everything the parent can see is decided by the school server (row-level security), not by this page.
const CFG = window.PORTAL || {};
const T = {
  ar: { brand: "بوابة أولياء الأمور · DLIS", login: "تسجيل الدخول", signup: "إنشاء حساب", email: "الإيميل", pass: "كلمة السر", code: "كود الطالب (من المدرسة)", haveAcc: "عندي حساب", noAcc: "أول مرة؟ أنشئ حساب", forgot: "نسيت كلمة السر", sent: "اتبعتلك رابط على الإيميل لو الحساب موجود.", out: "خروج", lang: "English",
    badLogin: "الإيميل أو كلمة السر مش صح.", badCode: "الكود مش صح أو اتستخدم قبل كده. اطلب كود جديد من المدرسة.", net: "مش قادر أوصل للسيرفر. اتأكد من النت.", notSet: "البوابة لسه ما اتظبطتش (عنوان السيرفر ناقص).",
    kids: "أبنائي", addKid: "إضافة ابن/ابنة بكود", add: "إضافة", grades: "الدرجات", files: "الملفات", week: "الأسبوع", news: "الإعلانات", noKids: "لسه ما ربطتش أي ابن. اكتب الكود اللي اتسلّمتهولك المدرسة.",
    noGrades: "مفيش درجات متسجلة لسه.", noFiles: "مفيش ملفات متاحة دلوقتي.", noWeek: "خطة الأسبوع لسه ما اتنشرتش.", noNews: "مفيش إعلانات.", homework: "الواجبات", material: "مواد إضافية", quizzes: "تنبيهات الكويزات", trimester: "الفصل الدراسي", open: "فتح", pw8: "كلمة السر 8 حروف على الأقل.",
    kind: { presentation: "بريزنتيشن", quiz: "كويز", revision: "مراجعة", link: "رابط", other: "ملف" },
    items: { Behavior: "السلوك", Attendance: "الحضور", Classwork: "شغل الفصل", Homework: "الواجب", Quiz: "الكويز", Total: "المجموع" }, loading: "جارٍ التحميل…" },
  en: { brand: "Parents' portal · DLIS", login: "Sign in", signup: "Create account", email: "Email", pass: "Password", code: "Student code (from the school)", haveAcc: "I have an account", noAcc: "First time? Create an account", forgot: "Forgot password", sent: "If the account exists, a link was sent to your email.", out: "Sign out", lang: "العربية",
    badLogin: "The email or password is not right.", badCode: "The code is wrong or already used. Ask the school for a new one.", net: "Could not reach the server. Check the internet.", notSet: "The portal is not set up yet (server address missing).",
    kids: "My children", addKid: "Add a child with a code", add: "Add", grades: "Grades", files: "Files", week: "This week", news: "Announcements", noKids: "No child linked yet. Type the code the school gave you.",
    noGrades: "No grades yet.", noFiles: "Nothing shared right now.", noWeek: "The week plan is not published yet.", noNews: "No announcements.", homework: "Homework", material: "Extra material", quizzes: "Quiz alerts", trimester: "Term", open: "Open", pw8: "Password must be at least 8 characters.",
    kind: { presentation: "Presentation", quiz: "Quiz", revision: "Revision", link: "Link", other: "File" },
    items: { Behavior: "Behavior", Attendance: "Attendance", Classwork: "Classwork", Homework: "Homework", Quiz: "Quiz", Total: "Total" }, loading: "Loading…" },
};
let lang = localStorage.getItem("lang") || "ar";
const t = (k) => T[lang][k] ?? k;
const app = document.getElementById("app");
const store = { get: () => { try { return JSON.parse(localStorage.getItem("sess") || "null"); } catch { return null; } }, set: (v) => (v ? localStorage.setItem("sess", JSON.stringify(v)) : localStorage.removeItem("sess")) };

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? "" : v); }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

class NetErr extends Error {}
async function raw(method, path, body, token, extra) {
  if (!CFG.url || !CFG.key) throw new Error("notSet");
  let res;
  try {
    res = await fetch(CFG.url + path, { method, headers: { apikey: CFG.key, "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}), ...(extra || {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new NetErr(); }
  const text = await res.text(); let data = null; try { data = text ? JSON.parse(text) : null; } catch { /* not json */ }
  if (!res.ok) { const e = new Error((data && (data.msg || data.message || data.error_description)) || "error"); e.status = res.status; throw e; }
  return data;
}
async function auth(path, body) { const j = await raw("POST", "/auth/v1/" + path, body); if (j && j.access_token) store.set({ access: j.access_token, refresh: j.refresh_token, exp: Date.now() + (j.expires_in || 3000) * 1000 - 60000 }); return j; }
async function token() {
  const s = store.get(); if (!s) throw new Error("signedout");
  if (Date.now() < s.exp) return s.access;
  try { await auth("token?grant_type=refresh_token", { refresh_token: s.refresh }); } catch (e) { if (e instanceof NetErr) throw e; store.set(null); throw new Error("signedout"); }
  return store.get().access;
}
const api = async (method, path, body, extra) => raw(method, path, body, await token(), extra);
const say = (box, text, err) => box.replaceChildren(h("div", { class: "msg" + (err ? " err" : "") }, text));
const errText = (e) => (e instanceof NetErr ? t("net") : e.message === "notSet" ? t("notSet") : e.message);

// ---------------------------------------------------------------- sign in / sign up
function loginScreen(signup) {
  const em = h("input", { type: "email", autocomplete: "username", dir: "ltr" }), pw = h("input", { type: "password", autocomplete: signup ? "new-password" : "current-password", dir: "ltr" });
  const code = h("input", { type: "text", dir: "ltr", autocapitalize: "characters", placeholder: "XXXX-XXXX" });
  const msg = h("div", {});
  const go = async () => {
    try {
      if (signup) {
        if (pw.value.length < 8) return say(msg, t("pw8"), true);
        if (!code.value.trim()) return say(msg, t("badCode"), true);
        await auth("signup", { email: em.value.trim(), password: pw.value });
        if (!store.get()) await auth("token?grant_type=password", { email: em.value.trim(), password: pw.value });
        try { await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); } catch (e) { if (!(e instanceof NetErr)) say(msg, t("badCode"), true); }
      } else await auth("token?grant_type=password", { email: em.value.trim(), password: pw.value });
      home();
    } catch (e) { say(msg, signup && e.status === 422 ? e.message : e.status === 400 || e.status === 401 ? t("badLogin") : errText(e), true); }
  };
  app.replaceChildren(h("div", { class: "card" }, h("h1", {}, signup ? t("signup") : t("login")),
    h("label", {}, t("email")), em, h("label", {}, t("pass")), pw, signup ? [h("label", {}, t("code")), code] : null, msg,
    h("button", { class: "btn", onclick: go }, signup ? t("signup") : t("login")), h("br"),
    h("button", { class: "link", onclick: () => loginScreen(!signup) }, signup ? t("haveAcc") : t("noAcc")), " ",
    signup ? null : h("button", { class: "link", onclick: async () => { if (!em.value.trim()) return; try { await raw("POST", "/auth/v1/recover", { email: em.value.trim() }); } catch { /* same message either way */ } say(msg, t("sent")); } }, t("forgot"))));
}

// ---------------------------------------------------------------- home
let kids = [], cur = 0, tab = "grades";
async function home() {
  document.getElementById("out").hidden = false;
  app.replaceChildren(h("p", { class: "muted" }, t("loading")));
  try {
    const links = await api("GET", "/rest/v1/parent_students?select=student_code");
    kids = links.length ? await api("GET", "/rest/v1/students?select=code,class_id,display_name&code=in.(" + links.map((l) => l.student_code).join(",") + ")") : [];
  } catch (e) { if (e.message === "signedout") return loginScreen(false); return app.replaceChildren(h("div", { class: "msg err" }, errText(e))); }
  cur = Math.min(cur, Math.max(0, kids.length - 1)); draw();
}
function addKidBox() {
  const code = h("input", { type: "text", dir: "ltr", autocapitalize: "characters", placeholder: "XXXX-XXXX" }), msg = h("div", {});
  return h("div", { class: "card" }, h("h2", {}, t("addKid")), code, msg, h("button", { class: "btn ghost", onclick: async () => {
    try { await api("POST", "/rest/v1/rpc/claim_student", { p_code: code.value }); await home(); } catch (e) { say(msg, e instanceof NetErr ? t("net") : t("badCode"), true); }
  } }, t("add")));
}
function draw() {
  if (!kids.length) return app.replaceChildren(h("div", { class: "msg" }, t("noKids")), addKidBox());
  const k = kids[cur], body = h("div", {}, h("p", { class: "muted" }, t("loading")));
  const TABS = ["grades", "files", "week", "news"];
  app.replaceChildren(
    h("h1", {}, t("kids")), h("div", { class: "tabs" }, kids.map((x, i) => h("button", { class: "tab" + (i === cur ? " on" : ""), onclick: () => { cur = i; draw(); } }, x.display_name || x.code))),
    h("div", { class: "tabs" }, TABS.map((x) => h("button", { class: "tab" + (x === tab ? " on" : ""), onclick: () => { tab = x; draw(); } }, t(x)))), body, addKidBox());
  VIEWS[tab](k, body).catch((e) => { if (e.message === "signedout") return loginScreen(false); body.replaceChildren(h("div", { class: "msg err" }, errText(e))); });
}
const VIEWS = {
  async grades(k, box) {
    const rows = await api("GET", `/rest/v1/grades?select=trimester,week,subject,item,score,max_score&student_code=eq.${k.code}&order=trimester,subject,week.desc,item`);
    if (!rows.length) return box.replaceChildren(h("p", { class: "muted" }, t("noGrades")));
    const groups = {}; rows.forEach((r) => { (groups[`${r.trimester + 1}|${r.subject}`] ||= []).push(r); });
    box.replaceChildren(...Object.entries(groups).map(([g, list]) => h("div", { class: "card" }, h("h2", {}, `${t("trimester")} ${g.split("|")[0]} · ${g.split("|")[1]}`),
      h("table", {}, list.map((r) => h("tr", {}, h("td", {}, r.week ? `${t("week")} ${r.week}` : ""), h("td", {}, (t("items") || {})[r.item] || r.item), h("td", { dir: "ltr" }, `${r.score ?? "—"} / ${r.max_score ?? "—"}`)))))));
  },
  async files(k, box) {
    const rows = await api("GET", `/rest/v1/publications?select=id,kind,title,url,file_path,created_at&class_id=eq.${encodeURIComponent(k.class_id)}&order=created_at.desc`);
    if (!rows.length) return box.replaceChildren(h("p", { class: "muted" }, t("noFiles")));
    box.replaceChildren(...rows.map((p) => h("div", { class: "card" }, h("span", { class: "chip" }, t("kind")[p.kind] || p.kind), " ", h("b", {}, p.title), h("br"),
      p.url ? h("a", { href: safeUrl(p.url), target: "_blank", rel: "noopener noreferrer" }, t("open"))
        : h("button", { class: "btn ghost", onclick: async (ev) => { const b = ev.currentTarget; try { const j = await api("POST", "/storage/v1/object/sign/files/" + p.file_path.split("/").map(encodeURIComponent).join("/"), { expiresIn: 600 });
          window.open(CFG.url + "/storage/v1" + j.signedURL, "_blank", "noopener"); } catch { b.textContent = t("net"); } } }, t("open")))));
  },
  async week(k, box) {
    const rows = await api("GET", `/rest/v1/week_plans?select=trimester,week,homework,material,quiz_alerts&class_id=eq.${encodeURIComponent(k.class_id)}&order=trimester.desc,week.desc&limit=1`);
    if (!rows.length) return box.replaceChildren(h("p", { class: "muted" }, t("noWeek")));
    const w = rows[0], list = (title, items) => (items && items.length ? h("div", { class: "card" }, h("h2", {}, title), h("ul", {}, items.map((x) => h("li", {}, typeof x === "string" ? x : x.url ? h("a", { href: safeUrl(x.url), target: "_blank", rel: "noopener noreferrer" }, x.title || x.url) : x.title || x.text || JSON.stringify(x))))) : null);
    box.replaceChildren(h("p", { class: "muted" }, `${t("trimester")} ${w.trimester + 1} · ${t("week")} ${w.week}`), list(t("homework"), w.homework), list(t("material"), w.material), list(t("quizzes"), w.quiz_alerts));
  },
  async news(k, box) {
    const rows = await api("GET", "/rest/v1/announcements?select=title,body,starts_on,image_path&order=starts_on.desc,created_at.desc&limit=30");
    if (!rows.length) return box.replaceChildren(h("p", { class: "muted" }, t("noNews")));
    box.replaceChildren(...rows.map((a) => h("div", { class: "card" }, h("b", {}, a.title), a.image_path ? h("img", { class: "pic", src: `${CFG.url}/storage/v1/object/public/announce/${encodeURIComponent(a.image_path)}`, alt: "" }) : null, h("p", { style: "white-space:pre-wrap" }, a.body), h("div", { class: "muted" }, a.starts_on))));
  },
};

function setLang(l) {
  lang = l; localStorage.setItem("lang", l); document.documentElement.lang = l; document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
  document.getElementById("brand").textContent = t("brand"); document.getElementById("lang").textContent = t("lang"); document.getElementById("out").textContent = t("out");
}
document.getElementById("lang").addEventListener("click", () => { setLang(lang === "ar" ? "en" : "ar"); store.get() ? draw() : loginScreen(false); });
document.getElementById("out").addEventListener("click", () => { store.set(null); document.getElementById("out").hidden = true; loginScreen(false); });
setLang(lang);
if (store.get()) home(); else loginScreen(false);
