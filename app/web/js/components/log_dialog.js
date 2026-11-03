import { h, modal, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { fmtShort } from "../labels.js";

// A short line saying where the class stopped last time (used on Today and on the Lesson log page).
export function lastLine(e) {
  if (!e) return null;
  const bits = [e.topic, e.slide ? t("log_slide_of", { n: `\u2066${e.slide}${e.total ? ` / ${e.total}` : ""}\u2069`, total: "" }) : ""].filter(Boolean).join(" · ");
  return h("div", { class: "last-log" },
    h("div", { class: "small muted" }, `${t("log_last_time")} (${fmtShort(e.date)}): `, h("b", {}, bits || "—")),
    e.total && e.slide ? h("div", { class: "progress", "aria-hidden": "true" }, h("i", { style: { width: `${Math.min(100, Math.round(e.slide / e.total * 100))}%` } })) : null,
    e.next_note ? h("div", { class: "remember" }, `📌 ${e.next_note}`) : null);
}

// opts: { room_id, date, period, entry (this lesson's existing entry), last (previous lesson's entry), onSaved }
export function logDialog(opts) {
  const e = opts.entry || {};
  const prev = opts.last || {};
  const topic = h("input", { type: "text", maxlength: 120, value: e.topic ?? (opts.plan && opts.plan.topic) ?? prev.topic ?? "", placeholder: t("log_topic") });
  const slide = h("input", { type: "number", min: 1, max: 2000, value: e.slide ?? "", style: { width: "6em" } });
  const total = h("input", { type: "number", min: 1, max: 2000, value: e.total ?? (opts.plan && opts.plan.slides) ?? prev.total ?? "", style: { width: "6em" } });
  const note = h("textarea", { rows: 3, maxlength: 1000, placeholder: t("log_note_ph") }, e.note ?? "");
  const next = h("input", { type: "text", maxlength: 300, value: e.next_note ?? "", placeholder: t("log_next_ph") });
  return modal({
    title: t("log_title"),
    body: h("div", { class: "grid-gap" },
      prev.slide ? h("p", { class: "muted small" }, t("log_prev_hint", { n: prev.slide })) : null,
      h("label", { class: "field" }, h("span", { class: "label" }, t("log_topic")), topic),
      h("div", { class: "row" }, h("label", { class: "row" }, h("b", {}, t("log_reached")), slide), h("label", { class: "row" }, t("log_of_total"), total)),
      h("label", { class: "field" }, h("span", { class: "label" }, t("log_note")), note),
      h("label", { class: "field" }, h("span", { class: "label" }, t("log_next")), next)),
    actions: [{ label: t("cancel") }, { label: t("save"), kind: "primary", onClick: async () => {
      const r = await guarded(() => api.post("/api/log", { room_id: opts.room_id, date: opts.date, period: opts.period,
        topic: topic.value, slide: slide.value, total: total.value, note: note.value, next_note: next.value }));
      if (!r) return false;
      toast(t("saved")); opts.onSaved && opts.onSaved(r);
    } }],
  });
}
