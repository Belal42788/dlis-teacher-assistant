import { h, icon, toast } from "./dom.js";
import { api } from "./api.js";
import { t } from "./i18n.js";
import { roomLabel, todayIso, fmt12 } from "./labels.js";

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
  const close = () => { clearInterval(ringTimer); card.remove(); try { window.pywebview?.api?.reminder_stop?.(); } catch { /* browser mode */ } };
  const when = item.alarm ? t("rem_alarm", { what: item.label }) : minutesLeft <= 0 ? t("rem_now", { what: item.label, time: fmt12(item.start) }) : t("rem_in", { what: item.label, n: Math.ceil(minutesLeft), time: fmt12(item.start) });
  card.append(
    h("div", { class: "rem-head" }, icon("clock"), h("b", {}, when)),
    h("div", { class: "rem-actions" },
      h("button", { class: "btn small primary", onClick: () => { handled.delete(key); if (item.alarm) alarmSnooze.set(key, { wake: Date.now() + 5 * 60000, item }); else snoozed.set(key, Date.now() + 5 * 60000); close(); } }, t("rem_snooze")),
      h("button", { class: "btn small", onClick: () => { handled.add(key); close(); } }, t("rem_dismiss")),
      item.alarm ? null : h("button", { class: "btn small ghost", onClick: async () => { await save({ muted_date: todayIso() }); close(); toast(t("rem_muted_today")); } }, t("rem_mute_today")),
      item.alarm ? null : h("button", { class: "btn small ghost", onClick: async () => { await save({ enabled: false }); close(); toast(t("rem_off_note")); } }, t("rem_off_always"))));
  container().append(card);
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
async function alarmsTick() {
  const n = nowMin(), today = todayIso(), dow = new Date().getDay();
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const { items } = await api.get("/api/alarms");
  for (const a of items) {
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

let seenDate = todayIso();
async function tick() {
  if (seenDate !== todayIso()) {      // the app was left open overnight: show the new day
    seenDate = todayIso();
    if (["", "#/today", "#/"].includes(location.hash)) window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
  try { cfg = await api.get("/api/reminders"); await alarmsTick(); } catch { /* try again in a moment */ }
  try {
    if (!cfg.enabled || cfg.muted_date === todayIso()) return;
    const { items, date } = await loadDay();
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
  } catch { /* stay quiet; try again in a moment */ }
}

export function startReminders() {
  if (timer) return;
  window.__dlisTick = tick;
  timer = setInterval(tick, 20000);
  setTimeout(tick, 1500);
}

export function forgetDay() { day = null; }

// For the "Try a reminder" button in Settings.
export function testReminder(sound) {
  const was = cfg; cfg = { ...(cfg || {}), sound };
  show({ label: t("rem_test_what"), start: "--:--" }, "test|" + Date.now(), 10);
  cfg = was;
}
