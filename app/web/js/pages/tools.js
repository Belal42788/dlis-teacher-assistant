import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { sourcePicker } from "../components/source_pick.js";
import { gradeName, roomLabel } from "../labels.js";

const memo = { tool: "", values: {}, text: "", grade: "" };   // what was typed stays while the teacher visits other pages

// Extra AI tools: pick one, fill its small form, get a ready text, copy it or save it as a Word file.
export async function renderTools(root) {
  const [cat, structure, ai] = await Promise.all([api.get("/api/tools"), api.get("/api/structure"), guarded(() => api.get("/api/ai")).then((x) => x || { ready: false })]);
  const lang = getLang(), L = (o) => (o && (o[lang] || o.en)) || "";
  const tools = cat.tools;
  const asked = new URLSearchParams((location.hash.split("?")[1]) || "").get("tool");
  if (asked && tools.some((x) => x.id === asked)) memo.tool = asked;
  const pick = h("select", { "aria-label": t("tl_pick"), onChange: () => { saveValues(); memo.tool = pick.value; drawForm(); } },
    cat.groups.map((g) => h("optgroup", { label: L(g.name) }, tools.filter((x) => x.group === g.id).map((x) => h("option", { value: x.id }, L(x.name))))));
  pick.value = tools.some((x) => x.id === memo.tool) ? memo.tool : tools[0].id; memo.tool = pick.value;
  const grade = h("select", { "aria-label": t("d_class"), onChange: () => { memo.grade = grade.value; } }, h("option", { value: "" }, "—"), structure.grades.map((g) => h("option", { value: g.id }, gradeName(g))));
  grade.value = memo.grade;
  const outLang = h("select", { "aria-label": t("tl_lang") }, [["en", "English"], ["ar", "العربية"], ["both", t("tl_both")]].map(([v, l]) => h("option", { value: v }, l)));
  outLang.value = lang === "ar" ? "ar" : "en";
  const src = await sourcePicker(null, { exact: true, pagesOnly: true });
  const cite = h("input", { type: "checkbox" });
  const citeRow = src ? h("label", { class: "row small" }, cite, t("tl_cite")) : null;
  const desc = h("p", { class: "muted" });
  const form = h("div", { class: "tl-form" });
  const result = h("textarea", { rows: 16, class: "tl-out", placeholder: t("tl_result_ph") });
  result.value = memo.text;
  result.addEventListener("input", () => { memo.text = result.value; });
  const fileBox = h("div", {});
  const stuBox = h("div", { class: "row", style: { marginTop: ".5rem" } });
  let inputs = {};
  const cur = () => tools.find((x) => x.id === pick.value);
  const saveValues = () => { memo.values[memo.tool] = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value])); };

  function drawForm() {
    const tool = cur();
    desc.textContent = L(tool.desc);
    inputs = {};
    const saved = memo.values[tool.id] || {};
    const fields = tool.fields.map((f) => {
      let el;
      if (f.type === "textarea") el = h("textarea", { rows: f.rows || 4, placeholder: f.placeholder || "" });
      else if (f.type === "select") el = h("select", {}, f.options.map((o) => h("option", { value: o }, o)));
      else el = h("input", { type: f.type === "number" ? "number" : "text", placeholder: f.placeholder || "", min: f.type === "number" ? 1 : null });
      el.value = saved[f.key] !== undefined ? saved[f.key] : (f.default || "");
      if (f.required) { el.required = true; el.setAttribute("data-label", L(f.label)); }
      inputs[f.key] = el;
      return h("label", { class: "field" }, h("span", { class: "label" }, L(f.label), f.required ? " *" : ""), el);
    });
    form.replaceChildren(...fields);
    drawStudent(tool);
  }

  // report-card comments and feedback: the AI writes [student]; the name is put in here, on this computer
  let stu = { names: [], english: [], auto: [] };
  const stuRoom = h("select", { "aria-label": t("ch_class"), onChange: () => loadStudents() }, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const stuName = h("select", { "aria-label": t("students") });
  async function loadStudents() {
    if (!stuRoom.value) return;
    stu = await guarded(() => api.get(`/api/rooms/${stuRoom.value}/students`)) || stu;
    stuName.replaceChildren(h("option", { value: "" }, "—"), ...stu.names.map((n, i) => h("option", { value: i }, n)));
  }
  function drawStudent(tool) {
    if (!tool.student || !structure.rooms.length) { stuBox.replaceChildren(); return; }
    stuBox.replaceChildren(h("span", { class: "muted small" }, t("tl_name_hint")), stuRoom, stuName,
      h("button", { class: "btn", onClick: () => {
        const i = +stuName.value; if (isNaN(i) || !stu.names[i]) { toast(t("pm_pick_student"), "error"); return; }
        const name = /[؀-ۿ]/.test(result.value) ? stu.names[i] : (stu.english[i] || stu.auto[i] || stu.names[i]);
        navigator.clipboard?.writeText(result.value.replace(/\[student\]/gi, name)).then(() => toast(t("pm_copied")), () => {});
      } }, icon("copy"), t("pm_name_copy")));
    loadStudents();
  }

  const writeBtn = h("button", { class: "btn primary", disabled: !ai.ready, onClick: () => {
    saveValues(); writeBtn.disabled = true;
    const old = writeBtn.lastChild.textContent; writeBtn.lastChild.textContent = t("ai_writing");
    guarded(async () => {
      const values = memo.values[memo.tool] || {};
      const r = await api.post("/api/tools/run", { tool: memo.tool, values, grade_id: grade.value, language: outLang.value, ...(src ? { source_id: src.value(), cite: cite.checked, ...src.extra() } : {}) });
      memo.text = result.value = r.text; fileBox.replaceChildren();
    }).finally(() => { writeBtn.disabled = !ai.ready; writeBtn.lastChild.textContent = old; });
  } }, icon("spark"), t("tl_write"));
  const copyBtn = h("button", { class: "btn", onClick: () => { navigator.clipboard?.writeText(result.value).then(() => toast(t("pm_copied")), () => {}); } }, icon("copy"), t("chat_copy"));
  const wordBtn = h("button", { class: "btn", onClick: () => guarded(async () => {
    if (!result.value.trim()) { toast(t("tl_nothing"), "error"); return; }
    const r = await api.post("/api/tools/word", { tool: memo.tool, text: result.value, grade_id: grade.value });
    fileBox.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel)),
      h("div", { class: "row" }, h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: false })) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: true })) }, icon("folder"), t("d_open_folder")),
        cur().student ? null : h("a", { class: "btn small", href: `#/library?share=${encodeURIComponent(r.rel.replace(/\\/g, "/"))}` }, icon("send"), t("lb_share")))));
  }) }, icon("file"), t("tl_word"));

  root.replaceChildren(h("div", { class: "page" }, h("a", { class: "btn small", href: "#/docs", "data-back-hub": "" }, icon("back"), " ", t("cr_back")),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_tools")), h("p", {}, t("tl_lead")))),
    ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, h("a", { href: "#/settings" }, t("ai_setup_link")))),
    h("div", { class: "panel" },
      h("label", { class: "field" }, h("span", { class: "label" }, t("tl_pick")), pick), desc,
      h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("d_class")), grade), h("label", { class: "field" }, h("span", { class: "label" }, t("tl_lang")), outLang)),
      src ? src.el : null, citeRow, form,
      h("div", { class: "row", style: { marginTop: ".6rem" } }, writeBtn)),
    h("div", { class: "panel" }, h("h3", {}, t("tl_result")), result,
      h("div", { class: "row", style: { marginTop: ".6rem" } }, copyBtn, wordBtn), stuBox, fileBox, h("p", { class: "muted small" }, t("tl_check")))));
  drawForm();
}
