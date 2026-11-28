"use strict";
// The school calendar, drawn like the teacher app's calendar page: the term card, one month (a week number on each row, holidays tinted),
// what is coming, then every week of every term as a square. Only the dates of the child's grade are shown. Read-only.
import { h, clear, icon, t, state } from "./core.js";
import { kid } from "./data.js";

let cached = null;
export async function loadCalendar() {
  if (!cached) { const r = await fetch("calendar.json", { cache: "no-cache" }); if (!r.ok) throw new Error("calendar"); cached = await r.json(); }
  return cached;
}

// ---------------------------------------------------------------- dates (plain "YYYY-MM-DD" strings, worked out in UTC so a time zone never moves a day)
const DAY = 864e5, pad = (n) => String(n).padStart(2, "0");
const toMs = (s) => { const [y, m, d] = s.split("-").map(Number); return Date.UTC(y, m - 1, d); };
const addDays = (s, n) => new Date(toMs(s) + n * DAY).toISOString().slice(0, 10);
const dow = (s) => new Date(toMs(s)).getUTCDay();
const between = (a, b) => Math.round((toMs(b) - toMs(a)) / DAY);
const todayIso = () => { const n = new Date(); return `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`; };
const loc = () => (state.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");
const fmt = (s, o) => new Date(toMs(s)).toLocaleDateString(loc(), { ...o, timeZone: "UTC" });
const short = (s) => fmt(s, { day: "numeric", month: "short" });
const name = (x) => ((state.lang === "ar" ? x.ar : x.en) || x.en).replace(/\(([^)]*)\)/g, "⁦($1)⁩");   // grade ranges like (KG – G5) read left to right inside an Arabic line
const termName = (i) => `${t("term")} ${i + 1}`;
const when = (n) => (n <= 0 ? t("today") : n === 1 ? t("tomorrow") : t("inDays").replace("{n}", n));

// what kind of day an event is: only the days that really are exams or revision say so; the first day of a term is its own kind
const START = /^first day of (trimester|foundation|g\d)/i, EXAM = /^(exams?\b|revision|recap days?|map test)/i;
export const kindOf = (en) => (START.test(en) ? "start" : EXAM.test(en) ? "exam" : "event");
const ICON = { holiday: "flag", exam: "quiz", start: "study", event: "week" };
const chipFor = (kind) => h("span", { class: "chip " + (kind === "holiday" ? "green" : kind === "exam" ? "indigo" : kind === "start" ? "amber" : "") }, t("calKind")[kind]);

// everything about each date, looked up fast: holiday names, events of this grade, week numbers, the weeks of every term
export function indexOf(cal, grade) {
  const hol = new Map(), ev = new Map(), weekOf = new Map(), weeks = [];
  for (const x of cal.holidays) for (let d = x.start, n = 0; d <= x.end && n < 400; d = addDays(d, 1), n++) hol.set(d, name(x));
  for (const e of cal.events) if (!e.grades || !grade || e.grades.includes(grade)) { if (!ev.has(e.date)) ev.set(e.date, []); ev.get(e.date).push({ name: name(e), kind: kindOf(e.en) }); }
  cal.terms.forEach((tr, ti) => {
    const list = []; let n = 1;
    for (let s = tr.week1; s <= tr.end; s = addDays(s, 7), n++) { list.push({ n, start: s, end: addDays(s, 6) }); for (let i = 0; i < 7; i++) weekOf.set(addDays(s, i), { n, ti }); }
    weeks.push(list);
  });
  return { hol, ev, weekOf, weeks };
}
const position = (cal, today) => { const i = cal.terms.findIndex((x) => today >= x.start && today <= x.end); return i < 0 ? null : { ti: i, n: Math.max(1, Math.floor(between(cal.terms[i].week1, today) / 7) + 1) }; };

