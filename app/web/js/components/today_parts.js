import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { announceCard } from "./announce_list.js";
import { fmtShort, fmtDay, triName, localName, fmt12 } from "../labels.js";

// Pieces of the Today page that do not depend on which day is shown.

const aiHint = { hidden: false };   // "not now" hides the AI hint until the program is opened again

// The boxes beside the lessons (AI hint, "prepare my week", announcements). They fill themselves when their data arrives.
export function sideBoxes(isToday) {
    const annBox = h("div", {});
    const aiBox = h("div", {});     // shown at the start while the AI is not set up: a button that explains how to turn it on
    if (isToday && !aiHint.hidden) api.get("/api/ai").then((r) => {
      if (r.ready) return;
      aiBox.append(h("div", { class: "banner info", style: { marginBottom: ".8rem" } }, icon("spark"),
        h("div", { class: "grow" }, h("b", {}, t("aih_title")), h("div", { class: "small muted" }, t("aih_text"))),
        h("a", { class: "btn small primary", href: "#/help?open=ai" }, t("aih_how")),
        h("a", { class: "btn small", href: "#/settings" }, t("aih_settings")),
        h("button", { class: "btn small ghost", onClick: () => { aiHint.hidden = true; aiBox.replaceChildren(); } }, t("aih_later"))));
    }).catch(() => {});
    const prepBox = h("div", {});   // "prepare my week": how many classes already have their lesson plan
    if (isToday) api.get("/api/week-prep").then((r) => {
      if (!r.total) return;
      const done = r.ready >= r.total;
      prepBox.append(h("div", { class: `banner ${done ? "ok" : "info"}`, style: { marginBottom: ".8rem" } }, icon(done ? "check" : "file"),
        h("div", { class: "grow" }, h("b", {}, done ? t("pw_all_ready") : t("pw_status", { a: r.ready, b: r.total })), done ? null : h("div", { class: "small muted" }, (() => { const m = r.grades.filter((g) => !g.has_plan); return m.slice(0, 5).map((g) => g.name + (g.topic ? ` (${g.topic})` : "")).join(" · ") + (m.length > 5 ? ` +${m.length - 5}` : ""); })())),
        done ? null : h("a", { class: "btn small primary", href: "#/docs" }, icon("spark"), t("pw_go")))); }).catch(() => {});
    if (isToday) Promise.all([api.get("/api/announcements"), api.get("/api/cloud").catch(() => ({}))]).then(([a, c]) => {
      const live = (a.items || []).filter((x) => x.active).slice(0, 3), admin = c.role === "admin";
      if (live.length || admin) annBox.append(h("div", { class: "panel", style: { marginTop: ".9rem" } },
        h("div", { class: "row" }, h("h3", { style: { margin: 0 } }, t("an_today")), h("span", { class: "grow" }),
          admin ? h("a", { class: "btn small primary", href: "#/announcements" }, icon("plus"), t("an_add_short")) : null),
        ...live.map((x) => announceCard(x)))); }).catch(() => {});
  return { aiBox, prepBox, annBox };
}

export function weekBadge(pos) {
  if (pos.state === "in_term") return h("span", { class: "week-badge" }, `${triName(pos.trimester_name)} · ${t("week_n", { n: pos.week })}`);
  if (pos.state === "no_calendar") return h("span", { class: "week-badge quiet" }, t("no_calendar_badge"));
  if (pos.state === "before_term" || pos.state === "between_terms")
    return h("span", { class: "week-badge quiet" }, t("next_term_starts", { name: triName(pos.next_name), date: fmtShort(pos.next_start) }));
  return h("span", { class: "week-badge quiet" }, t("year_finished"));
}

export function notices(d, structure) {
  const out = [];
  if (d.holiday) out.push(h("div", { class: "banner holiday" }, icon("calendar"), h("div", {}, h("b", {}, localName(d.holiday.name) || t("holiday")), h("div", {}, d.holiday.end && d.holiday.end !== d.holiday.start ? `${fmtDay(d.holiday.start)} → ${fmtDay(d.holiday.end)}` : fmtDay(d.holiday.start)), h("div", {}, t("no_school_today")))));
  for (const e of d.events) out.push(h("div", { class: "banner warn" }, icon("info"), h("b", {}, e)));
  if (d.position.state === "no_calendar") out.push(h("div", { class: "banner warn" }, icon("warn"),
    h("div", {}, t("calendar_missing"), " ", h("a", { href: "#/calendar" }, t("set_calendar")))));
  if (!structure.rooms.length) out.push(h("div", { class: "banner warn" }, icon("warn"),
    h("div", {}, t("no_classes_yet"), " ", h("a", { href: "#/classes" }, t("add_classes")))));
  return out;
}
const mins = (hhmm) => { const m = /^(\d{1,2}):(\d{2})/.exec(hhmm || ""); return m ? +m[1] * 60 + +m[2] : null; };
const nowMins = () => { const n = new Date(); return n.getHours() * 60 + n.getMinutes(); };

const fmtLeft = (m) => { m = Math.max(0, Math.ceil(m)); if (m < 60) return t("td_min", { n: m }); const hh = Math.floor(m / 60), mm = m % 60; return mm ? t("td_hm", { h: hh, m: mm }) : t("td_h", { h: hh }); };
// Marks the lesson that is running now, fades the ones that are over, writes the time left on each row and keeps the "next lesson" bar current
// (re-checked every 15 seconds while the page is open).
export function trackNow(items, nextBox) {
  const lessons = items.filter((x) => x.lesson && mins(x.start) !== null && mins(x.end) !== null);
  let shown = null;
  const tick = () => {
    const rows = document.querySelectorAll(".slot[data-s]");
    if (!rows.length) { clearInterval(timer); return; }
    const n = nowMins();
    rows.forEach((el) => {
      const a = mins(el.dataset.s), b = mins(el.dataset.e);
      const st = a === null || b === null ? "" : n >= b ? "past" : n >= a ? "now" : "";
      el.dataset.state = st;
      const u = el.querySelector(".until");
      if (u && a !== null) { u.textContent = st === "past" ? t("td_done") : st === "now" ? t("td_now") : t("td_in", { x: fmtLeft(a - n) }); u.className = "until" + (st === "past" ? " done" : st === "now" || a - n <= 15 ? " soon" : ""); }
    });
    if (!nextBox) return;
    const cur = lessons.find((x) => n < mins(x.end));
    if (!cur) { nextBox.replaceChildren(); shown = null; return; }
    if (cur !== shown) { shown = cur; nextBox.replaceChildren(cur.banner()); }
    const a = mins(cur.start), running = n >= a, left = running ? mins(cur.end) - n : a - n;
    const num = nextBox.querySelector(".nb-num"), unit = nextBox.querySelector(".nb-unit"), lab = nextBox.querySelector(".nb-lab");
    const big = Math.max(0, Math.ceil(left));
    if (num) { num.textContent = big < 60 ? String(big) : `${Math.floor(big / 60)}:${String(big % 60).padStart(2, "0")}`; unit.textContent = big < 60 ? t("td_unit_min") : t("td_unit_h"); }
    if (lab) lab.textContent = running ? t("td_left", { x: fmtLeft(left) }) : t("td_next_at", { time: fmt12(cur.start) });
    nextBox.firstChild?.classList.toggle("running", running);
  };
  const timer = setInterval(tick, 15000);
  setTimeout(tick, 0);
  return lessons.length;
}
