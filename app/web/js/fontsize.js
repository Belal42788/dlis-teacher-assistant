// Text size: small / normal / large. It is a setting of this computer (a teacher with a big screen may want large),
// so it is kept in the browser's own storage, not in the school's data.
const SIZES = { s: 14.5, m: 16, l: 18 };
const KEY = "dlis.fontsize";
export function getFontSize() {
  try { const v = localStorage.getItem(KEY); return SIZES[v] ? v : "m"; } catch { return "m"; }
}
export function applyFontSize() { document.documentElement.style.fontSize = SIZES[getFontSize()] + "px"; }
export function setFontSize(v) {
  try { localStorage.setItem(KEY, v); } catch { /* private window: the size still changes for this session */ }
  document.documentElement.style.fontSize = (SIZES[v] || 16) + "px";
}
