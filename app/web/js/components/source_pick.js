import { h } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";

export const picked = { id: "" };   // the chosen source stays chosen while the teacher moves between pages

// A small "Use my slides" selector. Returns null when there are no sources yet (nothing to choose).
export async function sourcePicker(onPick) {
  let list = [];
  try { list = (await api.get("/api/sources")).sources.filter((s) => s.chars > 0); } catch { return null; }
  if (!list.length) return null;
  if (!list.some((s) => s.id === picked.id)) picked.id = "";
  const sel = h("select", { "aria-label": t("src_use"), onChange: () => { picked.id = sel.value; onPick && onPick(sel.value, list.find((s) => s.id === sel.value)); } },
    h("option", { value: "" }, t("src_none")), list.map((s) => h("option", { value: s.id }, s.topic ? `${s.name} — ${s.topic}` : s.name)));
  sel.value = picked.id;
  const el = h("label", { class: "field src-pick" }, h("span", { class: "label" }, t("src_use")), sel);
  return { el, value: () => sel.value, list: () => list };
}
