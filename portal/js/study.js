"use strict";
// Home, this week, files (term -> week), grades and announcements.
import { h, clear, icon, t, api, CFG, safeUrl, fmtDay, errText, toast } from "./core.js";
import { S, kid, kidShort, pubs, plans, grades, news, weekIndex } from "./data.js";
import { enter, lastSeen, isNew } from "./fresh.js";
import { upcoming, upcomingRow, todayLine } from "./calendar.js";

const newChip = () => h("span", { class: "chip green new" }, t("newWord"));

const KIND_ICON = { presentation: "slides", quiz: "quiz", revision: "revision", link: "link", other: "file", message: "mail" };
const termName = (tri) => `${t("term")} ${tri + 1}`;
const weekName = (w) => `${t("wk")} ${w.wk}`;
// a card with nothing in it yet says what will appear there, so the page never looks abandoned
const hollow = (ic, title, hint, action) => h("div", { class: "hollow" }, h("span", { class: "orb" }, icon(ic)), h("b", {}, title), h("span", { class: "muted small" }, hint), action || null);
const empty = (ic, title, text) => h("div", { class: "empty" }, icon(ic), h("b", {}, title), text ? h("span", {}, text) : null);

async function openStored(btn, path) {
  try {
    const j = await api("POST", "/storage/v1/object/sign/files/" + path.split("/").map(encodeURIComponent).join("/"), { expiresIn: 600 });
    window.open(CFG.url + "/storage/v1" + j.signedURL, "_blank", "noopener");
  } catch (e) { toast(errText(e), true); }
}
export function fileRow(p, since) {
  const fresh = since && isNew(p, since) ? newChip() : null;
  if (p.kind === "message") return h("div", { class: "row" }, h("span", { class: "ic" }, icon("mail")), h("div", { class: "tx" }, h("b", {}, t("kind").message), h("small", {}, p.body || p.title)), fresh);
  const open = p.url ? h("a", { class: "btn small", href: safeUrl(p.url), target: "_blank", rel: "noopener noreferrer" }, t("open"))
    : p.file_path ? h("button", { class: "btn small", onclick: (ev) => openStored(ev.currentTarget, p.file_path) }, t("open")) : null;
  return h("div", { class: "row" }, h("span", { class: "ic k-" + p.kind }, icon(KIND_ICON[p.kind] || "file")),
    h("div", { class: "tx" }, h("b", {}, p.title), h("small", {}, [t("kind")[p.kind] || p.kind, p.created_at ? fmtDay(p.created_at) : ""].filter(Boolean).join(" · ")), p.note ? h("small", {}, p.note) : null), fresh, open);
}
const list = (items) => h("ul", { class: "plain" }, items.map((x) => h("li", {}, typeof x === "string" ? x : x.url ? h("a", { href: safeUrl(x.url), target: "_blank", rel: "noopener noreferrer" }, x.title || x.url) : x.title || x.text || JSON.stringify(x))));
function planCard(w, short) {
  const parts = [["homework", t("homework")], ["material", t("material")], ["quiz_alerts", t("quizzes")]].filter(([f]) => w[f] && w[f].length);
  return h("div", { class: "card" }, h("h2", {}, icon("week"), w.subject || t("week")), parts.length ? parts.map(([f, label]) => [h("div", { class: "sec" }, label), list(short ? w[f].slice(0, 3) : w[f])]) : h("p", { class: "muted" }, "—"));
}

