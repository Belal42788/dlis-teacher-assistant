import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";

// The "AI assistant" panel in Settings: pick a service, follow the steps to get a key, test, save.
export function aiPanel() {
  const box = h("div", { class: "panel" });
  let st = null, cur = null;

  async function load(select) {
    st = await guarded(() => api.get("/api/ai"));
    if (!st) return;
    cur = select || cur || st.provider || "gemini";
    draw();
  }

  function draw() {
    const lang = getLang();
    const p = st.providers.find((x) => x.id === cur) || st.providers[0];
    const key = h("input", { type: "password", autocomplete: "off", spellcheck: "false", dir: "ltr", placeholder: p.has_key ? "••••••••••••" : t("ai_key_ph"), "data-label": t("ai_key"), ...(p.needs_key && !p.has_key ? { required: true } : {}) });
    // Models are asked from the service itself. "Automatic" lets the app pick a working one.
    const model = h("select", { dir: "ltr" }, h("option", { value: "" }, t("ai_auto_model")));
    const fill = (list, chosen) => {
      model.replaceChildren(h("option", { value: "" }, t("ai_auto_model")), list.map((m) => h("option", { value: m }, m)));
      if (chosen && !list.includes(chosen)) model.append(h("option", { value: chosen }, chosen));
      model.value = chosen || "";
    };
    fill([], p.saved_model);
    const modelNote = h("span", { class: "small muted" });
    const loadModels = async (quiet) => {
      try {
        const r = await api.post("/api/ai/models", body());
        fill(r.models, model.value || p.saved_model);
        modelNote.textContent = t("ai_models_n", { n: r.models.length });
      } catch (e) { if (!quiet) throw e; }
    };
    if (p.has_key || !p.needs_key) loadModels(true);
    const base = h("input", { type: "url", dir: "ltr", value: p.saved_base_url || p.base_url, placeholder: "https://.../v1", "data-label": t("ai_base_url"), ...(p.saved_base_url || p.base_url ? {} : { required: true }) });
    const out = h("div", {});
    const body = () => ({ provider: p.id, api_key: key.value.trim(), model: model.value, base_url: base.value.trim() });
    const busy = async (btn, fn) => { btn.disabled = true; try { return await guarded(fn); } finally { btn.disabled = false; } };

    const testBtn = h("button", { class: "btn", "data-check": "", onClick: () => busy(testBtn, async () => {
      out.replaceChildren(h("span", { class: "muted" }, t("ai_testing")));
      try {
        const r = await api.post("/api/ai/test", body());
        if (r.models && r.models.length) { fill(r.models, model.value); modelNote.textContent = t("ai_models_n", { n: r.models.length }); }
        out.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", {}, t("ai_test_ok"), h("div", { class: "small" }, r.auto ? t("ai_auto_using", { m: r.model }) : r.model))));
      } catch (e) { out.replaceChildren(); throw e; }
    }) }, t("ai_test"));
    const modelsBtn = h("button", { class: "btn small", onClick: () => busy(modelsBtn, () => loadModels(false)) }, t("ai_load_models"));
    const saveBtn = h("button", { class: "btn primary", onClick: () => busy(saveBtn, async () => {
      st = await api.post("/api/ai/save", body());
      toast(t("ai_saved")); draw();
    }) }, icon("check"), t("ai_save"));
    const clearBtn = h("button", { class: "btn small", onClick: () => busy(clearBtn, async () => {
      st = await api.post("/api/ai/save", { provider: p.id, api_key: "__clear__" }); draw();
    }) }, t("ai_clear_key"));
    const offBtn = h("button", { class: "btn small", onClick: () => busy(offBtn, async () => { st = await api.post("/api/ai/off"); draw(); }) }, t("ai_off"));
    const openKey = p.key_url ? h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open-url", { url: p.key_url })) }, icon("link"), t("ai_open_key")) : null;

    box.replaceChildren(
      h("h3", {}, t("ai_title")),
      h("p", { class: "muted" }, t("ai_lead")),
      h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, t("ai_privacy"))),
      h("div", { class: "ai-grid" }, st.providers.map((x) => h("button", {
        class: `ai-card${x.id === cur ? " on" : ""}`, "aria-pressed": String(x.id === cur), onClick: () => { cur = x.id; draw(); } },
        h("b", {}, x.name),
        h("span", { class: "small" }, x.free ? t("ai_free") : t("ai_paid"), x.recommended ? ` · ${t("ai_recommended")}` : ""),
        x.id === st.provider && st.ready ? h("span", { class: "ai-badge" }, t("ai_active")) : null))),
      h("div", { class: "ai-detail" },
        h("p", { class: "muted small" }, p.limits[lang] || p.limits.en),
        h("details", { class: "more", open: !p.has_key && p.needs_key }, h("summary", {}, t("ai_how")),
          h("ol", {}, (p.steps[lang] || p.steps.en).map((s) => h("li", {}, s))), openKey),
        p.needs_key ? h("label", { class: "field" }, h("span", { class: "label" }, t("ai_key")), key,
          p.has_key ? h("span", { class: "small muted" }, t("ai_key_saved"), " ", clearBtn) : null) : null,
        p.custom ? h("label", { class: "field" }, h("span", { class: "label" }, t("ai_base_url")), base) : null,
        h("label", { class: "field" }, h("span", { class: "label" }, t("ai_model")), model, modelNote), h("div", {}, modelsBtn),
        h("div", { class: "row" }, testBtn, saveBtn, h("span", { class: "grow" }), st.provider ? offBtn : null),
        out));
  }
  load();
  return box;
}
