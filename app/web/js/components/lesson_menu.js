import { h, icon } from "../dom.js";
import { t } from "../i18n.js";

// A lesson's "more" menu closes when you press anywhere else or Esc
document.addEventListener("pointerdown", (e) => { document.querySelectorAll(".lesson-more[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; }); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.querySelectorAll(".lesson-more[open]").forEach((d) => { d.open = false; }); });

// The "more" menu of a lesson: a small floating list, so opening it never pushes the other lessons down.
export const menuItem = (label, onClick, opts = {}) => h(opts.href ? "a" : "button", { class: `menu-item${opts.danger ? " danger" : ""}`, type: opts.href ? null : "button", href: opts.href || null,
  onClick: (e) => { e.currentTarget.closest("details").open = false; onClick && onClick(e); } }, opts.icon ? icon(opts.icon) : null, label);
export const moreMenu = (items) => {
  const box = h("details", { class: "lesson-more", onToggle: (e) => {
    const slotEl = e.currentTarget.closest(".slot"); if (slotEl) slotEl.classList.toggle("menu-open", e.currentTarget.open);
    if (e.currentTarget.open) document.querySelectorAll(".lesson-more[open]").forEach((d) => { if (d !== box) d.open = false; });
  } }, h("summary", { class: "kebab", "aria-label": t("more"), title: t("more") }, "⋯"), h("div", { class: "menu" }, items));
  return box;
};
