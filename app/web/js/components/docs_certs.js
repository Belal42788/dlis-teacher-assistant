import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { t, getLang } from "../i18n.js";

// Certificates and thank-you cards. Names go only into the Word file, never to the AI.
export function certsPanel(ctx) {
  const { sel, run, showResult } = ctx;
  const ctOcc = h("select", {}, ["excellence", "improvement", "behavior", "participation", "attendance", "thanks", "custom"].map((k) => h("option", { value: k }, t(`ct_o_${k}`))));
  const ctKind = h("select", {}, h("option", { value: "certificate" }, t("ct_k_cert")), h("option", { value: "card" }, t("ct_k_card")));
  const ctLang = h("select", {}, h("option", { value: "ar" }, "العربية"), h("option", { value: "en" }, "English"));
  ctLang.value = getLang();
  const ctTitle = h("input", { type: "text", placeholder: t("ct_title_ph") });
  const ctText = h("input", { type: "text", placeholder: t("ct_text_ph"), style: { minWidth: "18rem" } });
  const ctCustom = h("div", { class: "row", hidden: true }, ctTitle, ctText);
  ctOcc.addEventListener("change", () => { ctCustom.hidden = ctOcc.value !== "custom"; });
  const ctNames = h("div", { class: "gs-absent", hidden: true, "data-nodraft": "1" });
  const ctAll = h("input", { type: "checkbox", checked: true });
  ctAll.addEventListener("change", () => { ctNames.hidden = ctAll.checked; });
  const ctExtra = h("textarea", { rows: 3, placeholder: t("ct_extra_ph") });
  const ctBtn = h("button", { class: "btn primary", onClick: () => run(ctBtn, async () => {
    const picked = [...ctNames.querySelectorAll("input:checked")].map((x) => x.value);
    const classPart = ctAll.checked ? { room_id: sel.room } : picked.length ? { room_id: sel.room, students: picked } : { room_id: "" };
    const r = await api.post("/api/docs/certificates", { ...classPart, occasion: ctOcc.value, kind: ctKind.value, lang: ctLang.value,
      title: ctTitle.value.trim(), text: ctText.value.trim(), extra_names: ctExtra.value, date: new Date().toISOString().slice(0, 10) });
    showResult(r, h("div", { class: "small" }, t("ct_count", { n: r.count })));
  }) }, icon("file"), t("ct_create"));
  const panel = h("div", { class: "panel" }, h("h3", {}, t("ct_title")), h("p", { class: "muted small" }, t("ct_lead")),
    h("div", { class: "row" }, h("label", { class: "field" }, h("span", { class: "label" }, t("ct_occasion")), ctOcc),
      h("label", { class: "field" }, h("span", { class: "label" }, t("ct_kind")), ctKind), h("label", { class: "field" }, h("span", { class: "label" }, t("ct_lang")), ctLang)),
    ctCustom,
    h("label", { class: "row", style: { marginTop: ".5rem" } }, ctAll, h("b", {}, t("ct_all"))), ctNames,
    h("label", { class: "field", style: { marginTop: ".5rem" } }, h("span", { class: "label" }, t("ct_extra")), ctExtra),
    h("div", { class: "row", style: { marginTop: ".6rem" } }, h("span", { class: "grow" }), ctBtn));
  const setNames = (names) => ctNames.replaceChildren(...names.map((n) => h("label", { class: "row small" }, h("input", { type: "checkbox", value: n }), n)));
  return { el: panel, setNames };
}
