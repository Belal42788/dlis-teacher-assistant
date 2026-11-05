import { h } from "../dom.js";
import { t, getLang } from "../i18n.js";

// A date picked as day / month / year (in that order, whatever the computer's own settings are).
// It behaves like an <input>: read and write .value as "YYYY-MM-DD" ("" when not complete), and it fires "change".
// The three dropdowns are built once per language and copied for every field: a page with dozens of dates
// (the calendar) used to spend a third of a second creating the same month names and options again and again.
let tpl = null;
function templates() {
  const lang = getLang(), now = new Date().getFullYear();
  if (tpl && tpl.lang === lang && tpl.now === now) return tpl;
  const loc = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
  const fmt = new Intl.DateTimeFormat(loc, { month: "long", timeZone: "UTC" });
  const dd = h("select", { "aria-label": t("date_day") }, h("option", { value: "" }, t("date_day")), Array.from({ length: 31 }, (_, i) => h("option", { value: i + 1 }, i + 1)));
  const mm = h("select", { "aria-label": t("date_month") }, h("option", { value: "" }, t("date_month")),
    Array.from({ length: 12 }, (_, i) => h("option", { value: i + 1 }, fmt.format(new Date(Date.UTC(2026, i, 1))))));
  const yy = h("select", { "aria-label": t("date_year") }, h("option", { value: "" }, t("date_year")), Array.from({ length: 9 }, (_, i) => h("option", { value: now - 2 + i }, now - 2 + i)));
  tpl = { lang, now, dd, mm, yy };
  return tpl;
}

export function dateField({ value = "", label = "", onChange } = {}) {
  const pad = (n) => String(n).padStart(2, "0");
  const T = templates();
  const dd = T.dd.cloneNode(true), mm = T.mm.cloneNode(true), yy = T.yy.cloneNode(true);
  const el = h("div", { class: "date3", role: "group", "aria-label": label }, dd, mm, yy);
  const get = () => (dd.value && mm.value && yy.value ? `${yy.value}-${pad(mm.value)}-${pad(dd.value)}` : "");
  const set = (v) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || "");
    if (!m) { dd.value = mm.value = yy.value = ""; return; }
    if (![...yy.options].some((o) => o.value === String(+m[1]))) yy.append(h("option", { value: +m[1] }, +m[1]));
    yy.value = String(+m[1]); mm.value = String(+m[2]); dd.value = String(+m[3]);
  };
  Object.defineProperty(el, "value", { get, set });
  set(value);
  // keep the day inside the month (31 Feb -> 28/29 Feb)
  const fit = () => {
    if (!mm.value) return;
    const y = +yy.value || 2024, last = new Date(Date.UTC(y, +mm.value, 0)).getUTCDate();
    if (+dd.value > last) dd.value = String(last);
  };
  for (const s of [dd, mm, yy]) s.addEventListener("change", (e) => { e.stopPropagation(); fit(); el.dispatchEvent(new Event("change")); if (onChange) onChange(get()); });
  return el;
}