// ---------------------------------------------------------------- home
export async function viewHome(box, go) {
  const k = kid();
  const [files, planRows, notes, soon, today] = await Promise.all([pubs(k), plans(k), news(), upcoming(3).catch(() => []), todayLine()]);
  const seenFiles = lastSeen(k.code, "files"), seenNews = lastSeen("all", "news");
  const weeks = weekIndex(files, planRows), now = weeks[0];
  const hello = h("div", { class: "card hero" }, h("img", { src: "img/logo-mark.png", alt: "" }), h("div", {}, h("h1", {}, `${t("hello")}، ${kidShort(k)}`),
    h("div", { class: "muted" }, S.role === "student" ? t("studentAcc") : `${t("parentAcc")} · ${t("following")} ${kidShort(k)}`),
    h("div", { class: "chips hero-chips" }, today.map((x, i) => h("span", { class: "chip" + (i === 1 ? " green" : "") }, x)))));
  const weekCard = h("div", { class: "card span2" }, h("h2", {}, icon("week"), t("homeWeek")), now ? [h("p", { class: "muted" }, `${termName(now.tri)} · ${weekName(now)}`),
    now.plans.length ? now.plans.slice(0, 2).map((w) => [w.subject ? h("span", { class: "chip" }, w.subject) : null, (w.homework || []).length ? list(w.homework.slice(0, 3)) : h("p", { class: "muted" }, "—")]) : h("p", { class: "muted" }, t("noWeek")),
    h("button", { class: "btn small", onclick: () => go("study", "week") }, t("seeAll"))] : hollow("week", t("noWeek"), t("noWeekHint")));
  const filesCard = h("div", { class: "card" }, h("h2", {}, icon("folder"), t("homeFiles")), files.length ? [files.slice(0, 4).map((p) => fileRow(p, seenFiles)), h("button", { class: "btn small", onclick: () => go("study", "files") }, t("seeAll"))] : hollow("folder", t("noFiles"), t("noFilesHint")));
  const newsCard = h("div", { class: "card" }, h("h2", {}, icon("news"), t("homeNews")), notes.length ? [notes.slice(0, 2).map((a) => h("div", { class: "row" }, h("span", { class: "ic" }, icon("news")), h("div", { class: "tx" }, h("b", {}, a.title), h("small", {}, a.body)), isNew(a, seenNews) ? newChip() : null)), h("button", { class: "btn small", onclick: () => go("talk", "news") }, t("seeAll"))] : hollow("news", t("noNews"), t("noNewsHint")));
  const talkCard = h("div", { class: "card" }, h("h2", {}, icon("talk"), t("homeTalk")), S.unread ? [h("p", {}, h("span", { class: "dot" }, S.unread), " ", t("unread")), h("button", { class: "btn small primary", onclick: () => go("talk", "messages") }, t("open"))]
      : hollow("talk", t("noUnread"), t("noUnreadHint"), h("button", { class: "btn small primary", onclick: () => go("talk", "messages") }, t("startTalk"))));
  const soonCard = soon.length ? h("div", { class: "card" }, h("h2", {}, icon("cal"), t("comingUp")), soon.map(upcomingRow), h("button", { class: "btn small", onclick: () => go("study", "calendar") }, t("seeAll"))) : null;
  clear(box, hello, h("div", { class: "grid home" }, weekCard, talkCard, filesCard, newsCard, soonCard));
}

// ---------------------------------------------------------------- this week
export async function viewWeek(box) {
  const k = kid(), since = lastSeen(k.code, "files"), [files, planRows] = await Promise.all([pubs(k), plans(k)]), weeks = weekIndex(files, planRows);
  if (!weeks.length) return clear(box, empty("week", t("noWeek")));
  let sel = weeks[0].key;
  const draw = () => {
    const w = weeks.find((x) => x.key === sel);
    clear(box, h("div", { class: "chips" }, weeks.slice(0, 14).map((x) => h("button", { "aria-pressed": x.key === sel ? "true" : "false", onclick: () => { sel = x.key; draw(); } }, `${weekName(x)}${x === weeks[0] ? " · " + t("latest") : ""}`))),
      h("p", { class: "muted" }, `${termName(w.tri)} · ${weekName(w)}`),
      w.plans.length ? w.plans.map((p) => planCard(p)) : h("p", { class: "muted" }, t("noWeek")),
      w.files.length ? [h("div", { class: "sec" }, t("weekFiles")), h("div", { class: "card" }, w.files.map((p) => fileRow(p, since)))] : null);
  };
  draw();
}

