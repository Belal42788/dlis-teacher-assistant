import { h, icon, toast, modal, confirmBox, debounce, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { t, getLang } from "../i18n.js";
import { state } from "../state.js";
import { roomLabel, gradeName, stageName, subjectLabel, stageTone } from "../labels.js";
import { classPicker } from "../components/class_picker.js";

let selectedId = "";

export async function renderClasses(root) {
  let structure = await api.get("/api/structure");
  state.structure = structure;
  const settings = await api.get("/api/settings");
  if (!structure.rooms.some((r) => r.id === selectedId)) selectedId = structure.rooms[0]?.id || "";

  const treeBox = h("div", { class: "tree panel" });
  const detail = h("div", {});

  async function reload(keep = true) {
    structure = await api.get("/api/structure");
    state.structure = structure;
    if (!keep || !structure.rooms.some((r) => r.id === selectedId)) selectedId = structure.rooms[0]?.id || "";
    drawTree(); await drawDetail();
  }

  function drawTree() {
    treeBox.replaceChildren();
    if (!structure.rooms.length) { treeBox.append(h("p", { class: "muted" }, t("no_classes_yet"))); return; }
    for (const stage of structure.stages) {
      const grades = structure.grades.filter((g) => g.stage_id === stage.id && structure.rooms.some((r) => r.grade_id === g.id));
      if (!grades.length) continue;
      treeBox.append(h("div", { class: "stage" }, stageName(stage)));
      for (const g of grades) for (const r of structure.rooms.filter((x) => x.grade_id === g.id)) {
        treeBox.append(h("button", { class: "room", "aria-current": String(r.id === selectedId), onClick: () => { selectedId = r.id; drawTree(); drawDetail(); } },
          h("span", { class: "dot", style: { background: stageTone(r.grade_id) } }), h("span", { class: "grow" }, roomLabel(r, structure)), h("span", { class: "count", title: t("students") }, r.student_count)));
      }
    }
  }

  async function drawDetail() {
    const room = structure.rooms.find((r) => r.id === selectedId);
    if (!room) {
      detail.replaceChildren(h("div", { class: "panel" }, h("h3", {}, t("no_classes_yet")), h("p", { class: "muted" }, t("add_classes_hint")),
        h("button", { class: "btn primary", onClick: addClasses }, icon("plus"), t("add_classes"))));
      return;
    }
    const grade = structure.grades.find((g) => g.id === room.grade_id);
    const data = await api.get(`/api/rooms/${room.id}/students`);
    detail.replaceChildren(studentsPanel(room, grade, data), optionsPanel(room), gradePanel(grade));
  }

  // ---------------- students
  function studentsPanel(room, grade, data) {
    let names = [...data.names], english = [...data.english], auto = [...data.auto];
    const status = h("span", { class: "saved" });
    const list = h("ul", { class: "students" });
    const countEl = h("span", { class: "count" }, names.length);
    const save = debounce(async () => {
      status.textContent = t("saving");
      const r = await guarded(() => api.put(`/api/rooms/${room.id}/students`, { names, english }));
      if (r) { auto = r.auto; status.textContent = "✓ " + t("saved"); const info = structure.rooms.find((x) => x.id === room.id); info.student_count = r.names.length; drawTree(); }
    }, 700);
    const touch = () => { countEl.textContent = names.filter((n) => n.trim()).length; save(); };

    // two spellings per student: Arabic and English. The one in the app's language comes first.
    function drawList() {
      const ar = getLang() === "ar";
      const arBox = (i) => h("input", { type: "text", dir: "rtl", value: names[i], placeholder: t("student_ar"), "aria-label": t("student_n", { n: i + 1 }),
        onInput: (e) => { names[i] = e.target.value; touch(); } });
      const enBox = (i) => h("input", { type: "text", dir: "ltr", value: english[i] || "", placeholder: auto[i] || t("student_en"), "aria-label": t("student_en"),
        onInput: (e) => { english[i] = e.target.value; touch(); } });
      list.replaceChildren(...names.map((n, i) => h("li", {},
        ...(ar ? [arBox(i), enBox(i)] : [enBox(i), arBox(i)]),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: () => { names.splice(i, 1); english.splice(i, 1); auto.splice(i, 1); drawList(); touch(); } }, icon("trash")))));
    }
    drawList();
    const add = h("input", { type: "text", placeholder: t("add_student_ph"), "aria-label": t("add_student_ph"), class: "grow",
      onKeydown: (e) => { if (e.key === "Enter") addOne(); } });
    function addOne() {
      const v = add.value.trim();
      if (!v) return;
      names.push(v); english.push(""); auto.push(""); add.value = ""; drawList(); touch(); add.focus();
      list.lastElementChild?.scrollIntoView({ block: "nearest" });
    }

    return h("div", { class: "panel" },
      h("div", { class: "row between", style: { marginBottom: ".9rem" } },
        h("div", {}, h("h2", {}, roomLabel(room, structure)), h("div", { class: "muted" }, gradeName(grade), " · ", countEl, " ", t("students"))),
        h("div", { class: "row" }, status, h("button", { class: "btn", onClick: () => importDialog(room, names, (merged) => { const keep = new Map(names.map((n, i) => [n, english[i]])); names = merged; english = merged.map((n) => keep.get(n) || ""); auto = merged.map(() => ""); drawList(); touch(); }) }, icon("upload"), t("paste_or_import")))),
      names.length ? null : h("div", { class: "banner info" }, icon("info"), h("div", {}, t("no_students_yet"))),
      list,
      h("div", { class: "row", style: { marginTop: ".8rem" } }, add, h("button", { class: "btn", onClick: addOne }, icon("plus"), t("add"))));
  }

  function importDialog(room, current, apply) {
    let parsed = { names: [], duplicates: [] };
    const ta = h("textarea", { placeholder: t("paste_here"), "aria-label": t("paste_here") });
    const info = h("div", { class: "muted", style: { margin: ".8rem 0" } }, t("import_waiting"));
    const replace = h("input", { type: "checkbox", style: { width: "20px", height: "20px" } });
    const show = (p) => {
      parsed = p;
      info.replaceChildren(p.names.length
        ? h("div", { class: "banner ok" }, icon("check"), h("div", {}, h("b", {}, t("found_students", { n: p.names.length })),
          p.duplicates.length ? h("div", { class: "small" }, t("duplicates_skipped", { n: p.duplicates.length })) : null,
          h("div", { class: "small muted" }, p.names.slice(0, 5).join(" · ") + (p.names.length > 5 ? " …" : ""))))
        : h("div", { class: "muted" }, t("import_nothing")));
    };
    const parseText = debounce(async () => { const r = await guarded(() => api.post("/api/students/parse", { text: ta.value })); r && show(r); }, 350);
    ta.addEventListener("input", parseText);
    const file = h("input", { type: "file", accept: ".xlsx,.csv,.txt", "aria-label": t("choose_file"),
      onChange: async (e) => {
        const f = e.target.files[0]; if (!f) return;
        const r = await guarded(async () => api.post("/api/students/parse", { filename: f.name, data_b64: await readFileB64(f) }));
        if (r) { ta.value = r.names.join("\n"); show(r); }
      } });
    modal({
      title: t("paste_or_import"), wide: true,
      body: h("div", {}, h("p", {}, t("import_help")), ta,
        h("div", { class: "row", style: { marginTop: ".8rem" } }, h("b", {}, t("or_choose_file")), file), info,
        current.length ? h("label", { class: "row" }, replace, t("replace_current", { n: current.length })) : null),
      actions: [{ label: t("cancel") }, { label: t("add_to_class"), kind: "primary", onClick: () => {
        if (!parsed.names.length) return false;
        const base = replace.checked ? [] : current.filter((x) => x.trim());
        const have = new Set(base.map((x) => x.toLowerCase()));
        apply([...base, ...parsed.names.filter((n) => !have.has(n.toLowerCase()))]);
      } }],
    });
  }

  // ---------------- class options
  function optionsPanel(room) {
    const name = h("input", { type: "text", value: room.name });
    const subj = h("select", {}, h("option", { value: "" }, t("same_as_mine")),
      state.boot.subjects.map((s) => h("option", { value: s.en }, subjectLabel(s.en, state.boot.subjects))));
    subj.value = room.subject || "";
    return h("details", { class: "panel more" },
      h("summary", {}, t("class_options")),
      h("div", { class: "grid2" },
        h("label", { class: "field" }, h("span", { class: "label" }, t("class_name")), name, h("span", { class: "hint" }, t("class_name_hint"))),
        h("label", { class: "field" }, h("span", { class: "label" }, t("class_subject")), subj)),
      h("div", { class: "row between" },
        h("button", { class: "btn primary", onClick: async () => {
          const s = JSON.parse(JSON.stringify(structure)); const r = s.rooms.find((x) => x.id === room.id);
          r.name = name.value.trim() || r.name; r.subject = subj.value;
          if (await guarded(() => api.put("/api/structure", stripExtra(s)))) { toast(t("saved")); reload(); }
        } }, t("save")),
        h("button", { class: "btn danger", onClick: async () => {
          if (!await confirmBox(t("delete_class_confirm", { name: roomLabel(room, structure), n: room.student_count }))) return;
          const s = JSON.parse(JSON.stringify(structure)); s.rooms = s.rooms.filter((x) => x.id !== room.id);
          if (await guarded(() => api.put("/api/structure", stripExtra(s)))) { toast(t("class_deleted")); reload(false); }
        } }, icon("trash"), t("delete_class"))));
  }

  // ---------------- grade settings (shared by all classes of the grade)
  function gradePanel(grade) {
    const st = grade.settings;
    const f = {
      period: h("input", { type: "number", min: 5, max: 240, value: st.period_minutes }),
      book: h("input", { type: "text", value: st.textbook }),
      lms: h("input", { type: "text", value: st.lms_stage_name }),
      band: h("select", {}, ["KG", "LOWER_PRIMARY", "UPPER_PRIMARY", "PREPARATORY", "SECONDARY"].map((b) => h("option", { value: b }, t(`band_${b}`)))),
    };
    f.band.value = st.age_band;
    const maxes = Object.fromEntries(["Behavior", "Attendance", "Classwork", "Homework", "Quiz Score"].map((k) => [k,
      h("input", { type: "number", min: 0, max: 100, value: st.grading_maximums[k] ?? 0 })]));
    return h("details", { class: "panel more" },
      h("summary", {}, t("grade_settings_title", { grade: gradeName(grade) })),
      h("p", { class: "muted small" }, t("grade_settings_hint")),
      h("div", { class: "grid2" },
        h("label", { class: "field" }, h("span", { class: "label" }, t("period_minutes")), f.period),
        h("label", { class: "field" }, h("span", { class: "label" }, t("textbook")), f.book),
        h("label", { class: "field" }, h("span", { class: "label" }, t("lms_stage")), f.lms),
        h("label", { class: "field" }, h("span", { class: "label" }, t("age_band")), f.band, h("span", { class: "hint" }, t("age_band_hint")))),
      h("div", { class: "label" }, t("grading_maximums")),
      h("div", { class: "grid2" }, Object.entries(maxes).map(([k, el]) => h("label", { class: "field" }, h("span", { class: "label" }, t(`gm_${k}`)), el))),
      h("button", { class: "btn primary", onClick: async () => {
        const s = JSON.parse(JSON.stringify(structure)); const g = s.grades.find((x) => x.id === grade.id);
        g.settings = { ...g.settings, period_minutes: parseInt(f.period.value || "40", 10), textbook: f.book.value.trim(), lms_stage_name: f.lms.value.trim(), age_band: f.band.value,
          grading_maximums: Object.fromEntries(Object.entries(maxes).map(([k, el]) => [k, parseInt(el.value || "0", 10)])) };
        if (await guarded(() => api.put("/api/structure", stripExtra(s)))) { toast(t("saved")); reload(); }
      } }, t("save")));
  }

  const stripExtra = (s) => ({ stages: s.stages, grades: s.grades, rooms: s.rooms.map(({ student_count, ...r }) => r) });

  function addClasses() {
    const picker = classPicker({ presets: structure.presets, existing: structure.rooms });
    modal({ title: t("add_classes"), wide: true, body: picker.el,
      actions: [{ label: t("cancel") }, { label: t("add_selected"), kind: "primary", onClick: async () => {
        if (!picker.count()) return false;
        const r = await guarded(() => api.post("/api/structure/build", { selection: picker.value() }));
        if (!r) return false; toast(t("saved")); reload();
      } }] });
  }

  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_classes")), h("p", {}, t("classes_page_lead"))),
      h("button", { class: "btn primary", onClick: addClasses }, icon("plus"), t("add_classes"))),
    h("div", { class: "split" }, treeBox, detail)));
  drawTree(); await drawDetail();
}
