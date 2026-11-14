import { h, icon } from "../dom.js";
import { t } from "../i18n.js";

// "Check before you go on": a button that does something (a primary button, or one marked data-check) first looks over the fields around it.
// A field is checked when it is marked required (the attribute, or data-required) or has a rule: number min/max, url, email, pattern, minlength.
// Anything missing or wrong is marked, listed in one calm box at the top of that form, and the first one gets the cursor. Nothing is sent until it is right.
const RULED = "[required],[data-required],input[type=number][min],input[type=number][max],input[type=url],input[type=email],[pattern],[minlength]";
const FIELDS = "input, textarea, select";
const SCOPE = ".modal, form, [data-form], .panel, .card";

const shown = (el) => !el.disabled && el.type !== "hidden" && !el.closest("[hidden]") && el.getClientRects().length > 0;

export function labelOf(el) {
  const own = el.getAttribute("data-label") || el.getAttribute("aria-label");
  if (own) return own.trim();
  const lab = el.closest("label")?.querySelector(".label")?.textContent || el.closest(".field")?.querySelector(".label")?.textContent;
  return (lab || el.getAttribute("placeholder") || "").trim();
}

// what is wrong with one field: "" when it is fine, otherwise a short reason
export function why(el) {
  const required = el.required || el.hasAttribute("data-required");
  if (el.type === "checkbox" || el.type === "radio") return required && !el.checked ? t("v_tick") : "";
  if (el.type === "file") return required && !(el.files && el.files.length) ? t("v_file") : "";
  const v = String(el.value ?? "").trim();
  if (!v) return required ? (el.tagName === "SELECT" ? t("v_pick") : t("v_required")) : "";
  if (el.type === "number") {
    const n = Number(v), min = el.min !== "" ? Number(el.min) : null, max = el.max !== "" ? Number(el.max) : null;
    if (Number.isNaN(n)) return t("v_number");
    if ((min !== null && n < min) || (max !== null && n > max)) return min !== null && max !== null ? t("v_range", { min, max }) : min !== null ? t("v_min", { min }) : t("v_max", { max });
  }
  if (el.type === "url") { try { if (!/^https?:$/.test(new URL(v).protocol)) return t("v_url"); } catch { return t("v_url"); } }
  if (el.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) return t("v_email");
  const pat = el.getAttribute("pattern");
  if (pat) { try { if (!new RegExp(`^(?:${pat})$`).test(v)) return t("v_pattern"); } catch { /* a bad pattern never blocks */ } }
  const ml = Number(el.getAttribute("minlength") || 0);
  if (ml && v.length < ml) return t("v_minlen", { n: ml });
  return "";
}

export function problems(root) {
  const mine = (el) => { const f = el.closest("[data-form]"); return !f || f === root || f.contains(root); };   // a small form inside a big panel is checked only by its own button
  return [...root.querySelectorAll(FIELDS)].filter((el) => shown(el) && el.matches(RULED) && mine(el))
    .map((el) => ({ el, label: labelOf(el), reason: why(el) })).filter((p) => p.reason);
}

export function clearProblems(host) {
  host.querySelectorAll(".v-banner").forEach((b) => b.remove());
  host.querySelectorAll("[aria-invalid]").forEach((el) => { el.removeAttribute("aria-invalid"); el.classList.remove("invalid"); });
}

// mark the fields, list them in a box at the top of the form, move the cursor to the first one
export function showProblems(root, list) {
  const host = root.matches(".modal") ? root.querySelector(".body") || root : root;
  clearProblems(host);
  const items = list.map(({ el, label, reason }) => h("li", {}, h("button", { type: "button", class: "linklike", onClick: () => { el.scrollIntoView?.({ block: "center" }); el.focus?.(); } }, label ? `${label}: ` : "", reason)));
  host.prepend(h("div", { class: "v-banner", role: "alert" }, icon("info"), h("div", {}, h("b", {}, t("v_title")), h("ul", {}, items))));
  for (const { el } of list) {
    el.setAttribute("aria-invalid", "true"); el.classList.add("invalid");
    const done = () => {
      if (why(el)) return;
      el.removeAttribute("aria-invalid"); el.classList.remove("invalid"); el.removeEventListener("input", done); el.removeEventListener("change", done);
      if (!host.querySelector("[aria-invalid]")) host.querySelectorAll(".v-banner").forEach((b) => b.remove());
    };
    el.addEventListener("input", done); el.addEventListener("change", done);
  }
  const first = list[0].el; first.scrollIntoView?.({ block: "center" }); first.focus?.();
}

// the form around a button: the nearest dialog, <form>, [data-form], panel or card that has a field with a rule
function scopeOf(btn) {
  for (let s = btn.parentElement?.closest(SCOPE); s; s = s.parentElement?.closest(SCOPE)) {
    if (s.querySelector(RULED)) return s;
    if (s.matches(".modal, form, [data-form]")) return null;   // a form without rules: nothing to check
  }
  return null;
}

// Runs before any button's own click handler (capture phase), so a wrong form never reaches it.
export function installValidation() {
  document.addEventListener("click", (ev) => {
    const btn = ev.target instanceof Element ? ev.target.closest("button") : null;
    if (!btn || btn.disabled || !btn.matches(".primary, [data-check]") || btn.hasAttribute("data-nocheck")) return;
    const scope = scopeOf(btn); if (!scope) return;
    const list = problems(scope); if (!list.length) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    showProblems(scope, list);
  }, true);
}
