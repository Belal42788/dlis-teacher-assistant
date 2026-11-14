import { h, icon, toast, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { sourcePicker } from "../components/source_pick.js";
import { gradeName, triName, fmtShort } from "../labels.js";

// What the teacher typed and the slides being edited stay here while they visit other tabs (nothing is saved to disk until the file is made).
const memo = { model: "", grade: "", tri: "", week: "", topic: "", objectives: "", count: 10, lang: "en", look: "auto", notes: "", prompt: "", source: "", slides: [], built: null };

export async function renderSlides(root, { embedded = false } = {}) {
  const [structure, ov, ai, img] = await Promise.all([api.get("/api/structure"), api.get("/api/overview"), api.get("/api/ai"), api.get("/api/slides/image-config")]);
  const tris = ov.trimesters.filter((x) => x.weeks.length);
  if (!structure.grades.length || !tris.length) {
    root.replaceChildren(h("div", { class: embedded ? "" : "page" }, h("div", { class: "page-head", hidden: embedded || null }, h("div", {}, h("h1", {}, t("nav_slides")))),
      h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_calendar")))));
    return;
  }
  const pos = ov.position;
  const gradeSel = h("select", { onChange: () => { memo.grade = gradeSel.value; if (!typed) memo.objectives = ""; loadTopics(); } }, structure.grades.map((g) => h("option", { value: g.id }, gradeName(g))));
  const triSel = h("select", { onChange: () => { memo.tri = triSel.value; fillWeeks(true); loadTopics(); } }, tris.map((x) => h("option", { value: x.index }, triName(x.name))));
  const weekSel = h("select", { onChange: () => { memo.week = weekSel.value; typed = false; applyTopic(); } });
  if (memo.grade && structure.grades.some((g) => g.id === memo.grade)) gradeSel.value = memo.grade; else memo.grade = gradeSel.value;
  triSel.value = memo.tri !== "" && tris.some((x) => String(x.index) === String(memo.tri)) ? memo.tri : (pos.state === "in_term" ? pos.trimester : tris[0].index);
  memo.tri = triSel.value;
  let topics = [], typed = !!memo.topic;
  const curTri = () => tris.find((x) => x.index === +triSel.value) || tris[0];
  function fillWeeks(reset) {
    weekSel.replaceChildren(h("option", { value: "" }, t("sl_no_week")), curTri().weeks.map((w) => h("option", { value: w.number }, `${t("week_n", { n: w.number })} · ${fmtShort(w.start)} → ${fmtShort(w.end)}`)));
    weekSel.value = !reset && memo.week !== "" ? memo.week : (pos.state === "in_term" && pos.trimester === +triSel.value ? pos.week : "");
    memo.week = weekSel.value;
  }
  const srcSl = await sourcePicker((id, x) => { if (id && x && x.topic && !topic.value.trim()) { topic.value = memo.topic = x.topic; typed = true; } });
  const topic = h("input", { type: "text", required: true, "data-label": t("d_topic"), placeholder: t("sl_topic_ph"), value: memo.topic, onInput: (e) => { memo.topic = e.target.value; typed = true; memo.objectives = ""; } });
  const source = h("div", { class: "muted small" });
  function applyTopic() {
    const w = topics.find((x) => String(x.week) === weekSel.value);
    if (w && w.topic) {
      topic.value = memo.topic = w.topic; memo.objectives = w.objectives || "";
      source.textContent = t(w.source === "lesson" ? "sl_from_lesson" : "sl_from_trimester");
    } else source.textContent = weekSel.value ? t("sl_no_plan") : "";
  }
  async function loadTopics() {
    const r = await guarded(() => api.get(`/api/slides/topics?grade=${gradeSel.value}&tri=${triSel.value}`));
    topics = r ? r.weeks : [];
    if (weekSel.value && !typed) applyTopic();
  }
  const count = h("input", { type: "number", min: 4, max: 30, value: memo.count, style: { width: "5em" }, onInput: (e) => { memo.count = +e.target.value || 10; } });
  const lang = h("select", { onChange: () => { memo.lang = lang.value; } }, h("option", { value: "en" }, "English"), h("option", { value: "ar" }, "العربية"));
  lang.value = memo.lang;
  const look = h("select", { onChange: () => { memo.look = look.value; } }, ["auto", "simple", "colorful", "cartoon", "diagram", "infographic", "pro"].map((k) => h("option", { value: k }, t(`sl_look_${k}`))));
  look.value = memo.look;
  const notes = h("textarea", { rows: 2, placeholder: t("sl_notes_ph"), onInput: (e) => { memo.notes = e.target.value; } }, memo.notes);
  const body = () => ({ grade_id: gradeSel.value, topic: topic.value.trim(), objectives: memo.objectives, slides: +count.value || 10, language: lang.value, look: look.value === "auto" ? "" : look.value, notes: notes.value.trim(), source_id: srcSl ? srcSl.value() : "" });

  const promptBox = h("textarea", { rows: 12, dir: "ltr", placeholder: t("sl_prompt_ph"), onInput: (e) => { memo.prompt = e.target.value; } }, memo.prompt);
  const sourceBox = h("textarea", { rows: 10, placeholder: t("sl_source_ph"), onInput: (e) => { memo.source = e.target.value; } }, memo.source);
  const copy = (el) => { if (!el.value.trim()) return; navigator.clipboard?.writeText(el.value).then(() => toast(t("chat_copied")), () => {}); };
  const busy = async (btn, fn) => { btn.disabled = true; try { return await guarded(fn); } finally { btn.disabled = false; } };
  const promptBtn = h("button", { class: "btn primary", onClick: () => busy(promptBtn, async () => { promptBox.value = memo.prompt = (await api.post("/api/slides/notebooklm", body())).prompt; }) }, icon("file"), t("sl_make_prompt"));
  const sourceBtn = h("button", { class: "btn", disabled: !ai.ready, onClick: () => busy(sourceBtn, async () => { sourceBox.value = memo.source = (await api.post("/api/slides/source", body())).text; toast(t("ai_filled")); }) }, icon("spark"), t("sl_source_btn"));

  // ================= build the slides here
  let imgState = img;
  const provSel = h("select", { "aria-label": t("sl_img_title"), onChange: () => drawImgFields() }, imgState.providers.map((p) => h("option", { value: p.id }, p.label)));
  provSel.value = imgState.provider;
  const cfAcc = h("input", { type: "text", dir: "ltr", autocomplete: "off", value: imgState.account_id, placeholder: "Account ID" });
  const cfTok = h("input", { type: "password", dir: "ltr", autocomplete: "off", placeholder: imgState.has_token ? "••••••••••••" : "API Token" });
  const hfTok = h("input", { type: "password", dir: "ltr", autocomplete: "off", placeholder: imgState.has_hf ? "••••••••••••" : "Hugging Face token (hf_...)" });
  const cfOut = h("span", { class: "muted small" });
  const fields = h("div", {});
  const payload = () => ({ provider: provSel.value, account_id: cfAcc.value.trim(), api_token: cfTok.value.trim(), hf_token: hfTok.value.trim() });
  function drawImgFields() {
    const p = provSel.value;
    fields.replaceChildren(p === "cloudflare" ? h("div", {}, h("ol", { class: "small" }, [1, 2, 3].map((i) => h("li", {}, t(`sl_img_step${i}`)))),
        h("div", { class: "row" }, h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open-url", { url: "https://dash.cloudflare.com/profile/api-tokens" })) }, icon("link"), t("sl_img_open"))),
        h("div", { class: "grid2", style: { marginTop: ".6rem" } }, h("label", { class: "field" }, h("span", { class: "label" }, "Account ID"), cfAcc), h("label", { class: "field" }, h("span", { class: "label" }, "API Token"), cfTok)))
      : p === "huggingface" ? h("div", {}, h("p", { class: "small muted" }, t("sl_img_hf")), h("label", { class: "field" }, h("span", { class: "label" }, "Token"), hfTok))
      : p === "gemini" ? h("p", { class: "small muted" }, t(imgState.ready.gemini ? "sl_img_gemini_ok" : "sl_img_gemini_no"))
      : p === "wikimedia" ? h("p", { class: "small muted" }, t("sl_img_wiki")) : h("p", { class: "small muted" }, t("sl_img_poll")));
  }
  drawImgFields();
  const cfSave = h("button", { class: "btn", onClick: () => busy(cfSave, async () => { imgState = await api.put("/api/slides/image-config", payload()); cfTok.value = ""; hfTok.value = ""; toast(t("saved")); drawDeck(); }) }, icon("check"), t("sl_img_save"));
  const cfTest = h("button", { class: "btn", onClick: () => busy(cfTest, async () => { cfOut.textContent = t("ai_testing"); try { await api.post("/api/slides/image-test", payload()); imgState = await api.get("/api/slides/image-config"); cfOut.textContent = "✓ " + t("sl_img_ok"); drawDeck(); } catch (e) { cfOut.textContent = ""; throw e; } }) }, icon("spark"), t("sl_img_test"));
  const imgSetup = h("details", { class: "more" }, h("summary", {}, t("sl_img_title")),
    h("p", { class: "muted small" }, t("sl_img_lead2")), h("label", { class: "field" }, h("span", { class: "label" }, t("sl_img_service")), provSel), fields,
    h("div", { class: "row" }, cfSave, cfTest, cfOut));

  const deckBox = h("div", {});
  const modelLine = h("p", { class: "muted small dir-ltr", style: { margin: ".3rem 0" } });
  const result = h("div", {});
  const planBtn = h("button", { class: "btn primary", disabled: !ai.ready, onClick: () => busy(planBtn, async () => {
    if (memo.slides.length && !(await confirmBox(t("sl_replace_confirm"), { okLabel: t("ok"), danger: false }))) return;
    const r = await api.post("/api/slides/plan", { ...body(), slides: Math.max(4, (+count.value || 10) - 1) });
    memo.slides = r.slides.map((s) => ({ ...s, image_id: "", data_url: "" })); memo.built = null; memo.model = r.model || ""; drawDeck(); toast(t("ai_filled"));
  }) }, icon("spark"), t("sl_plan"));
  const makeAllBtn = h("button", { class: "btn", onClick: () => makeAll() }, icon("file"), t("sl_all_pics"));
  const addBtn = h("button", { class: "btn", onClick: () => { memo.slides.push({ title: "", bullets: [], explain: "", notes: "", image_prompt: "", image_id: "", data_url: "" }); drawDeck(); } }, icon("plus"), t("sl_add"));
  const buildBtn = h("button", { class: "btn primary", onClick: () => busy(buildBtn, async () => {
    memo.built = await api.post("/api/slides/build", { grade_id: gradeSel.value, title: topic.value.trim(), language: lang.value, trimester: +triSel.value, week: weekSel.value ? +weekSel.value : 0,
      slides: memo.slides.map((s) => ({ title: s.title, bullets: s.bullets, explain: s.explain || "", notes: s.notes, image_id: s.image_id })) });
    drawDeck();
  }) }, icon("file"), t("sl_build"));

  async function makePic(s, btn) {
    if (!s.image_prompt.trim()) { toast(t("sl_need_img_prompt"), "error"); return; }
    btn.disabled = true;
    try {
      const r = await api.post("/api/slides/image", { prompt: s.image_prompt, grade_id: gradeSel.value, look: look.value === "auto" ? "" : look.value });
      s.image_id = r.id; s.data_url = r.data_url; drawDeck();
    } catch (e) { toast(e.friendly || e.message, "error"); } finally { btn.disabled = false; }
  }
  async function makeAll() {
    makeAllBtn.disabled = true;
    try {
      for (const s of memo.slides) {
        if (s.image_id || !s.image_prompt.trim()) continue;
        const r = await api.post("/api/slides/image", { prompt: s.image_prompt, grade_id: gradeSel.value, look: look.value === "auto" ? "" : look.value });
        s.image_id = r.id; s.data_url = r.data_url; drawDeck();
      }
    } catch (e) { toast(e.friendly || e.message, "error"); } finally { makeAllBtn.disabled = false; }
  }
  const move = (i, d) => { const j = i + d; if (j < 0 || j >= memo.slides.length) return; [memo.slides[i], memo.slides[j]] = [memo.slides[j], memo.slides[i]]; drawDeck(); };

  function drawDeck() {
    const ready = imgState.configured;
    makeAllBtn.style.display = ready && memo.slides.length ? "" : "none";
    buildBtn.style.display = memo.slides.length ? "" : "none";
    modelLine.textContent = memo.model && memo.slides.length ? t("sl_model", { model: memo.model }) : "";
    deckBox.replaceChildren(...memo.slides.map((s, i) => {
      const picBtn = h("button", { class: "btn small", disabled: !ready, title: ready ? "" : t("sl_img_first"), onClick: () => makePic(s, picBtn) }, icon("spark"), s.image_id ? t("sl_pic_again") : t("sl_pic_make"));
      return h("div", { class: "slide-card" },
        h("div", { class: "slide-no" }, i + 2),
        h("div", { class: "slide-body" },
          h("input", { type: "text", value: s.title, placeholder: t("sl_s_title"), "aria-label": t("sl_s_title"), onInput: (e) => { s.title = e.target.value; } }),
          h("textarea", { rows: 3, placeholder: t("sl_s_bullets"), "aria-label": t("sl_s_bullets"), onInput: (e) => { s.bullets = e.target.value.split("\n").map((x) => x.trim()).filter(Boolean); } }, s.bullets.join("\n")),
          h("textarea", { rows: 3, placeholder: t("sl_s_explain"), "aria-label": t("sl_s_explain"), onInput: (e) => { s.explain = e.target.value; } }, s.explain || ""),
          h("details", { class: "more" }, h("summary", {}, t("sl_s_more")),
            h("label", { class: "field" }, h("span", { class: "label" }, t("sl_s_notes")), h("textarea", { rows: 2, onInput: (e) => { s.notes = e.target.value; } }, s.notes)),
            h("label", { class: "field" }, h("span", { class: "label" }, t("sl_s_imgprompt")), h("input", { type: "text", dir: "ltr", value: s.image_prompt, onInput: (e) => { s.image_prompt = e.target.value; } }))),
          h("div", { class: "row small" }, picBtn,
            s.image_id ? h("button", { class: "btn small ghost", onClick: () => { s.image_id = ""; s.data_url = ""; drawDeck(); } }, t("sl_pic_remove")) : null,
            h("span", { class: "grow" }),
            h("button", { class: "btn icon ghost", "aria-label": "up", onClick: () => move(i, -1) }, "↑"), h("button", { class: "btn icon ghost", "aria-label": "down", onClick: () => move(i, 1) }, "↓"),
            h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { memo.slides.splice(i, 1); drawDeck(); } }, icon("trash")))),
        s.data_url ? h("img", { class: "slide-pic", src: s.data_url, alt: "" }) : h("div", { class: "slide-pic empty" }, icon("file")));
    }));
    result.replaceChildren(memo.built ? h("div", { class: "banner ok" }, icon("check"),
      h("div", { class: "grow" }, h("b", {}, t("sl_built", { n: memo.built.slides })), h("div", { class: "dir-ltr small" }, memo.built.rel), h("div", { class: "muted small" }, t("sl_built_note"))),
      h("div", { class: "row" },
        h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open", { path: memo.built.path, folder: false })) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: memo.built.path, folder: true })) }, icon("folder"), t("d_open_folder")))) : null);
  }

  fillWeeks(false);
  root.replaceChildren(h("div", { class: embedded ? "" : "page", "data-form": "" },
    h("div", { class: "page-head", hidden: embedded || null }, h("div", {}, h("h1", {}, t("nav_slides")), h("p", {}, t("sl_lead")))),
    h("div", { class: "panel" }, h("h3", {}, t("sl_step1")),
      h("div", { class: "pick-row" },
        h("label", {}, h("span", { class: "label" }, t("d_class")), gradeSel),
        h("label", {}, h("span", { class: "label" }, t("d_trimester")), triSel),
        h("label", {}, h("span", { class: "label" }, t("d_week")), weekSel)),
      srcSl ? srcSl.el : null, h("label", { class: "field" }, h("span", { class: "label" }, t("d_topic")), topic), source,
      h("div", { class: "opt-row", style: { marginTop: ".8rem" } },
        h("label", {}, h("span", { class: "label" }, t("sl_count")), count), h("label", {}, h("span", { class: "label" }, t("sl_language")), lang),
        h("label", {}, h("span", { class: "label" }, t("sl_look")), look)),
      h("label", { class: "field" }, h("span", { class: "label" }, t("sl_notes")), notes)),
    h("div", { class: "panel" }, h("h3", {}, t("sl_build_title")), h("p", { class: "muted small" }, t("sl_build_lead")), imgSetup,
      h("div", { class: "row", style: { margin: ".8rem 0" } }, planBtn, addBtn, makeAllBtn, buildBtn), result, modelLine, deckBox),
    h("details", { class: "panel fold" }, h("summary", {}, h("h3", {}, t("sl_nlm_title"))), h("p", { class: "muted small" }, t("sl_nlm_lead")),
      h("div", { class: "row" }, promptBtn,
        h("button", { class: "btn", onClick: () => copy(promptBox) }, icon("copy"), t("chat_copy")),
        h("button", { class: "btn", onClick: () => guarded(() => api.post("/api/open-url", { url: "https://notebooklm.google.com/" })) }, icon("link"), t("sl_open_nlm"))),
      promptBox,
      h("h4", { style: { marginTop: "1rem" } }, t("sl_source_title")), h("p", { class: "muted small" }, t("sl_source_lead")),
      h("div", { class: "row" }, sourceBtn, h("button", { class: "btn", onClick: () => copy(sourceBox) }, icon("copy"), t("chat_copy"))),
      sourceBox,
      h("details", { class: "more" }, h("summary", {}, t("sl_how")), h("ol", {}, [1, 2, 3, 4, 5].map((i) => h("li", {}, t(`sl_how_${i}`))))))));
  drawDeck();
  await loadTopics();
}
