import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

const PROMPT_KEYS = ["lesson", "quiz", "trimester", "slides", "revision", "chat"];

// Edit the wording the AI helpers use (kept per teacher, can be reset to the default at any time).
export async function promptEditor() {
  let prompts = await api.get("/api/ai/prompts");
  const pSel = h("select", { onChange: () => drawPrompt() }, PROMPT_KEYS.map((k) => h("option", { value: k }, t(`chat_p_${k}`))));
  const pSystem = h("textarea", { rows: 5 }), pGuide = h("textarea", { rows: 3 });
  const pGuideLabel = h("label", { class: "field" }, h("span", { class: "label" }, t("chat_p_guidance")), pGuide);
  const pFixed = h("div", { class: "fixed-parts" });
  const pNote = h("span", { class: "muted small" });
  function drawPrompt() {
    const k = pSel.value, def = prompts.defaults[k], mine = prompts.custom[k];
    pSystem.value = (mine?.system ?? def.system) || "";
    pGuide.value = (mine && "guidance" in mine ? mine.guidance : def.guidance) || "";
    pGuideLabel.style.display = k === "chat" ? "none" : "";
    pFixed.replaceChildren(h("b", {}, t("chat_p_fixed")), h("ul", {}, (prompts.fixed?.[k] || []).map((x) => h("li", {}, x))));
    pNote.textContent = mine ? t("chat_p_custom") : t("chat_p_default");
  }
  const savePrompt = h("button", { class: "btn primary", onClick: async () => {
    const r = await guarded(() => api.put("/api/ai/prompts", { key: pSel.value, system: pSystem.value, guidance: pGuide.value }));
    if (r) { prompts = r; drawPrompt(); toast(t("saved")); }
  } }, icon("check"), t("chat_p_save"));
  const resetPrompt = h("button", { class: "btn", onClick: async () => {
    const r = await guarded(() => api.put("/api/ai/prompts", { key: pSel.value, reset: true }));
    if (r) { prompts = r; drawPrompt(); toast(t("chat_p_reset_done")); }
  } }, t("chat_p_reset"));
  const editor = h("div", { class: "panel" }, h("h3", {}, t("chat_p_title")),
    h("p", { class: "muted small" }, t("chat_p_lead")),
    h("label", { class: "field" }, h("span", { class: "label" }, t("chat_p_which")), pSel),
    h("label", { class: "field" }, h("span", { class: "label" }, t("chat_p_role")), pSystem), pGuideLabel,
    h("details", { class: "more" }, h("summary", {}, t("chat_p_fixed_h")), pFixed),
    h("div", { class: "row" }, savePrompt, resetPrompt, pNote));
  drawPrompt();

  return editor;
}
