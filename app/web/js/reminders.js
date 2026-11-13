import { h, icon, toast } from "./dom.js";
import { api } from "./api.js";
import { t } from "./i18n.js";
import { roomLabel, todayIso, fmt12, addDays, fmtShort, localName, fmtDate } from "./labels.js";

// A small pop-up shortly before each lesson or duty, while the app is open.
let cfg = null, day = null, dayAt = 0, timer = null;
const handled = new Set();   // reminders already shown / answered today
const snoozed = new Map();   // key -> time it should pop up again
const alarmSnooze = new Map(); // the teacher's own reminders that were snoozed

const toMin = (hhmm) => { const [a, b] = String(hhmm || "99:99").split(":").map(Number); return a * 60 + b; };
const nowMin = () => { const d = new Date(); return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60; };

function container() {
  let c = document.getElementById("reminders");
  if (!c) { c = h("div", { id: "reminders", "aria-live": "polite" }); document.body.append(c); }
  return c;
}

// With three or more alerts at once (for example when the app opens late), one button dismisses them all instead of leaving a pile over the page.
function syncAll() {
  const c = container(), cards = [...c.querySelectorAll(".reminder")];
  c.querySelector(".rem-all")?.remove();
  if (cards.length < 3) return;
  c.prepend(h("button", { class: "btn small rem-all", onClick: () => cards.forEach((x) => x.querySelector(".rem-actions button:nth-child(2)")?.click()) }, t("rem_dismiss_all", { n: cards.length })));
}

const nativeSound = () => !!window.pywebview?.api?.reminder_alert;   // the desktop app rings by itself, also when minimised
function beep() {
  if (!cfg?.sound || nativeSound()) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.28, 0.56].forEach((at) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.22);
      o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.25);
    });
    setTimeout(() => ctx.close(), 1500);
  } catch { /* sound is optional */ }
}

async function save(change) { cfg = await api.put("/api/reminders", change); return cfg; }

function show(item, key, minutesLeft) {
  const card = h("div", { class: "reminder", role: "alert" });
  let ringTimer = null;
  const close = () => { clearInterval(ringTimer); card.remove(); syncAll(); try { window.pywebview?.api?.reminder_stop?.(); } catch { /* browser mode */ } };
  const when = item.alarm ? t("rem_alarm", { what: item.label }) : minutesLeft <= 0 ? t("rem_now", { what: item.label, time: fmt12(item.start) }) : t("rem_in", { what: item.label, n: Math.ceil(minutesLeft), time: fmt12(item.start) });
  card.append(
    h("div", { class: "rem-head" }, icon("clock"), h("b", {}, when)),
    h("div", { class: "rem-actions" },
      h("button", { class: "btn small", onClick: () => { handled.delete(key); if (item.alarm) alarmSnooze.set(key, { wake: Date.now() + 5 * 60000, item }); else snoozed.set(key, Date.now() + 5 * 60000); close(); } }, t("rem_snooze")),
      h("button", { class: "btn small", onClick: () => { handled.add(key); close(); } }, t("rem_dismiss")),
      item.alarm ? null : h("button", { class: "btn small", onClick: async () => { await save({ muted_date: todayIso() }); close(); toast(t("rem_muted_today")); } }, t("rem_mute_today"))));
  container().append(card);
  syncAll();
  beep();
  // keep ringing until the teacher answers, or until the chosen ring time is over (0 = until answered)
  const ringMs = (cfg?.ring_seconds ?? 60) * 1000, began = Date.now();
  ringTimer = setInterval(() => {
    if (!card.isConnected || (ringMs && Date.now() - began >= ringMs)) { clearInterval(ringTimer); return; }
    beep();
  }, 2500);
  try { window.pywebview?.api?.reminder_alert?.(item.alarm ? item.label : `${item.label} ${fmt12(item.start)}`, !!cfg?.sound, cfg?.ring_seconds ?? 60); } catch { /* browser mode */ }
}

async function loadDay() {
  if (day && Date.now() - dayAt < 3 * 60000 && day.date === todayIso()) return day;
  const [d, structure] = await Promise.all([api.get(`/api/today?date=${todayIso()}`), api.get("/api/structure")]);
  const items = [
    ...d.sessions.filter((s) => s.start).map((s) => {
      const room = structure.rooms.find((r) => r.id === s.room_id);
      return { start: s.start, end: s.end, label: `${room ? roomLabel(room, structure) : s.room_id} · ${t("rem_period", { n: s.period })}` };
    }),
    ...(d.duties || []).map((u) => ({ start: u.start, end: u.end, label: t(`duty_${u.kind}`) })),
  ].sort((a, b) => toMin(a.start) - toMin(b.start));
  day = { date: todayIso(), items };
  dayAt = Date.now();
  return day;
}

// The teacher's own reminders ("print the quiz"): always on, at the exact time.
let alarmsList = [];
function alarmsCheck() {
  const n = nowMin(), today = todayIso(), dow = new Date().getDay();
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  for (const a of alarmsList) {
    if (!a.enabled) continue;
    const key = `alarm|${today}|${a.id}`;
    if (handled.has(key) || alarmSnooze.has(key)) continue;
    const todayOk = a.days.length ? a.days.includes(DAYS[dow]) : a.date === today;
    const start = toMin(a.time);
    if (!todayOk || n < start || n >= start + 3) continue;
    handled.add(key);
    show({ alarm: true, label: a.text, start: a.time }, key, 0);
  }
  for (const [key, v] of [...alarmSnooze]) if (Date.now() >= v.wake) { alarmSnooze.delete(key); show(v.item, key, 0); }
}

