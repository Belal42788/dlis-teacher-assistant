import { h, icon } from "../dom.js";

// A page with nothing in it yet: say what it is for in one sentence, and give the one button that starts it.
export function emptyState({ icon: name = "file", title, text, action }) {
  return h("div", { class: "empty-state" },
    h("div", { class: "es-ico", "aria-hidden": "true" }, icon(name)),
    h("h3", {}, title),
    text ? h("p", { class: "muted" }, text) : null,
    action ? h("button", { class: "btn primary", onClick: action.onClick }, action.icon ? icon(action.icon) : null, action.label) : null);
}