// the dates from today on: holidays, events, and where a term ends; the first day of a term is already an event
export function comingUp(cal, idx, today, limit) {
  const rows = [];
  for (const x of cal.holidays) if (x.end >= today) rows.push({ kind: "holiday", from: x.start, to: x.end, d: x.start < today ? today : x.start, name: name(x) });
  for (const [d, list] of idx.ev) if (d >= today) list.forEach((e) => rows.push({ kind: e.kind, from: d, to: d, d, name: e.name }));
  cal.terms.forEach((tr, i) => { if (tr.end >= today) rows.push({ kind: "holiday", from: tr.end, to: tr.end, d: tr.end, name: `${termName(i)} · ${t("endsOn")}`, term: true }); });
  const byDate = (a, b) => a.d.localeCompare(b.d) || a.name.localeCompare(b.name);
  // holidays and term dates first; events (there are many) only fill what is left, so they never push the holidays out
  const main = rows.filter((x) => x.kind === "holiday").sort(byDate).slice(0, Math.max(2, limit - 3));
  return [...main, ...rows.filter((x) => x.kind !== "holiday").sort(byDate).slice(0, limit - main.length)].sort(byDate);
}

const range = (r) => (r.from === r.to ? fmt(r.from, { weekday: "short", day: "numeric", month: "short" }) : `${short(r.from)} – ${short(r.to)}`);
// one date in a list: a small date box, then the name, then when and what kind (under the name, so a long name never gets squeezed)
export function row(r, today) {
  return h("div", { class: "row cal" + (r.to < today ? " past" : "") },
    h("span", { class: "ic k-" + r.kind }, icon(ICON[r.kind])),
    h("div", { class: "tx" }, h("b", {}, r.name), h("small", {}, range(r), r.to >= today ? ` · ${when(between(today, r.d))}` : ""), h("span", { class: "kc" }, chipFor(r.kind))));
}

// "Sunday 29 November · Term 2 · Week 1" for the top of the home page
export async function todayLine() {
  const today = todayIso(), parts = [fmt(today, { weekday: "long", day: "numeric", month: "long" })];
  try { const cal = await loadCalendar(), at = position(cal, today); if (at) parts.push(`${termName(at.ti)} · ${t("wk")} ${at.n}`); } catch { /* no calendar: just the date */ }
  return parts;
}
// the next few dates, for the home page
export async function upcoming(n = 3) {
  const cal = await loadCalendar(), k = kid(), today = todayIso();
  return comingUp(cal, indexOf(cal, k && k.grade_id), today, n).map((r) => ({ ...r, today }));
}
export const upcomingRow = (r) => row(r, r.today);

