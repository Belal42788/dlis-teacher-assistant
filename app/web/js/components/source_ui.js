import { h, icon, toast, confirmBox, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

// Everything about a source for the AI that lives inside «My files»: adding a book or a web page, reading its pictures, sorting its content.
// The page gives `reload` (draws the list again) and gets back the small pieces it puts in each row.
export function sourceTools({ ai, reload }) {
  const status = h("div", { class: "muted small", "aria-live": "polite" });
  let working = false;

  // read the picture pages (a few at a time), then let the AI sort what it found
  async function process(id) {
    working = true;
    try {
      let b = await api.get(`/api/sources/${id}`);
      const total = b.pending;
      while (b.pending > 0) {
        status.textContent = t("src_reading", { done: total - b.pending, total });
        b = await api.post(`/api/sources/${id}/read`, {});
      }
      if (b.chars > 0 && !b.has_digest && ai.ready) {
        status.textContent = t("src_digesting");
        await api.post(`/api/sources/${id}/digest`, {});
      }
      status.textContent = ""; toast(t("src_ready"));
    } catch (e) { status.textContent = ""; throw e; } finally { working = false; await reload(); }
  }
  const run = (fn) => { if (working) return; return guarded(fn); };

  // the buttons of a source: read its pictures, sort its content
  const buttons = (s) => [
    s.pending ? h("button", { class: "btn small primary", onClick: () => run(() => process(s.id)) }, icon("spark"), t("src_read_pics", { n: s.pending })) : null,
    s.chars && !s.has_digest && !s.pending ? h("button", { class: "btn small", disabled: !ai.ready, onClick: () => run(() => process(s.id)) }, icon("spark"), t("src_analyze")) : null,
  ];

  // what the app found inside it (opens on demand)
  function details(s) {
    const detail = h("div", {});
    const open = h("details", { class: "more", onToggle: async () => {
      if (!open.open || detail.childNodes.length) return;
      const r = await guarded(() => api.get(`/api/sources/${s.id}`)); if (!r) return;
      const d = r.digest || {};
      detail.replaceChildren(
        d.topic ? h("div", {}, h("b", {}, t("src_topic")), " ", d.topic) : null,
        d.objectives?.length ? h("div", {}, h("b", {}, t("d_objectives")), h("ul", {}, d.objectives.map((x) => h("li", {}, x)))) : null,
        d.words?.length ? h("div", {}, h("b", {}, t("rv_words").split(" (")[0]), h("ul", {}, d.words.map((x) => h("li", {}, `${x.term}: ${x.meaning}`)))) : null,
        d.questions?.length ? h("div", {}, h("b", {}, t("src_questions")), h("ul", {}, d.questions.map((x) => h("li", {}, `${x.q} → ${x.a}`)))) : null,
        h("details", { class: "more" }, h("summary", {}, t("src_text")), h("pre", { class: "pre small", style: { maxHeight: "16rem", overflow: "auto" } }, r.text || "—")));
    } }, h("summary", {}, t("src_details")), detail);
    return open;
  }

  const removeButton = (s) => h("button", { class: "btn small ghost", "aria-label": t("remove"), onClick: async () => { if (await confirmBox(t("src_delete_confirm"))) await guarded(async () => { await api.post(`/api/sources/${s.id}/delete`, {}); await reload(); }); } }, icon("trash"));

  // the panel to add a book / file / web page
  const file = h("input", { type: "file", accept: ".pdf,.pptx,.docx,.txt,.md", hidden: true, onChange: async () => {
    const f = file.files[0]; file.value = ""; if (!f || working) return;
    const r = await guarded(async () => {
      status.textContent = t("src_importing");
      const out = await api.post("/api/sources/import", { filename: f.name, data_b64: await readFileB64(f) });
      await reload(); return out;
    });
    if (!r) { status.textContent = ""; return; }
    await guarded(() => process(r.id));
  } });
  const adder = (extra) => h("details", { class: "panel add-src" },
    h("summary", {}, icon("upload"), h("b", {}, t("src_add_title"))),
    h("p", { class: "muted small" }, t("src_add_lead")),
    h("div", { class: "row" }, h("button", { class: "btn primary", onClick: () => file.click() }, icon("upload"), t("src_choose")), file),
    extra || null);

  return { status, adder, buttons, details, removeButton, run, process };
}
