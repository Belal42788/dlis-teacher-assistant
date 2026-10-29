import { h, icon, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { roomLabel, mapName } from "../labels.js";

const memo = { floor: "", sel: "" };
const rnd = () => Math.random().toString(36).slice(2, 10);

export async function renderMap(root) {
  const [map, structure] = await Promise.all([api.get("/api/map"), api.get("/api/structure")]);
  const [GW, GH] = map.grid;
  let edit = false, query = "";
  const floors = map.floors;
  if (!floors.some((f) => f.id === memo.floor)) memo.floor = floors[0]?.id || "";
  const curFloor = () => floors.find((f) => f.id === memo.floor);
  const findRoom = () => curFloor()?.rooms.find((r) => r.id === memo.sel);
  let saveTimer = 0;
  const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => guarded(() => api.put("/api/map", { floors })), 400); };

  const tabs = h("div", { class: "map-tabs" });
  const canvas = h("div", { class: "map-canvas editing" });
  const building = h("div", { class: "bld" });
  const stage = h("div", {});
  const side = h("div", { class: "panel map-side" });
  const search = h("input", { type: "search", placeholder: t("mp_search"), "aria-label": t("mp_search"), onInput: (e) => { query = e.target.value.trim().toLowerCase(); draw(); } });
  const editBtn = h("button", { class: "btn", onClick: () => { edit = !edit; editBtn.classList.toggle("primary", edit); draw(); } }, icon("edit"), t("mp_edit"));

  function matches(r) { return query && (r.name.toLowerCase().includes(query) || mapName(r.name).toLowerCase().includes(query) || r.person.toLowerCase().includes(query) || r.notes.toLowerCase().includes(query)); }
  function drawTabs() {
    tabs.replaceChildren(...floors.map((f) => h("button", { class: "btn" + (f.id === memo.floor ? " primary" : ""), onClick: () => { memo.floor = f.id; memo.sel = ""; draw(); } }, f.name)),
      edit ? h("button", { class: "btn ghost", onClick: () => { const f = { id: rnd(), name: t("mp_floor_n", { n: floors.length + 1 }), rooms: [] }; floors.push(f); memo.floor = f.id; save(); draw(); } }, icon("plus"), t("mp_add_floor")) : null);
  }
  function roomEl(r, f, oy = 0, gh = GH) {
    const pick = () => { memo.sel = r.id; memo.floor = f.id; draw(); };
    return h("div", { class: `map-room k-${r.kind}${r.id === memo.sel ? " sel" : ""}${matches(r) ? " hit" : ""}`, tabindex: 0, role: "button", "aria-label": mapName(r.name),
      style: { left: `${r.x / GW * 100}%`, top: `${(r.y - oy) / gh * 100}%`, width: `${r.w / GW * 100}%`, height: `${r.h / gh * 100}%` },
      onClick: pick, onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } } }, h("span", {}, edit ? r.name : mapName(r.name)));
  }
  function drawCanvas() {
    const f = curFloor();
    canvas.style.aspectRatio = `${GW} / ${GH}`;
    canvas.replaceChildren(...(f ? f.rooms : []).map((r) => {
      const el = roomEl(r, f);
      el.addEventListener("pointerdown", (e) => startDrag(e, r, el, "move"));
      if (r.id === memo.sel) { const hd = h("i", { class: "map-handle" }); hd.addEventListener("pointerdown", (e) => { e.stopPropagation(); startDrag(e, r, el, "size"); }); el.append(hd); }
      return el;
    }), !f || !f.rooms.length ? h("div", { class: "map-empty" }, t("mp_empty_edit")) : null);
  }
  // The whole school as one drawing: the building seen from the front, top floor first.
  // Rooms are laid out automatically (equal widths, no gaps) in three blocks: left wing, middle, right wing.
  function flowRoom(r, f) {
    const pick = () => { memo.sel = r.id; memo.floor = f.id; draw(); };
    return h("div", { class: `bld-room k-${r.kind}${r.id === memo.sel ? " sel" : ""}${matches(r) ? " hit" : ""}`, tabindex: 0, role: "button", "aria-label": mapName(r.name),
      onClick: pick, onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } } }, h("span", {}, mapName(r.name)));
  }
  function wingEl(rooms, f, cls, maxCols) {
    const n = rooms.length;
    const cols = Math.max(1, Math.min(maxCols, n));
    return h("div", { class: `bld-wing ${cls}`, style: { gridTemplateColumns: `repeat(${cols}, 1fr)`, flex: `${cls === "mid" ? 1 : 2} 1 0` } }, rooms.map((r) => flowRoom(r, f)));
  }
  function drawBuilding() {
    const rows = [...floors].reverse().map((f) => {
      const order = (a, b) => a.y - b.y || a.x - b.x;
      const left = f.rooms.filter((r) => r.x + r.w / 2 < 9).sort(order);
      const right = f.rooms.filter((r) => r.x + r.w / 2 >= 15).sort(order);
      const mid = f.rooms.filter((r) => r.x + r.w / 2 >= 9 && r.x + r.w / 2 < 15).sort(order);
      const wings = [left.length ? wingEl(left, f, "left", 3) : null, mid.length ? wingEl(mid, f, "mid", 1) : null, right.length ? wingEl(right, f, "right", 3) : null].filter(Boolean);
      return h("div", { class: "bld-floor" }, h("div", { class: "bld-label" }, h("span", {}, mapName(f.name))), h("div", { class: "bld-rooms" }, wings));
    });
    building.replaceChildren(h("div", { class: "bld-roof" }), h("div", { class: "bld-body" }, rows), h("div", { class: "bld-ground" }),
      floors.length ? null : h("div", { class: "map-empty" }, t("mp_empty")));
  }
  function startDrag(e, r, el, mode) {
    e.preventDefault(); memo.sel = r.id;
    const box = canvas.getBoundingClientRect(), cw = box.width / GW, ch = box.height / GH, sx = e.clientX, sy = e.clientY, o = { x: r.x, y: r.y, w: r.w, h: r.h };
    let moved = false;
    const mv = (ev) => {
      const dx = Math.round((ev.clientX - sx) / cw), dy = Math.round((ev.clientY - sy) / ch);
      if (mode === "move") { r.x = Math.max(0, Math.min(GW - r.w, o.x + dx)); r.y = Math.max(0, Math.min(GH - r.h, o.y + dy)); }
      else { r.w = Math.max(1, Math.min(GW - r.x, o.w + dx)); r.h = Math.max(1, Math.min(GH - r.y, o.h + dy)); }
      moved = true;
      Object.assign(el.style, { left: `${r.x / GW * 100}%`, top: `${r.y / GH * 100}%`, width: `${r.w / GW * 100}%`, height: `${r.h / GH * 100}%` });
    };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); if (moved) save(); draw(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  }
  const label = (k) => t(`mp_k_${k}`);
  function drawSide() {
    const f = curFloor(), r = findRoom();
    if (edit) {
      const bar = [];
      if (f) bar.push(h("label", { class: "field" }, h("span", { class: "label" }, t("mp_floor_name")), h("input", { type: "text", value: f.name, onInput: (e) => { f.name = e.target.value.slice(0, 40); save(); drawTabs(); } })),
        h("div", { class: "row" }, h("button", { class: "btn primary", onClick: () => { const n = { id: rnd(), name: t("mp_new_room"), kind: "class", x: 0, y: 0, w: 4, h: 3, room_id: "", notes: "", person: "", phone: "" }; f.rooms.push(n); memo.sel = n.id; save(); draw(); } }, icon("plus"), t("mp_add_room")),
          h("button", { class: "btn ghost", onClick: async () => { if (!(await confirmBox(t("mp_del_floor_confirm")))) return; floors.splice(floors.indexOf(f), 1); memo.floor = floors[0]?.id || ""; memo.sel = ""; save(); draw(); } }, icon("trash"), t("mp_del_floor"))));
      else bar.push(h("p", { class: "muted" }, t("mp_need_floor")));
      if (r) {
        const set = (k) => (e) => { r[k] = e.target.value; save(); if (k === "name") canvas.querySelector(".map-room.sel span").textContent = r.name || "?"; };
        const kind = h("select", { onChange: (e) => { r.kind = e.target.value; save(); drawCanvas(); } }, map.kinds.map((k) => h("option", { value: k }, label(k)))); kind.value = r.kind;
        const link = h("select", { onChange: (e) => { r.room_id = e.target.value; save(); } }, h("option", { value: "" }, "—"), structure.rooms.map((x) => h("option", { value: x.id }, roomLabel(x, structure)))); link.value = r.room_id;
        bar.push(h("hr"), h("label", { class: "field" }, h("span", { class: "label" }, t("mp_name")), h("input", { type: "text", value: r.name, onInput: set("name") })),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_kind")), kind),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_class_link")), link),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_person")), h("input", { type: "text", value: r.person, onInput: set("person") })),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_phone")), h("input", { type: "text", dir: "ltr", value: r.phone, onInput: set("phone") })),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_notes")), h("textarea", { rows: 3, onInput: set("notes") }, r.notes)),
          h("button", { class: "btn ghost", onClick: () => { f.rooms.splice(f.rooms.indexOf(r), 1); memo.sel = ""; save(); draw(); } }, icon("trash"), t("mp_del_room")));
      } else if (f) bar.push(h("p", { class: "muted small" }, t("mp_edit_hint")));
      side.replaceChildren(...bar);
      return;
    }
    if (!r) { side.replaceChildren(h("p", { class: "muted" }, t("mp_pick"))); return; }
    const linked = structure.rooms.find((x) => x.id === r.room_id);
    side.replaceChildren(h("h3", {}, mapName(r.name)), h("div", { class: `map-kind k-${r.kind}` }, label(r.kind)), h("div", { class: "muted small" }, mapName(f.name)),
      linked ? h("p", {}, icon("classes"), " ", roomLabel(linked, structure)) : null,
      r.person ? h("p", {}, icon("user"), " ", h("b", {}, r.person)) : null,
      r.phone ? h("p", {}, icon("phone"), " ", h("a", { href: `tel:${r.phone.replace(/[^+\d]/g, "")}`, dir: "ltr" }, r.phone)) : null,
      r.notes ? h("p", { class: "pre" }, r.notes) : null);
  }
  function draw() {
    tabs.hidden = !edit;
    if (edit) { drawTabs(); drawCanvas(); stage.replaceChildren(canvas); } else { drawBuilding(); stage.replaceChildren(building); }
    drawSide();
  }

  const legend = h("div", { class: "map-legend" }, map.kinds.map((k) => h("span", {}, h("i", { class: `k-${k}` }), label(k))));
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_map")), h("p", {}, t("mp_lead"))), h("div", { class: "row" }, search, editBtn)),
    tabs, h("div", { class: "map-wrap" }, h("div", {}, stage, legend), side)));
  draw();
}