// ---------------------------------------------------------------- the page
export async function viewCalendar(box) {
  const cal = await loadCalendar(), k = kid(), today = todayIso(), idx = indexOf(cal, k && k.grade_id), at = position(cal, today);
  const view = { y: +today.slice(0, 4), m: +today.slice(5, 7) - 1 };
  let picked = today;
  const monthBox = h("div", { class: "card mo-wrap" }), weeksBox = h("div", { class: "card wk-line" });

  const nextTerm = cal.terms.findIndex((x) => x.start > today);
  const termCard = h("div", { class: "cal-card" }, h("div", { class: "big" }, at ? `${termName(at.ti)} · ${t("wk")} ${at.n}` : nextTerm >= 0 ? termName(nextTerm) : cal.year),
    at ? h("small", {}, `${short(cal.terms[at.ti].start)} – ${short(cal.terms[at.ti].end)}`) : nextTerm >= 0 ? h("small", {}, `${t("startsOn")} ${fmt(cal.terms[nextTerm].start, { weekday: "long", day: "numeric", month: "long" })}`) : null);

  function dayPanel() {
    const hol = idx.hol.get(picked), evs = idx.ev.get(picked) || [], wk = idx.weekOf.get(picked);
    return h("div", { class: "day-panel" }, h("div", { class: "day-title" }, h("b", {}, fmt(picked, { weekday: "long", day: "numeric", month: "long" })), wk ? h("span", { class: "muted small" }, ` · ${t("wk")} ${wk.n}`) : null),
      hol ? h("div", { class: "day-line hol" }, icon("flag"), h("span", {}, hol)) : null,
      evs.map((e) => h("div", { class: "day-line" }, icon(ICON[e.kind]), h("span", {}, e.name), chipFor(e.kind))),
      !hol && !evs.length ? h("p", { class: "muted small" }, t("dayEmpty")) : null);
  }
  function drawMonth() {
    const first = `${view.y}-${pad(view.m + 1)}-01`, lastDay = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate(), last = `${view.y}-${pad(view.m + 1)}-${pad(lastDay)}`;
    const heads = [0, 1, 2, 3, 4, 5, 6].map((i) => h("div", { class: "mo-dn" }, fmt(addDays("2026-11-01", i), { weekday: "short" })));
    const cells = [];
    for (let r = 0; ; r++) {
      const rowStart = addDays(first, -dow(first) + r * 7);
      if (rowStart > last) break;
      const wk = [0, 1, 2, 3, 4, 5, 6].map((i) => idx.weekOf.get(addDays(rowStart, i))).find(Boolean);
      cells.push(h("div", { class: "mo-wk" }, wk ? wk.n : ""));
      for (let i = 0; i < 7; i++) {
        const d = addDays(rowStart, i), inMonth = d.slice(0, 7) === first.slice(0, 7), hol = idx.hol.get(d), evs = idx.ev.get(d) || [];
        const cls = ["mo-d", !inMonth ? "mute" : "", dow(d) >= 5 ? "off" : "", hol ? "hol" : "", d === today ? "today" : "", d === picked ? "sel" : ""].filter(Boolean).join(" ");
        cells.push(h("button", { type: "button", class: cls, "aria-label": `${fmt(d, { day: "numeric", month: "long" })}${hol ? ` · ${hol}` : ""}`, onclick: () => { picked = d; drawMonth(); } },
          h("span", { class: "mo-n" }, +d.slice(8)),
          hol ? h("small", { class: "mo-h", dir: "auto" }, hol) : null,
          ...evs.slice(0, hol ? 1 : 2).map((e) => h("small", { class: "mo-e", dir: "auto" }, e.name)),
          evs.length > (hol ? 1 : 2) ? h("small", { class: "mo-more" }, `+${evs.length - (hol ? 1 : 2)}`) : null,
          evs.length || hol ? h("i", { class: "mo-dot" + (hol ? " h" : "") }) : null));
      }
    }
    const move = (n) => { if (n === 0) { view.y = +today.slice(0, 4); view.m = +today.slice(5, 7) - 1; picked = today; } else { const d = new Date(Date.UTC(view.y, view.m + n, 1)); view.y = d.getUTCFullYear(); view.m = d.getUTCMonth(); } drawMonth(); };
    const soon = comingUp(cal, idx, today, 6);
    clear(monthBox, h("div", { class: "mo" },
      h("div", { class: "mo-head" },
        h("button", { class: "btn icon", "aria-label": t("calPrev"), onclick: () => move(-1) }, icon("back")),
        h("h2", {}, fmt(first, { month: "long", year: "numeric" })),
        h("button", { class: "btn icon", "aria-label": t("calNext"), onclick: () => move(1) }, icon("chevron")),
        h("button", { class: "btn small", onclick: () => move(0) }, t("today"))),
      h("div", { class: "mo-grid" }, h("div", {}), heads, cells), dayPanel()),
      h("div", { class: "mo-side" }, h("h3", {}, t("comingUp")), soon.length ? soon.map((r) => row(r, today)) : h("p", { class: "muted small" }, t("nothingNext"))));
  }
  function drawWeeks() {
    clear(weeksBox, idx.weeks.map((list, ti) => h("div", { class: "wk-row" },
      h("div", { class: "wk-name" }, h("b", {}, termName(ti)), h("span", { class: "muted small" }, `${short(cal.terms[ti].start)} – ${short(cal.terms[ti].end)} · ${list.length} ${t("weeksWord")}`)),
      h("div", { class: "wk-squares" }, list.map((w) => h("button", { type: "button", class: "wk-sq" + (w.end < today ? " past" : "") + (at && at.ti === ti && at.n === w.n ? " now" : ""), "aria-label": `${t("wk")} ${w.n}`, title: `${t("wk")} ${w.n} · ${short(w.start)}`,
        onclick: () => { view.y = +w.start.slice(0, 4); view.m = +w.start.slice(5, 7) - 1; picked = w.start; drawMonth(); monthBox.scrollIntoView({ behavior: "smooth", block: "start" }); } }, w.n))))),
      h("div", { class: "cal-legend small" }, h("span", {}, h("i", { class: "lg now" }), t("legendNow")), h("span", {}, h("i", { class: "lg past" }), t("legendPast"))));
  }
  drawMonth(); drawWeeks();
  clear(box, termCard, monthBox, weeksBox, h("p", { class: "muted small" }, t("calNote")));
}
