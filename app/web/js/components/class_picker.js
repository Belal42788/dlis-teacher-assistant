import { h } from "../dom.js";
import { t } from "../i18n.js";
import { gradeName, stageName } from "../labels.js";

// Pick grades and sections (A, B, C...) from a ready-made list.
// `existing` = structure.rooms already in the app (shown as locked so nothing is removed by accident).
export function classPicker({ presets, existing = [] }) {
  const selection = {}; // gradeId -> Set(letters)
  const locked = new Set(existing.map((r) => r.id));
  for (const r of existing) {
    const letter = r.id.split("-").pop().toUpperCase();
    (selection[r.grade_id] ||= new Set()).add(letter);
  }
  const root = h("div", {});
  const maxLetters = {}; // how many letters shown per grade

  function render() {
    root.replaceChildren();
    for (const stage of presets.stages) {
      const grades = presets.grades.filter((g) => g.stage_id === stage.id);
      root.append(h("div", { class: "stage-title" },
        h("h3", {}, stageName(stage)),
        h("button", { class: "btn small ghost", onClick: () => {
          const all = grades.every((g) => selection[g.id]?.size);
          for (const g of grades) {
            if (all) { for (const l of [...(selection[g.id] || [])]) if (!locked.has(`${g.id}-${l.toLowerCase()}`)) selection[g.id].delete(l); }
            else if (!selection[g.id]?.size) selection[g.id] = new Set(["A"]);
          }
          render();
        } }, t("select_whole_stage"))));
      for (const g of grades) {
        const chosen = selection[g.id] || new Set();
        const letters = presets.room_letters.slice(0, Math.max(maxLetters[g.id] || 4, ...[...chosen].map((l) => presets.room_letters.indexOf(l) + 1)));
        root.append(h("div", { class: "grade-row" },
          h("label", { class: "row", style: { gap: ".6rem" } },
            h("input", {
              type: "checkbox", checked: chosen.size > 0, style: { width: "22px", height: "22px" },
              onChange: (e) => {
                if (e.target.checked) selection[g.id] = new Set(["A"]);
                else for (const l of [...chosen]) if (!locked.has(`${g.id}-${l.toLowerCase()}`)) chosen.delete(l);
                render();
              },
            }), h("b", {}, gradeName(g))),
          h("div", { class: "letters", role: "group", "aria-label": t("sections_of", { grade: gradeName(g) }) },
            chosen.size ? [letters.map((l) => {
              const on = chosen.has(l);
              const isLocked = locked.has(`${g.id}-${l.toLowerCase()}`);
              return h("button", {
                class: `chip sq${on ? " on" : ""}`, "aria-pressed": String(on), disabled: isLocked,
                title: isLocked ? t("already_added") : "",
                onClick: () => { on ? chosen.delete(l) : chosen.add(l); selection[g.id] = chosen; render(); },
              }, l);
            }), letters.length < presets.room_letters.length
              ? h("button", { class: "chip sq", "aria-label": t("more_sections"), onClick: () => { maxLetters[g.id] = letters.length + 1; render(); } }, "+") : null]
              : h("span", { class: "muted small" }, t("tick_to_add")))));
      }
    }
  }
  render();

  return {
    el: root,
    value: () => Object.fromEntries(Object.entries(selection).filter(([, s]) => s.size).map(([k, s]) => [k, [...s]])),
    count: () => Object.values(selection).reduce((n, s) => n + s.size, 0),
  };
}
