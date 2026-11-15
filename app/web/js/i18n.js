// All words on screen live in two files, one per language: i18n_ar.js and i18n_en.js. Only the language in use is loaded,
// so the other one costs nothing. t("key", {n: 3}) fills {n}. Every key must exist in both files (scripts/check_i18n.sh).
let lang = "en";
const packs = {};
export const getLang = () => lang;

/** Fetch a language's words (once). Nothing can be drawn with t() until the language in use has been loaded. */
export async function loadLang(l) {
  const code = l === "ar" ? "ar" : "en";
  if (!packs[code]) packs[code] = (await import(`./i18n_${code}.js`)).default;
  return code;
}

/** Switch the language: loads it if needed, then turns the page to it (direction, title). */
export async function setLang(l) {
  lang = await loadLang(l);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.title = t("app_name");
}

export const hasKey = (k) => Object.prototype.hasOwnProperty.call(packs[lang] || packs.en || {}, k);
export function t(key, vars) {
  const s = (packs[lang] && packs[lang][key]) ?? (packs.en && packs.en[key]) ?? key;
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? "")) : s;
}
