import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { todayIso, fmt12 } from "../labels.js";
import { timeInput12 } from "./time12.js";
import { testReminder } from "../reminders.js";

// Settings > Reminders
export function reminderPanel() {
  const box = h("div", { class: "panel" });
  let cfg = null, bg = null;
  const save = async (change) => { const r = await guarded(() => api.put("/api/reminders", change)); if (r) { cfg = r; draw(); toast(t("saved")); } };
  const check = (label, key) => h("label", { class: "row", style: { marginBottom: ".5rem" } },
    h("input", { type: "checkbox", checked: cfg[key], onChange: (e) => save({ [key]: e.target.checked }) }), label);

  function draw() {
    const mutedToday = cfg.muted_date === todayIso();
    box.replaceChildren(
      h("h3", {}, t("rem_title")), h("p", { class: "muted" }, t("rem_lead")),
      check(t("rem_on"), "enabled"),
      h("label", { class: "row", style: { marginBottom: ".5rem" } }, t("rem_before"),
        h("select", { style: { width: "auto" }, onChange: (e) => save({ minutes: +e.target.value }) },
          [5, 10, 15, 20, 30].map((m) => h("option", { value: m, selected: m === cfg.minutes }, t("rem_min", { n: m }))))),
      check(t("rem_skip_b2b"), "skip_back_to_back"),
      check(t("rem_sound"), "sound"),
      h("label", { class: "row", style: { marginBottom: ".5rem" } }, t("rem_ring"),
        h("select", { style: { width: "auto" }, onChange: (e) => save({ ring_seconds: +e.target.value }) },
          [15, 30, 60, 120, 300, 0].map((n) => h("option", { value: n, selected: n === (cfg.ring_seconds ?? 60) }, n === 0 ? t("rem_ring_until") : n < 60 ? t("rem_ring_s", { n }) : t("rem_min", { n: n / 60 }))))),
      mutedToday ? h("div", { class: "banner warn" }, icon("info"), h("div", { class: "grow" }, t("rem_muted_today")),
        h("button", { class: "btn small", onClick: () => save({ muted_date: "" }) }, t("rem_unmute"))) : null,
      h("div", { class: "row" }, h("button", { class: "btn", onClick: () => testReminder(cfg.sound) }, icon("clock"), t("rem_test"))),
      bg && (bg.support.tray)
        ? h("div", { class: "bg-box" }, h("b", {}, t("bg_title")),
            h("label", { class: "row" }, h("input", { type: "checkbox", checked: bg.keep_running, onChange: (e) => saveBg({ keep_running: e.target.checked }) }), t("bg_keep")),
            bg.support.autostart ? h("label", { class: "row" }, h("input", { type: "checkbox", checked: bg.autostart, onChange: (e) => saveBg({ autostart: e.target.checked }) }), t("bg_autostart")) : null,
            h("p", { class: "muted small" }, t("bg_note")))
        : h("p", { class: "muted small" }, t("rem_only_open")));
  }
  const saveBg = async (change) => { const r = await guarded(() => api.put("/api/background", change)); if (r) { bg = r; draw(); toast(t("saved")); } };
  Promise.all([guarded(() => api.get("/api/reminders")), guarded(() => api.get("/api/background"))]).then(([r, b]) => { if (r) { cfg = r; bg = b; draw(); } });
  return box;
}

// Settings > My reminders: things the teacher wants to be reminded of, once or every week.
const WEEK = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export function alarmsPanel() {
  const box = h("div", { class: "panel" });
  let data = null;
  const text = h("input", { type: "text", maxlength: 160, placeholder: t("alarm_text_ph"), "aria-label": t("alarm_text_ph") });
  const time = timeInput12("08:00");
  const date = h("input", { type: "date", "aria-label": t("alarm_date"), value: todayIso() });
  const days = new Set();
  const dayBtns = WEEK.slice(0, 5).concat([]).map((d) => h("button", { type: "button", class: "chip", "aria-pressed": "false", onClick: (e) => {
    days.has(d) ? days.delete(d) : days.add(d); e.currentTarget.classList.toggle("on", days.has(d)); e.currentTarget.setAttribute("aria-pressed", String(days.has(d)));
    date.style.display = days.size ? "none" : "";
  } }, t(`day_${d}`)));
  const add = async () => {
    if (!text.value.trim()) { text.focus(); return; }
    const r = await guarded(() => api.post("/api/alarms", { text: text.value, time: time.value, days: [...days], date: date.value }));
    if (r) { data = r; text.value = ""; draw(); toast(t("saved")); }
  };
  const act = async (fn) => { const r = await guarded(fn); if (r) { data = r; draw(); } };
  const when = (a) => a.days.length ? t("alarm_every", { days: a.days.map((d) => t(`day_${d}`)).join("، ") }) : t("alarm_on", { date: a.date });

  function draw() {
    const items = [...data.items].sort((a, b) => a.time.localeCompare(b.time));
    box.replaceChildren(h("h3", {}, t("alarm_title")), h("p", { class: "muted" }, t("alarm_lead")),
      items.length ? h("div", { class: "paper", style: { marginBottom: ".8rem" } }, h("table", { class: "tasks-table" }, h("tbody", {}, items.map((a) =>
        h("tr", { class: a.enabled ? "" : "done" },
          h("td", { class: "c-chk" }, h("input", { type: "checkbox", checked: a.enabled, "aria-label": t("alarm_on_off"), onChange: (e) => act(() => api.post(`/api/alarms/${a.id}/update`, { enabled: e.target.checked })) })),
          h("td", {}, h("b", {}, a.text), h("div", { class: "small muted" }, when(a))),
          h("td", { dir: "ltr", style: { fontWeight: 700 } }, fmt12(a.time)),
          h("td", { class: "c-act" }, h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => act(() => api.post(`/api/alarms/${a.id}/delete`, {})) }, icon("trash")))))))) : h("p", { class: "muted small" }, t("alarm_none")),
      h("div", { class: "alarm-add" }, text, time),
      h("div", { class: "row", style: { margin: ".6rem 0" } }, h("span", { class: "muted small" }, t("alarm_repeat")), dayBtns, date),
      h("button", { class: "btn primary", onClick: add }, icon("plus"), t("t_add")));
  }
  guarded(() => api.get("/api/alarms")).then((r) => { if (r) { data = r; draw(); } });
  return box;
}