// ---------------------------------------------------------------- files: term -> week on the side, the week's files in the middle
export async function viewFiles(box) {
  const k = kid(), files = await pubs(k), weeks = weekIndex(files, []), since = enter(k.code, "files");
  if (!files.length) return clear(box, empty("folder", t("noFiles")));
  const loose = files.filter((p) => !p.week);
  let sel = weeks.length ? weeks[0].key : "none", kind = "all";
  const draw = () => {
    const inSel = sel === "none" ? loose : (weeks.find((w) => w.key === sel) || { files: [] }).files;
    const kinds = [...new Set(inSel.map((p) => p.kind))], shown = inSel.filter((p) => kind === "all" || p.kind === kind);
    const terms = [...new Set(weeks.map((w) => w.tri))];
    const tree = h("nav", { class: "tree", "aria-label": t("files") },
      terms.map((tri) => [h("div", { class: "stage" }, termName(tri)), h("div", { class: "wks" }, weeks.filter((w) => w.tri === tri).map((w) =>
        h("button", { class: w === weeks[0] ? "now" : "", "aria-current": w.key === sel ? "true" : "false", onclick: () => { sel = w.key; kind = "all"; draw(); } }, h("span", {}, weekName(w)), h("span", { class: "count" }, w.files.some((p) => isNew(p, since)) ? [newChip(), " "] : null, w.files.length))))]),
      loose.length ? [h("div", { class: "stage" }, t("files")), h("div", { class: "wks" }, h("button", { "aria-current": sel === "none" ? "true" : "false", onclick: () => { sel = "none"; kind = "all"; draw(); } }, h("span", {}, t("general")), h("span", { class: "count" }, loose.length)))] : null);
    const cur = weeks.find((w) => w.key === sel);
    clear(box, h("div", { class: "lay" }, tree, h("div", { class: "main" },
      h("div", { class: "head" }, h("h2", {}, sel === "none" ? t("general") : `${termName(cur.tri)} · ${weekName(cur)}`), cur && cur === weeks[0] ? h("span", { class: "chip green" }, t("latest")) : null, h("span", { class: "grow" }), h("span", { class: "muted small" }, `${inSel.length} ${t("files_n")}`)),
      kinds.length > 1 ? h("div", { class: "chips" }, [["all", t("allKinds")], ...kinds.map((x) => [x, t("kind")[x] || x])].map(([x, label]) => h("button", { "aria-pressed": kind === x ? "true" : "false", onclick: () => { kind = x; draw(); } }, label))) : null,
      shown.length ? h("div", { class: "card" }, shown.map((p) => fileRow(p, since))) : empty("folder", t("noFilesWeek")))));
  };
  draw();
}

// ---------------------------------------------------------------- grades
const ORDER = ["Behavior", "Attendance", "Classwork", "Homework", "Quiz", "Quiz Score", "Total"];
export async function viewGrades(box) {
  const rows = await grades(kid());
  if (!rows.length) return clear(box, empty("grades", t("noGrades")));
  const terms = [...new Set(rows.map((r) => r.trimester))].sort((a, b) => b - a);
  let tri = terms[0];
  const draw = () => {
    const mine = rows.filter((r) => r.trimester === tri), subjects = [...new Set(mine.map((r) => r.subject))].sort();
    clear(box, terms.length > 1 ? h("div", { class: "seg" }, terms.map((x) => h("button", { "aria-pressed": x === tri ? "true" : "false", onclick: () => { tri = x; draw(); } }, termName(x)))) : null,
      subjects.map((s) => {
        const list = mine.filter((r) => r.subject === s), items = [...new Set(list.map((r) => r.item))].sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b));
        const wks = [...new Set(list.map((r) => r.week))].sort((a, b) => b - a), cell = (w, it) => { const r = list.find((x) => x.week === w && x.item === it); return h("td", { class: it === "Total" ? "tot" : "", dir: "ltr" }, r ? [r.score ?? "—", h("span", { class: "of" }, ` / ${r.max_score ?? "—"}`)] : "—"); };
        return h("div", { class: "card" }, h("h2", {}, icon("grades"), s), h("div", { class: "tbl" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, t("wk")), items.map((it) => h("th", {}, t("items")[it] || it)))),
          h("tbody", {}, wks.map((w) => h("tr", {}, h("td", {}, w ? `${t("wk")} ${w}` : "—"), items.map((it) => cell(w, it))))))));
      }));
  };
  draw();
}

// ---------------------------------------------------------------- announcements
export async function viewNews(box) {
  const rows = await news(), since = enter("all", "news");
  if (!rows.length) return clear(box, empty("news", t("noNews")));
  clear(box, rows.map((a) => h("div", { class: "card" }, h("div", { class: "head" }, h("h2", {}, a.title), isNew(a, since) ? newChip() : null, h("span", { class: "grow" }), h("span", { class: "muted small" }, fmtDay(a.starts_on))),
    a.image_path ? h("img", { src: `${CFG.url}/storage/v1/object/public/announce/${encodeURIComponent(a.image_path)}`, alt: "", style: "max-width:100%;border-radius:10px;margin:.3rem 0" }) : null, h("p", { style: "white-space:pre-wrap" }, a.body))));
}
