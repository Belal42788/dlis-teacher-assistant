import { hubTabs } from "../components/hubtabs.js";
import { h, icon, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { emptyState } from "../components/empty.js";
import { roomLabel } from "../labels.js";

// Seating chart: pick a student, tap a seat. Tap a seated student to pick them up again. Saved after every change; printable.
export async function renderSeating(root) {
  const structure = await api.get("/api/structure");
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_seating")), h("p", {}, t("st_lead"))));
  if (!structure.rooms.length) {
    root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "seating"), head, h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_rooms"), " ", h("a", { href: "#/classes" }, t("nav_classes"))))));
    return;
  }
  let room = (structure.rooms.find((r) => r.id === q.get("room")) || structure.rooms[0]).id;
  const sel = h("select", { "aria-label": t("d_class"), onChange: (e) => { room = e.target.value; load(); } }, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  sel.value = room;
  const body = h("div", {});
  let st = null, picked = "";   // st = {rows, cols, seats, students}; picked = the student waiting for a seat

  const save = async () => {
    const r = await guarded(() => api.put("/api/seating", { room_id: room, rows: st.rows, cols: st.cols, seats: st.seats }));
    if (r) st = r;
  };
  const seatedNames = () => new Set(Object.values(st.seats));
  const change = async (fn) => { fn(); picked = ""; draw(); await save(); draw(); };

  function tap(key) {
    const here = st.seats[key];
    if (picked && !here) return change(() => { st.seats[key] = picked; });
    if (picked && here) return change(() => { const was = Object.keys(st.seats).find((k) => st.seats[k] === picked); st.seats[key] = picked; if (was) st.seats[was] = here; else picked = here; });
    if (here) { picked = here; delete st.seats[key]; draw(); save(); }   // pick the student up: the seat is free again
  }
  const order = () => [...st.students];
  const fill = (names) => change(() => {
    st.seats = {};
    names.forEach((n, i) => { if (i < st.rows * st.cols) st.seats[`${Math.floor(i / st.cols)}-${i % st.cols}`] = n; });
  });
  const shuffled = () => { const a = order(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const size = (key, delta) => change(() => { st[key] = Math.min(12, Math.max(1, st[key] + delta)); });

  function draw() {
    const waiting = st.students.filter((n) => !seatedNames().has(n));
    const grid = h("div", { class: "seat-grid", style: { gridTemplateColumns: `repeat(${st.cols}, minmax(0, 1fr))` } },
      ...Array.from({ length: st.rows * st.cols }, (_, i) => {
        const key = `${Math.floor(i / st.cols)}-${i % st.cols}`, who = st.seats[key];
        return h("button", { type: "button", class: `seat${who ? " full" : ""}${picked && !who ? " free" : ""}`, onClick: () => tap(key), "aria-label": who || t("st_empty_seat") }, who ? h("span", { dir: "auto" }, who) : "");
      }));
    const stepper = (key, label) => h("div", { class: "row" }, h("span", { class: "label" }, label),
      h("button", { class: "btn small", "aria-label": `${label} −`, onClick: () => size(key, -1) }, "−"), h("b", {}, String(st[key])), h("button", { class: "btn small", "aria-label": `${label} +`, onClick: () => size(key, 1) }, "+"));
    body.replaceChildren(
      h("div", { class: "panel st-tools" }, stepper("rows", t("st_rows")), stepper("cols", t("st_cols")), h("span", { class: "grow" }),
        h("button", { class: "btn", onClick: () => fill(order()) }, t("st_auto")), h("button", { class: "btn", onClick: () => fill(shuffled()) }, icon("spark"), t("st_shuffle")),
        h("button", { class: "btn", onClick: async () => { if (await confirmBox(t("st_clear_confirm"), { okLabel: t("st_clear") })) change(() => { st.seats = {}; }); } }, t("st_clear")),
        h("button", { class: "btn primary", onClick: () => window.print() }, icon("file"), t("st_print"))),
      h("div", { class: `panel st-pool${picked ? " has-pick" : ""}` }, h("h3", {}, picked ? t("st_pick_seat", { name: picked }) : waiting.length ? t("st_unplaced") : t("st_all_seated")),
        h("div", { class: "row", style: { flexWrap: "wrap" } }, waiting.map((n) => h("button", { class: `chip${picked === n ? " on" : ""}`, "aria-pressed": String(picked === n), onClick: () => { picked = picked === n ? "" : n; draw(); } }, n)))),
      h("div", { class: "seat-print" }, h("div", { class: "seat-board" }, t("st_front")), grid));
  }

  async function load() {
    st = await api.get(`/api/seating?room=${encodeURIComponent(room)}`);
    picked = "";
    if (!root.isConnected) return;
    if (!st.students.length) { body.replaceChildren(emptyState({ icon: "classes", title: t("bh_no_students"), text: t("bh_no_students_text"), action: { label: t("nav_classes"), icon: "classes", onClick: () => { location.hash = "#/classes"; } } })); return; }
    draw();
  }

  root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "seating"), head, h("div", { class: "panel no-print" }, h("label", {}, h("span", { class: "label" }, t("d_class")), sel)), body));
  await load();
}