// The day before a school event (trip, exams, parents' meeting...) a reminder pops up at the chosen time.
// On the last working day before a weekend it also covers the events of the days that follow.
let eventsShown = "";
async function eventsEveTick() {
  if (!cfg?.events_eve || eventsShown === todayIso() || nowMin() < toMin(cfg.events_time || "13:00")) return;
  eventsShown = todayIso();
  const [cal, st] = await Promise.all([api.get("/api/calendar"), api.get("/api/settings")]);
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const working = (iso) => (st.working_days || []).includes(DAYS[new Date(`${iso}T00:00:00Z`).getUTCDay()]);
  const today = todayIso();
  let last = addDays(today, 1);
  for (let i = 0; i < 7 && !working(last); i++) last = addDays(last, 1);   // through the next working day
  const list = (cal.events || []).filter((e) => e.date > today && e.date <= last && e.name);
  if (!list.length) return;
  const text = list.map((e) => (e.date === addDays(today, 1) ? "" : `${fmtShort(e.date)}: `) + localName(e.name)).join(" · ");
  show({ alarm: true, label: t("rem_events_tomorrow", { names: text }), start: cfg.events_time }, `events|${today}`, 0);
}

// In the evening: how many lessons tomorrow, and which classes still have no lesson plan.
let tomorrowShown = "";
async function tomorrowTick() {
  if (cfg?.tomorrow === false || tomorrowShown === todayIso() || nowMin() < toMin(cfg?.tomorrow_time || "19:00")) return;
  tomorrowShown = todayIso();
  const r = await api.get(`/api/tomorrow?date=${todayIso()}`);
  if (!r.found) return;
  const dayName = r.tomorrow ? t("rem_tomorrow") : fmtDate(r.date, { weekday: "long", day: "numeric", month: "short" });
  const text = r.missing.length ? t("rem_tmr_missing", { day: dayName, n: r.lessons, names: r.missing.join("، ") }) : t("rem_tmr_ready", { day: dayName, n: r.lessons });
  show({ alarm: true, label: text, start: cfg.tomorrow_time }, `tomorrow|${todayIso()}`, 0);
}

// Every school day, when the prayer break starts.
let prayerAt = null;
async function loadPrayer() {
  const today = todayIso();
  if (prayerAt && prayerAt.date === today) return;
  const [d, tt] = await Promise.all([api.get(`/api/today?date=${today}`), api.get("/api/timetable")]);
  prayerAt = { date: today, time: d.school_day && tt.bell && tt.bell.prayer ? tt.bell.prayer.start : "" };
}
function prayerCheck() {
  if (cfg?.prayer === false || !prayerAt) return;
  const today = todayIso(), n = nowMin(), key = `prayer|${today}`;
  if (prayerAt.date !== today || !prayerAt.time || handled.has(key) || n < toMin(prayerAt.time) || n >= toMin(prayerAt.time) + 5) return;
  handled.add(key);
  show({ alarm: true, label: t("rem_prayer"), start: prayerAt.time }, key, 0);
}

let seenDate = todayIso();
// Every 20 seconds: fetch what the checks need (settings, reminders, today's lessons). Every second: compare the clock with what was fetched,
// so a reminder shows at its minute and not up to 20 seconds late.
async function refresh() {
  if (seenDate !== todayIso()) {      // the app was left open overnight: show the new day
    seenDate = todayIso();
    if (["", "#/today", "#/"].includes(location.hash)) window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
  try {
    cfg = await api.get("/api/reminders");
    alarmsList = (await api.get("/api/alarms")).items;
    await eventsEveTick(); await tomorrowTick(); await loadPrayer();
    if (cfg.enabled && cfg.muted_date !== todayIso()) await loadDay();
  } catch { /* try again in a moment */ }
  check();
}

function check() {
  if (!cfg) return;
  try { alarmsCheck(); prayerCheck(); lessonsCheck(); } catch { /* stay quiet; try again in a second */ }
}

function lessonsCheck() {
  if (!cfg.enabled || cfg.muted_date === todayIso() || !day || day.date !== todayIso()) return;
  const { items, date } = day;
  const n = nowMin();
  items.forEach((it, i) => {
    const key = `${date}|${it.start}|${it.label}`;
    const start = toMin(it.start);
    if (handled.has(key)) return;
    const wake = snoozed.get(key);
    if (wake) {                       // the teacher asked to be reminded again
      if (n >= start + 2) { snoozed.delete(key); handled.add(key); return; }
      if (Date.now() < wake) return;
      snoozed.delete(key); show(it, key, start - n); return;
    }
    if (n < start - cfg.minutes || n >= start + 2) return;
    handled.add(key);                 // shown once
    // Coming straight from another lesson or duty: the teacher is already on the move.
    const prev = items[i - 1];
    if (cfg.skip_back_to_back && prev && start - toMin(prev.end) <= 10) return;
    show(it, key, start - n);
  });
}

export function startReminders() {
  if (timer) return;
  window.__dlisTick = refresh;
  timer = setInterval(refresh, 20000);
  setInterval(check, 1000);
  setTimeout(refresh, 1500);
}

export function forgetDay() { day = null; }

// For the "Try a reminder" button in Settings.
export function testReminder(sound) {
  const was = cfg; cfg = { ...(cfg || {}), sound };
  show({ label: t("rem_test_what"), start: "--:--" }, "test|" + Date.now(), 10);
  cfg = was;
}
