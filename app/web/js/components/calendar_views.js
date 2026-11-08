import { h, icon } from "../dom.js";
import { t } from "../i18n.js";
import { fmtDate, fmtShort, addDays, localName, triName } from "../labels.js";

// Two ways of looking at the school year, built from the calendar (/api/calendar) and the weeks overview (/api/overview).
// Nothing here changes data: pressing a day asks the page to open its notes.

const DAY = 86400000;
const toMs = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d); };
export const daysBetween = (a, b) => Math.round((toMs(b) - toMs(a)) / DAY);
const dow = (iso) => new Date(toMs(iso)).getUTCDay();
const isoOf = (ms) => new Date(ms).toISOString().slice(0, 10);

// "in 17 days" / "tomorrow" / "now"
export const inDays = (n) => (n <= 0 ? t("cal_now") : n === 1 ? t("cal_tomorrow") : t("cal_in_days", { n }));

// Everything the views need to know about one date, looked up fast.
export function calendarIndex(cal, ov) {
  const hol = new Map(), ev = new Map(), weekOf = new Map();
  for (const x of cal.holidays || []) {
    if (!x.start) continue;
    const to = x.end && x.end >= x.start ? x.end : x.start;
    for (let d = x.start, n = 0; d <= to && n < 400; d = addDays(d, 1), n++) hol.set(d, localName(x.name) || t("holiday"));
  }
  for (const x of cal.events || []) if (x.date) { if (!ev.has(x.date)) ev.set(x.date, []); ev.get(x.date).push(x.name); }
  for (const tri of ov.trimesters || []) for (const w of tri.weeks) { for (let i = 0; i < 7; i++) weekOf.set(addDays(w.start, i), { n: w.number, tri: tri.index }); }
  return { hol, ev, weekOf };
}

// ---------- 1) the weeks line: one row per trimester, one square per week
export function weeksLine(ov, cal, idx, onWeek) {
  const now = ov.position.state === "in_term" ? ov.position : null;
  const rows = ov.trimesters.filter((x) => x.weeks.length).map((tri) => {
    const squares = tri.weeks.map((w) => {
      const cls = ["wk-sq", w.end < ov.today ? "past" : "", now && now.trimester === tri.index && now.week === w.number ? "now" : "", w.holidays.length ? "hol" : ""].filter(Boolean).join(" ");
      const names = [...new Set(w.holidays.map((x) => localName(x.name)))].join("، ");
      return h("button", { type: "button", class: cls, title: `${t("cal_week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}${names ? ` · ${names}` : ""}`, "aria-label": t("cal_week_n", { n: w.number }), onClick: () => onWeek(w.start) }, w.number);
    });
    return h("div", { class: "wk-row" },
      h("div", { class: "wk-name" }, h("b", {}, triName(tri.name)), h("span", { class: "muted small" }, `${fmtShort(tri.start)} – ${fmtShort(tri.end)} · ${t("weeks_count", { n: tri.weeks.length })}`)),
      h("div", { class: "wk-squares", style: { gridTemplateColumns: `repeat(${tri.weeks.length}, minmax(0, 1fr))` } }, squares));
  });
  return h("div", { class: "panel wk-line" }, rows.length ? rows : h("p", { class: "muted" }, t("weeks_empty")),
    h("div", { class: "cal-legend small" }, h("span", {}, h("i", { class: "lg now" }), t("cal_k_now")), h("span", {}, h("i", { class: "lg hol" }), t("holiday")), h("span", {}, h("i", { class: "lg past" }), t("cal_k_past"))));
}

// ---------- three small cards under the line: where am I, next holiday, time to the next term
export function summaryCards(ov, cal) {
  const today = ov.today, pos = ov.position, cards = [];
  const tri = pos.state === "in_term" ? ov.trimesters.find((x) => x.index === pos.trimester) : null;
  if (tri) {
    const total = tri.weeks.length, left = Math.max(0, total - pos.week);
    cards.push(h("div", { class: "cal-card g" }, h("div", { class: "big" }, t("cal_week_of", { n: pos.week, m: total })), h("small", {}, `${triName(tri.name)} · ${t("cal_weeks_left", { n: left })}`)));
  } else cards.push(h("div", { class: "cal-card g" }, h("div", { class: "big" }, t("cal_no_term")), h("small", {}, t("outside_term"))));
  const hol = (cal.holidays || []).filter((x) => x.start && (x.end || x.start) >= today).sort((a, b) => a.start.localeCompare(b.start))[0];
  cards.push(hol
    ? h("div", { class: "cal-card" }, h("div", { class: "big" }, inDays(daysBetween(today, hol.start))), h("small", {}, `${t("cal_next_hol")}: ${localName(hol.name) || t("holiday")} (${fmtShort(hol.start)}${hol.end && hol.end !== hol.start ? " → " + fmtShort(hol.end) : ""})`))
    : h("div", { class: "cal-card" }, h("div", { class: "big" }, "—"), h("small", {}, t("cal_next_hol"))));
  if (tri) cards.push(h("div", { class: "cal-card" }, h("div", { class: "big" }, t("cal_days_n", { n: Math.max(0, daysBetween(today, tri.end)) })), h("small", {}, t("cal_to_end", { tri: triName(tri.name) }))));
  else {
    const next = (cal.trimesters || []).filter((x) => x.start && x.start > today).sort((a, b) => a.start.localeCompare(b.start))[0];
    cards.push(h("div", { class: "cal-card" }, h("div", { class: "big" }, next ? t("cal_days_n", { n: daysBetween(today, next.start) }) : "—"), h("small", {}, next ? t("cal_to_start", { tri: triName(next.name) }) : t("cal_no_next"))));
  }
  return h("div", { class: "cal-cards" }, cards);
}

