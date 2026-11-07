// "What is new": a short list shown once after the app was updated (and again from Settings, on request).
import { h, icon, modal } from "../dom.js";
import { api } from "../api.js";
import { t, getLang } from "../i18n.js";

export function showWhatsNew(entries, { remember = true } = {}) {
  const lang = getLang() === "ar" ? "ar" : "en";
  const rows = (entries || []).filter((e) => (e[lang] || []).length);
  if (!rows.length) return null;
  const done = () => { if (remember) api.post("/api/whats-new/seen", {}).catch(() => {}); };
  return modal({
    title: t("wn_title"),
    onClose: done,
    body: h("div", { class: "whatsnew" }, rows.map((e, i) => h("section", {},
      rows.length > 1 || i === 0 ? h("h4", {}, t("wn_version", { v: e.version })) : null,
      h("ul", {}, e[lang].map((line) => h("li", {}, icon("check"), h("span", {}, line))))))),
    actions: [{ label: t("wn_ok"), kind: "primary" }],
  });
}

export async function openWhatsNew() {
  const r = await api.get("/api/whats-new?all=1");
  return showWhatsNew(r.entries, { remember: false });
}
