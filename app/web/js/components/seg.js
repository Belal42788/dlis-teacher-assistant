import { h } from "../dom.js";

// Tabs for pages with several unrelated sections: shows one section at a time and remembers which one.
const remembered = {};
export function segTabs(key, items) {   // items: [[id, label, element], ...]
  const ids = items.map((x) => x[0]);
  const btns = items.map(([id, label]) => h("button", { class: "seg-btn", role: "tab", "data-tab": id, onClick: () => show(id) }, label));
  const bar = h("div", { class: "seg", role: "tablist" }, btns);
  function show(id) {
    remembered[key] = id;
    items.forEach(([k, , el]) => { el.hidden = k !== id; });
    btns.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === id)));
  }
  show(ids.includes(remembered[key]) ? remembered[key] : ids[0]);
  return [bar, ...items.map((x) => x[2])];
}