// ---------- 2) one month, big
// state: { y, m }  (m = 0..11). onDay(iso) opens the notes of that day. workingDays: ["Sunday", ...]
const NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export function monthView({ cal, ov, idx, workingDays, view, onMove, onDay }) {
  const today = ov.today;
  const first = `${view.y}-${String(view.m + 1).padStart(2, "0")}-01`;
  const lastDay = new Date(Date.UTC(view.y, view.m + 1, 0)).getUTCDate();
  const start = addDays(first, -dow(first));
  const working = new Set(workingDays || []);
  const heads = [0, 1, 2, 3, 4, 5, 6].map((i) => h("div", { class: "mo-dn" }, fmtDate(addDays("2026-11-01", i), { weekday: "short" })));
  const cells = [];
  for (let r = 0; ; r++) {
    const rowStart = addDays(start, r * 7);
    if (r > 0 && rowStart.slice(0, 7) > first.slice(0, 7) && rowStart > `${first.slice(0, 8)}${String(lastDay).padStart(2, "0")}`) break;
    const wk = [0, 1, 2, 3, 4, 5, 6].map((i) => idx.weekOf.get(addDays(rowStart, i))).find(Boolean);
    cells.push(h("div", { class: "mo-wk", title: wk ? t("cal_week_n", { n: wk.n }) : "" }, wk ? wk.n : ""));
    for (let i = 0; i < 7; i++) {
      const iso = addDays(rowStart, i), inMonth = iso.slice(0, 7) === first.slice(0, 7);
      const holName = idx.hol.get(iso), evs = idx.ev.get(iso) || [];
      const cls = ["mo-d", !inMonth ? "mute" : "", !working.has(NAMES[dow(iso)]) ? "off" : "", holName ? "hol" : "", iso === today ? "today" : ""].filter(Boolean).join(" ");
      cells.push(h("button", { type: "button", class: cls, "aria-label": `${fmtDate(iso)}${holName ? ` · ${holName}` : ""}`, onClick: () => onDay(iso) },
        h("span", { class: "mo-n" }, Number(iso.slice(8))),
        holName ? h("small", { class: "mo-h", dir: "auto" }, holName) : null,
        ...evs.slice(0, holName ? 1 : 2).map((n) => h("small", { class: "mo-e", dir: "auto" }, localName(n))),
        evs.length > (holName ? 1 : 2) ? h("small", { class: "mo-more" }, `+${evs.length - (holName ? 1 : 2)}`) : null));
    }
  }
  const pos = idx.weekOf.get(first.slice(0, 7) === today.slice(0, 7) ? today : first) || null;
  return h("div", { class: "mo" },
    h("div", { class: "mo-head" },
      h("button", { class: "btn icon", "aria-label": t("cal_prev"), onClick: () => onMove(-1) }, h("span", { class: "flip" }, icon("chevron"))),
      h("h2", {}, fmtDate(first, { month: "long", year: "numeric" })),
      h("button", { class: "btn icon", "aria-label": t("cal_next"), onClick: () => onMove(1) }, icon("chevron")),
      h("button", { class: "btn small", onClick: () => onMove(0) }, t("cal_today")),
      pos ? h("span", { class: "muted small grow", style: { textAlign: "end" } }, t("cal_week_n", { n: pos.n })) : null),
    h("div", { class: "mo-grid" }, h("div", {}), heads, cells));
}

// ---------- the "coming up" list beside the month
export function upcoming(cal, ov, limit = 6) {
  const today = ov.today, items = [];
  for (const x of cal.holidays || []) if (x.start && (x.end || x.start) >= today) items.push({ d: x.start < today ? today : x.start, to: x.end, name: localName(x.name) || t("holiday"), hol: true, from: x.start });
  for (const x of cal.events || []) if (x.date && x.date >= today) items.push({ d: x.date, name: x.name });
  for (const tr of cal.trimesters || []) {
    if (tr.start && tr.start >= today) items.push({ d: tr.start, name: `${triName(tr.name)} · ${t("starts_on")}`, tri: true });
    if (tr.end && tr.end >= today) items.push({ d: tr.end, name: `${triName(tr.name)} · ${t("ends_on")}`, tri: true });
  }
  // holidays and term dates first; school events (there are many) only fill what is left, so they never push the holidays out
  const byDate = (a, b) => a.d.localeCompare(b.d);
  const main = items.filter((x) => x.hol || x.tri).sort(byDate).slice(0, limit - 2);
  const shown = [...main, ...items.filter((x) => !x.hol && !x.tri).sort(byDate).slice(0, limit - main.length)].sort(byDate);
  return h("div", { class: "mo-side" }, h("h3", {}, t("cal_coming")),
    shown.length ? shown.map((x) => h("div", { class: `mo-it${x.hol ? " h" : ""}${x.tri ? " tri" : ""}` },
      h("div", { class: "mo-date" }, h("b", {}, Number(x.d.slice(8))), h("span", {}, fmtDate(x.d, { month: "short" }))),
      h("div", {}, h("b", { dir: "auto" }, localName(x.name)), h("small", { class: "muted" }, `${x.hol && x.to && x.to !== x.from ? `${fmtShort(x.from)} → ${fmtShort(x.to)} · ` : ""}${inDays(daysBetween(today, x.d))}`))))
      : h("p", { class: "muted small" }, t("cal_nothing_next")));
}
