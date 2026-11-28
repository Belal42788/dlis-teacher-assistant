"use strict";
// The school calendar for the child's grade: where we are in the year, what is coming, then every month.
import { h, clear, icon, t, state } from "./core.js";
import { kid } from "./data.js";

let cached = null;
export async function loadCalendar() {
  if (!cached) { const r = await fetch("calendar.json", { cache: "no-cache" }); if (!r.ok) throw new Error("calendar"); cached = await r.json(); }
  return cached;
}
const DAY = 864e5, EXAM = /exam|revision|recap|map test/i;
const day = (iso) => new Date(iso + "T00:00:00");
const loc = () => (state.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");
const fmt = (d, o) => d.toLocaleDateString(loc(), o);
const startOfToday = () => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth(), n.getDate()); };
// grade ranges like (KG – G5) are written left to right even inside an Arabic line
const name = (x) => ((state.lang === "ar" ? x.ar : x.en) || x.en).replace(/\(([^)]*)\)/g, "\u2066($1)\u2069");
const termName = (i) => `${t("term")} ${i + 1}`;

// what the family sees: the holidays and the events for this child's grade, each with a kind, sorted by date
export function items(cal, grade) {
  const rows = [];
  cal.holidays.forEach((x) => rows.push({ kind: "holiday", from: day(x.start), to: day(x.end || x.start), name: name(x) }));
  cal.events.filter((e) => !e.grades || !grade || e.grades.includes(grade)).forEach((e) => rows.push({ kind: EXAM.test(e.en) ? "exam" : "event", from: day(e.date), to: day(e.date), name: name(e) }));
  return rows.sort((a, b) => a.from - b.from || a.name.localeCompare(b.name));
}
export function where(cal, today) {
  const i = cal.terms.findIndex((x) => today >= day(x.start) && today <= day(x.end));
  if (i < 0) return null;
  return { term: i, week: Math.floor((today - day(cal.terms[i].week1)) / (7 * DAY)) + 1 };
}
const when = (d, today) => { const n = Math.round((d - today) / DAY); return n <= 0 ? t("today") : n === 1 ? t("tomorrow") : t("inDays").replace("{n}", n); };
const range = (r) => (+r.from === +r.to ? fmt(r.from, { weekday: "short", day: "numeric", month: "short" }) : `${fmt(r.from, { day: "numeric", month: "short" })} – ${fmt(r.to, { day: "numeric", month: "short" })}`);
const chipFor = (kind) => h("span", { class: "chip " + (kind === "holiday" ? "green" : kind === "exam" ? "indigo" : "") }, t("calKind")[kind]);

function row(r, today) {
  const past = r.to < today;
  return h("div", { class: "row cal" + (past ? " past" : "") }, h("span", { class: "ic k-" + r.kind }, icon(r.kind === "holiday" ? "flag" : r.kind === "exam" ? "quiz" : "week")),
    h("div", { class: "tx" }, h("b", {}, r.name), h("small", {}, range(r))), r.to >= today ? h("span", { class: "muted small" }, when(r.from > today ? r.from : today, today)) : null, chipFor(r.kind));
}

// "Sunday 29 November · Term 2 · Week 1" for the top of the home page
export async function todayLine() {
  const today = startOfToday(), parts = [fmt(today, { weekday: "long", day: "numeric", month: "long" })];
  try { const at = where(await loadCalendar(), today); if (at) parts.push(`${termName(at.term)} · ${t("wk")} ${at.week}`); } catch { /* no calendar: just the date */ }
  return parts;
}

// the three coming things, for the home page
export async function upcoming(n = 3) {
  const cal = await loadCalendar(), k = kid(), today = startOfToday();
  return items(cal, k && k.grade_id).filter((r) => r.to >= today).slice(0, n).map((r) => ({ ...r, today }));
}
export const upcomingRow = (r) => row(r, r.today);

export async function viewCalendar(box) {
  const cal = await loadCalendar(), k = kid(), today = startOfToday(), all = items(cal, k && k.grade_id), at = where(cal, today);
  const next = all.filter((r) => r.to >= today).slice(0, 5);
  const months = new Map();
  all.forEach((r) => { const key = `${r.from.getFullYear()}-${String(r.from.getMonth() + 1).padStart(2, "0")}`; (months.get(key) || months.set(key, []).get(key)).push(r); });
  const thisMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const status = h("div", { class: "card" }, h("h2", {}, icon("week"), cal.year),
    at ? h("p", {}, h("b", {}, `${termName(at.term)} · ${t("wk")} ${at.week}`)) : h("p", { class: "muted" }, t("noTerm")),
    h("div", { class: "chips" }, cal.terms.map((x, i) => h("span", { class: "chip" + (at && at.term === i ? " green" : "") }, `${termName(i)}: ${fmt(day(x.start), { day: "numeric", month: "short" })} – ${fmt(day(x.end), { day: "numeric", month: "short" })}`))));
  clear(box, status,
    next.length ? h("div", { class: "card" }, h("h2", {}, icon("flag"), t("comingUp")), next.map((r) => row(r, today))) : null,
    [...months].map(([key, rows]) => {
      const first = rows[0].from, past = key < thisMonth;
      return h("details", { class: "card month", open: !past }, h("summary", {}, h("b", {}, fmt(first, { month: "long", year: "numeric" })), h("span", { class: "muted small" }, ` · ${rows.length}`)), rows.map((r) => row(r, today)));
    }),
    h("p", { class: "muted small" }, t("calNote")));
}
