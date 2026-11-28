// Settings > End of the year: one guided step. A backup first, then this year's records go to the archive, every class moves up
// one grade, and the students who are leaving the school are taken off.
import { h, icon, toast, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

export function yearEndPanel({ reloadApp }) {
  const box = h("div", {});
  const leaving = {};                         // room id -> Set of names that are leaving the school

  const fateText = (r) => (r.fate === "graduates" ? t("ye_graduates") : r.fate === "moves" ? t("ye_moves", { name: r.next_name }) : t("ye_elsewhere"));

  function roomCard(r) {
    const set = (leaving[r.id] ||= new Set());
    const count = h("span", { class: "chip" }, "");
    const upd = () => { count.textContent = set.size ? t("ye_leaving_n", { n: set.size }) : ""; count.hidden = !set.size; };
    upd();
    return h("details", { class: "ye-room panel" },
      h("summary", {}, h("b", {}, r.name), h("span", { class: "muted small" }, ` · ${t("ye_students_n", { n: r.students.length })}`), h("span", { class: "grow" }), h("span", { class: "small" }, fateText(r)), count),
      r.students.length ? h("div", { class: "ye-names" }, r.students.map((n) => h("label", { class: "ye-name" },
        h("input", { type: "checkbox", onChange: (e) => { e.target.checked ? set.add(n) : set.delete(n); upd(); } }), h("span", {}, n)))) : h("p", { class: "muted small" }, t("ye_no_students")));
  }

  function done(r) {
    box.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", {},
      h("b", {}, t("ye_done", { label: r.label })),
      h("ul", { class: "small" },
        h("li", {}, t("ye_res_moved", { n: r.moved })), r.left ? h("li", {}, t("ye_res_left", { n: r.left })) : null,
        r.graduated ? h("li", {}, t("ye_res_grad", { n: r.graduated })) : null, r.elsewhere ? h("li", {}, t("ye_res_else", { n: r.elsewhere })) : null),
      r.empty.length ? h("p", {}, t("ye_res_empty", { list: r.empty.join("، ") })) : null,
      h("p", { class: "small dir-ltr" }, `Archive: ${r.archive}`), h("p", { class: "small dir-ltr" }, `Backup: ${r.backup}`),
      r.server_changes ? h("p", { class: "small" }, t("ye_res_server")) : null,
      r.server_changes ? serverCard({ pending: true, moved: r.server_moved, removed: r.server_removed }) : null,
      h("div", { class: "row" }, h("a", { class: "btn", href: "#/classes" }, icon("classes"), t("ye_go_classes")), h("button", { class: "btn", onClick: () => reloadApp(false) }, icon("check"), t("ye_reload"))))));
  }

  // Step 2, the administration only: the school server follows (students move up there, those who left are removed, old marks and files are cleared).
  function serverCard(srv) {
    const card = h("div", { class: "panel ye-server" });
    if (!srv || (!srv.pending && !srv.done)) return card;
    api.get("/api/cloud").then((c) => {
      if (c.role !== "admin") return;
      if (srv.done) return card.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", {}, t("ye_srv_done"))));
      const ok = h("input", { type: "checkbox" });
      card.replaceChildren(h("h3", {}, t("ye_srv_title")), h("p", { class: "muted small" }, t("ye_srv_lead", { moved: srv.moved, removed: srv.removed })),
        h("label", { class: "row small" }, ok, h("span", {}, t("ye_srv_confirm"))),
        h("div", { class: "row" }, h("button", { class: "btn primary", onClick: async () => {
          if (!ok.checked) return toast(t("ye_tick"), "error");
          if (!(await confirmBox(t("ye_srv_sure"), { okLabel: t("ye_srv_start") }))) return;
          const r = await guarded(() => api.post("/api/yearend/server", { confirm: true }));
          if (r) card.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", {}, h("b", {}, t("ye_srv_done")),
            h("ul", { class: "small" }, h("li", {}, t("ye_srv_r_moved", { n: r.moved })), h("li", {}, t("ye_srv_r_removed", { n: r.removed })), h("li", {}, t("ye_srv_r_files", { n: r.files }))),
            h("p", { class: "small dir-ltr" }, `Backup: ${r.backup_path}`))));
        } }, icon("check"), t("ye_srv_start"))));
    }).catch(() => {});
    return card;
  }

  async function load() {
    const p = await api.get("/api/yearend");
    const ok = h("input", { type: "checkbox", id: "ye-ok" });
    const again = h("input", { type: "checkbox" });
    const run = h("button", { class: "btn primary", onClick: async () => {
      if (!ok.checked) return toast(t("ye_tick"), "error");
      if (!(await confirmBox(t("ye_sure", { label: p.label }), { okLabel: t("ye_start") }))) return;
      const r = await guarded(() => api.post("/api/yearend", { confirm: true, again: again.checked, leaving: Object.fromEntries(Object.entries(leaving).map(([k, v]) => [k, [...v]]).filter(([, v]) => v.length)) }));
      if (r) done(r);
    } }, icon("check"), t("ye_start"));
    box.replaceChildren(
      h("p", { class: "muted" }, t("ye_lead")),
      h("ol", { class: "ye-steps" }, h("li", {}, t("ye_step1")), h("li", {}, t("ye_step2")), h("li", {}, t("ye_step3")), h("li", {}, t("ye_step4"))),
      p.last.label ? h("div", { class: "banner info" }, icon("info"), h("div", {}, t("ye_last", { label: p.last.label, date: (p.last.at || "").slice(0, 10) }), h("label", { class: "row small" }, again, t("ye_again")))) : null,
      serverCard(p.last.server),
      h("h3", {}, t("ye_rooms")), h("p", { class: "muted small" }, t("ye_leaving_hint")),
      p.rooms.length ? h("div", { class: "ye-rooms" }, p.rooms.map(roomCard)) : h("p", { class: "muted" }, t("ye_no_rooms")),
      h("label", { class: "row ye-ok" }, ok, h("span", {}, t("ye_confirm", { label: p.label }))), h("div", { class: "row" }, run));
  }
  guarded(load);
  return box;
}
