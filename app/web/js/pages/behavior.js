import { hubTabs } from "../components/hubtabs.js";
import { h, icon, confirmBox, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { emptyState } from "../components/empty.js";
import { roomLabel, fmtDate } from "../labels.js";

// Behaviour notes: a quick note about a student, good or to follow up. A message for the parent is written here, on this computer.
export async function renderBehavior(root) {
  const structure = await api.get("/api/structure");
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_behavior")), h("p", {}, t("bh_lead"))));
  if (!structure.rooms.length) {
    root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "behavior"), head, h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_rooms"), " ", h("a", { href: "#/classes" }, t("nav_classes"))))));
    return;
  }
  let room = (structure.rooms.find((r) => r.id === q.get("room")) || structure.rooms[0]).id;
  let who = "";   // filter: one student, or everyone
  const sel = h("select", { "aria-label": t("d_class"), onChange: (e) => { room = e.target.value; who = ""; draw(); } }, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  sel.value = room;
  const body = h("div", {});

  async function draw() {
    const d = await api.get(`/api/behavior?room=${encodeURIComponent(room)}`);
    if (!root.isConnected) return;
    if (!d.students.length) {
      body.replaceChildren(emptyState({ icon: "classes", title: t("bh_no_students"), text: t("bh_no_students_text"), action: { label: t("nav_classes"), icon: "classes", onClick: () => { location.hash = "#/classes"; } } }));
      return;
    }
    // ---- the quick form
    let kind = "good";
    const student = h("select", { "aria-label": t("bh_student") }, d.students.map((n) => h("option", { value: n }, n)));
    if (who) student.value = who;
    const note = h("input", { type: "text", maxlength: 500, placeholder: t("bh_note_ph"), "aria-label": t("bh_note"), style: { flex: "1 1 18rem" } });
    const kinds = h("div", { class: "row" });
    const drawKinds = () => kinds.replaceChildren(...[["good", "bh_good"], ["concern", "bh_concern"]].map(([k, key]) =>
      h("button", { type: "button", class: `chip${kind === k ? " on" : ""}`, "aria-pressed": String(kind === k), onClick: () => { kind = k; drawKinds(); } }, t(key))));
    drawKinds();
    const add = async () => {
      const r = await guarded(() => api.post("/api/behavior", { room_id: room, student: student.value, kind, note: note.value, date: new Date().toISOString().slice(0, 10) }));
      if (r) { toast(t("saved")); who = student.value; draw(); }
    };
    note.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
    const form = h("div", { class: "panel" }, h("div", { class: "row" }, student, kinds), h("div", { class: "row", style: { marginTop: ".5rem" } }, note, h("button", { class: "btn primary", onClick: add }, icon("plus"), t("bh_add"))));

    // ---- who has notes
    const chips = h("div", { class: "row", style: { flexWrap: "wrap", marginBottom: ".6rem" } },
      h("button", { class: `chip${!who ? " on" : ""}`, "aria-pressed": String(!who), onClick: () => { who = ""; draw(); } }, t("bh_all")),
      ...d.students.filter((n) => d.counts[n].good + d.counts[n].concern).map((n) => {
        const c = d.counts[n];
        return h("button", { class: `chip${who === n ? " on" : ""}`, "aria-pressed": String(who === n), onClick: () => { who = n; draw(); } },
          n, " ", c.good ? h("span", { class: "tag", title: t("bh_good") }, `+${c.good}`) : null, c.open ? h("span", { class: "tag warn", title: t("bh_open") }, `${c.open}`) : null);
      }));

    // ---- the notes
    const rows = d.notes.filter((n) => !who || n.student === who).map((n) => {
      const msg = () => {
        const text = t(n.kind === "good" ? "bh_msg_good" : "bh_msg_concern", { name: n.student, note: n.note });
        navigator.clipboard?.writeText(text).then(() => toast(t("pm_copied")), () => {});
      };
      return h("div", { class: `bh-note ${n.kind}${n.done ? " done" : ""}` },
        h("div", { class: "grow" }, h("div", {}, h("b", {}, n.student), " ", h("span", { class: `tag${n.kind === "concern" && !n.done ? " warn" : ""}` }, t(n.kind === "good" ? "bh_good" : n.done ? "bh_done" : "bh_concern")), " ", h("span", { class: "muted small" }, fmtDate(n.date))), h("div", { dir: "auto" }, n.note)),
        n.kind === "concern" ? h("button", { class: "btn small", onClick: async () => { await guarded(() => api.post(`/api/behavior/${n.id}/done`, { done: !n.done })); draw(); } }, t(n.done ? "bh_reopen" : "bh_mark_done")) : null,
        h("button", { class: "btn small", onClick: msg }, icon("copy"), t("bh_msg")),
        h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: async () => { if (await confirmBox(t("bh_delete_confirm"), { okLabel: t("remove") })) { await guarded(() => api.post(`/api/behavior/${n.id}/delete`, {})); draw(); } } }, icon("close")));
    });
    body.replaceChildren(form, d.notes.length ? h("div", {}, chips, h("div", { class: "bh-list" }, rows)) : emptyState({ icon: "list", title: t("bh_none_title"), text: t("bh_none_text") }));
  }

  root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "behavior"), head, h("div", { class: "panel" }, h("label", {}, h("span", { class: "label" }, t("d_class")), sel)), body));
  await draw();
}
