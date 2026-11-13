// Small helpers: build DOM nodes, modals, toasts. No framework needed.
import { t } from "./i18n.js";

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "open") el[k] = !!v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}

function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
}

export const $ = (sel, root = document) => root.querySelector(sel);

// replaceChildren() would print "null"/"false" as text; make it skip empty values and accept nested lists.
const _replace = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...kids) {
  const clean = kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false)
    .map((k) => (k.nodeType ? k : document.createTextNode(String(k))));
  _replace.apply(this, clean);
};

const ICONS = {
  today: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 3v3M16 3v3"/><path d="M8 14h3"/>',
  classes: '<circle cx="9" cy="8" r="3.2"/><path d="M3 19c.5-3.2 3-5 6-5s5.5 1.8 6 5"/><circle cx="17" cy="9" r="2.4"/><path d="M16.5 14.2c2.4.1 4 1.6 4.5 4.3"/>',
  timetable: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16M15 4v16"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 3v3M16 3v3M8 14h.01M12 14h.01M16 14h.01M8 17.5h.01M12 17.5h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  chevron: '<path d="M9 5l7 7-7 7"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  warn: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5h.01"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
  tool: '<path d="M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2-.5-.5-2z"/>',
  tasks: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  slides: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  send: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.6-4 3.5-6 7-6s6.4 2 7 6"/>',
  phone: '<path d="M6 4h3l1.5 4-2 1.5a11 11 0 0 0 6 6L16 13.5l4 1.5v3a2 2 0 0 1-2 2A15 15 0 0 1 4 6a2 2 0 0 1 2-2z"/>',
  megaphone: '<path d="M3 10v4h3l7 4V6L6 10z"/><path d="M16 9a4 4 0 010 6"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.5 7.5l8.5 6 8.5-6"/>',
};

export function icon(name) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("class", name === "back" || name === "chevron" ? "i dir" : "i");
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name] || "";
  return s;
}

export function toast(message, kind = "ok") {
  const box = document.getElementById("toasts");
  const el = h("div", { class: `toast ${kind}` }, message);
  box.replaceChildren(el);   // one message at a time, they do not pile up
  setTimeout(() => el.remove(), kind === "error" ? 6500 : 2600);
}

export function modal({ title, body, actions = [], onClose, wide = false }) {
  const overlay = h("div", { class: "overlay", role: "dialog", "aria-modal": "true", "aria-label": title });
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); onClose && onClose(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  const box = h("div", { class: "modal", style: wide ? { width: "min(820px, 100%)" } : null },
    h("header", {}, h("h3", {}, title), h("button", { class: "btn icon ghost", "aria-label": t("close"), onClick: close }, icon("close"))),
    h("div", { class: "body" }, body),
    actions.length ? h("footer", {}, actions.map((a) => h("button", {
      class: `btn ${a.kind || ""}`, disabled: a.disabled,
      onClick: async (ev) => { const r = await a.onClick?.(ev, close); if (a.close !== false && r !== false) close(); },
    }, a.label))) : null);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  overlay.append(box);
  document.body.append(overlay);
  const first = box.querySelector("input, select, textarea, button.primary");
  first && first.focus();
  return { close, el: box };
}

export function confirmBox(message, { okLabel, danger = true } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    modal({
      title: t("are_you_sure"),
      body: h("p", {}, message),
      onClose: () => finish(false),
      actions: [
        { label: t("cancel"), onClick: () => finish(false) },
        { label: okLabel || t("yes_delete"), kind: danger ? "danger" : "primary", onClick: () => finish(true) },
      ],
    });
  });
}

export function debounce(fn, ms) {
  let id;
  return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); };
}

export function readFileB64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}
