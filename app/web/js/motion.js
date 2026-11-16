// Motion in one place. The teacher can turn all of it off in Settings (for a slow computer); the system's own "reduce motion" setting is
// respected too. Everything animated in CSS is switched off by the `still` class on <html>; the little motion done from code asks motionOn().
const KEY = "dlis.motion";
const reduceQuery = () => (window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false });
export function getMotion() {
  try { return localStorage.getItem(KEY) === "off" ? "off" : "on"; } catch { return "on"; }
}
export const motionOn = () => getMotion() === "on" && !reduceQuery().matches;
export function applyMotion() { document.documentElement.classList.toggle("still", !motionOn()); }
export function setMotion(v) {
  try { localStorage.setItem(KEY, v); } catch { /* still changes for this session */ }
  applyMotion();
}

/** Play a short CSS animation class on an element and remove it when it ends (does nothing when motion is off). */
export function play(el, cls, ms = 600) {
  if (!el || !motionOn()) return;
  el.classList.remove(cls);
  void el.offsetWidth;                    // restart it if it is already playing
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), ms);
}

/** Let an element leave before it is removed: it fades and folds its height away, then `then()` runs (at once when motion is off). */
export function leave(el, then) {
  if (!el || !motionOn()) { then && then(); return Promise.resolve(); }
  return new Promise((resolve) => {
    const h = el.offsetHeight;
    el.style.height = `${h}px`;
    el.classList.add("leaving");
    void el.offsetWidth;
    el.style.height = "0px";
    setTimeout(() => { then && then(); resolve(); }, 260);
  });
}

// A button that switches something (a chip, a present/absent toggle) answers the touch with a small pulse.
// (Many of them are redrawn by their own click, so the pulse goes to whatever stands in the same place afterwards.)
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("[aria-pressed]");
  if (!b || !b.parentElement) return;
  const parent = b.parentElement, at = [...parent.children].indexOf(b);
  setTimeout(() => { const now = b.isConnected ? b : parent.isConnected ? parent.children[at] : null; if (now && now.hasAttribute("aria-pressed")) play(now, "pulse", 350); }, 0);
}, true);

/** A table row on its way out slides away and fades (heights of table rows cannot be folded smoothly); resolves when it is gone (at once when motion is off). */
export function leaveRow(el) {
  if (!el || !motionOn()) return Promise.resolve();
  el.classList.add("row-out");
  return new Promise((resolve) => setTimeout(resolve, 230));
}
