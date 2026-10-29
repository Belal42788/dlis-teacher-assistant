import { h } from "../dom.js";
import { t } from "../i18n.js";

// A 12-hour time picker (hour, minute, AM/PM). The browser's own time box follows the computer's settings, which may be 24-hour.
// `.value` is always "HH:MM" (24-hour) for the app.
export function timeInput12(initial = "08:00") {
  const [h0, m0] = initial.split(":").map(Number);
  const hour = h("select", { "aria-label": t("time_hour") }, Array.from({ length: 12 }, (_, i) => h("option", { value: i + 1 }, String(i + 1))));
  const min = h("select", { "aria-label": t("time_minute") }, Array.from({ length: 60 }, (_, i) => h("option", { value: i }, String(i).padStart(2, "0"))));
  const ampm = h("select", { "aria-label": "AM/PM" }, h("option", { value: "am" }, t("time_am")), h("option", { value: "pm" }, t("time_pm")));
  hour.value = h0 % 12 || 12; min.value = m0; ampm.value = h0 >= 12 ? "pm" : "am";
  const box = h("span", { class: "time12", dir: "ltr" }, hour, ":", min, ampm);
  Object.defineProperty(box, "value", { get() { return `${String((+hour.value % 12) + (ampm.value === "pm" ? 12 : 0)).padStart(2, "0")}:${String(+min.value).padStart(2, "0")}`; } });
  return box;
}
