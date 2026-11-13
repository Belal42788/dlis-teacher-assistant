import { h, toast } from "../dom.js";
import { api } from "../api.js";
import { t } from "../i18n.js";

const picked = { id: "" };   // the chosen source stays chosen while the teacher moves between pages

// A small "Use my slides" selector. Returns null when there are no sources yet (nothing to choose).
export async function sourcePicker(onPick, opts = {}) {
  let list = [];
  try { list = (await api.get("/api/sources/pick")).sources.filter((s) => s.chars > 0 || s.virtual); } catch { return null; }
  if (!list.length) return null;
  if (!list.some((s) => s.id === picked.id)) picked.id = "";
  // any file of My files can be chosen: it is read now (a big book takes a moment) and from then on it is an ordinary source
  const busy = h("span", { class: "muted small", "aria-live": "polite" });
  async function choose() {
    let s = list.find((x) => x.id === sel.value);
    if (s && s.virtual) {
      sel.disabled = true; busy.textContent = t("src_reading_file");
      try {
        const real = await api.post("/api/sources/use", { id: s.id });
        const at = list.indexOf(s); list[at] = { ...real }; sel.options[sel.selectedIndex].value = real.id; sel.value = real.id; s = list[at];
      } catch (e) { sel.value = ""; picked.id = ""; toast(e.message || String(e), "error"); onPick && onPick("", null); return; }
      finally { sel.disabled = false; busy.textContent = ""; }
    }
    picked.id = sel.value; onPick && onPick(sel.value, s);
  }
  const sel = h("select", { "aria-label": t("src_use"), onChange: choose },
    h("option", { value: "" }, t("src_none")), list.map((s) => h("option", { value: s.id }, s.topic ? `${s.name} — ${s.topic}` : s.name)));
  sel.value = picked.id;
  const pages = h("input", { type: "text", dir: "ltr", placeholder: t("src_pages_ph"), "aria-label": t("src_pages"), style: { maxWidth: "11em" } });
  const verb = h("input", { type: "checkbox" });
  const more = opts.exact ? h("div", { class: "row small", style: { marginTop: ".3rem" } }, h("label", { class: "row" }, t("src_pages"), pages), opts.pagesOnly ? null : h("label", { class: "row" }, verb, t("qt_verbatim"))) : null;
  const el = h("div", { class: "src-pick-box" }, h("label", { class: "field src-pick" }, h("span", { class: "label" }, t("src_use")), sel), busy, more);
  return { el, value: () => sel.value, list: () => list, extra: () => (opts.exact && sel.value ? { source_pages: pages.value.trim(), ...(opts.pagesOnly ? {} : { verbatim: verb.checked }) } : {}) };
}
