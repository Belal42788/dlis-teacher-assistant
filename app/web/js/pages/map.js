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
  // The whole school as a see-through 3D building: every floor open, rooms as glass boxes. Drag to turn it, wheel to zoom.
  const CW_ = 150, CH_ = 118, ROWS = 2, MID_W = 170, ANG = 15, FLOOR_GAP = 330, WALL_H = 110, PAD = 24;
  const view = { az: 0, tilt: 56, zoom: 0.62 };
  const VIEW0 = { az: 0, tilt: 56, zoom: 0.62 };
  function applyView() {
    scene.style.setProperty("--az", `${view.az}deg`); scene.style.setProperty("--tilt", `${view.tilt}deg`); scene.style.setProperty("--zoom", view.zoom);
  }
  // one room as a glass box at (x, y) inside its wing, w x d pixels
  function room3d(r, f, x, y, w, d) {
    const face = (cls, style) => h("i", { class: `f3 ${cls}`, style });
    const pick = () => { if (scene._dragged) return; memo.sel = r.id; memo.floor = f.id; draw(); };
    return h("div", { class: `room3d k-${r.kind}${r.id === memo.sel ? " sel" : ""}${matches(r) ? " hit" : ""}`, tabindex: 0, role: "button", "aria-label": mapName(r.name),
      style: { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${d}px` },
      onClick: pick, onKeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } } },
      face("f3-floor", {}),
      face("f3-w f3-back", { width: `${w}px`, height: `${WALL_H}px` }),
      face("f3-w f3-front", { width: `${w}px`, height: `${WALL_H}px`, transform: `translateY(${d}px) rotateX(90deg)` }),
      face("f3-w f3-left", { width: `${d}px`, height: `${WALL_H}px`, transform: "rotateZ(90deg) rotateX(90deg)" }),
      face("f3-w f3-right", { width: `${d}px`, height: `${WALL_H}px`, transform: `translateX(${w}px) rotateZ(90deg) rotateX(90deg)` }),
      h("span", { class: "f3-label" }, h("b", {}, mapName(r.name))));
  }
  // Seen from above the building is an upside-down V: the administrative block is at the back, the two class wings come towards you.
  function drawBuilding() {
    const order = (a, b) => a.y - b.y || a.x - b.x;
    const zone = (f, wg) => f.rooms.filter((r) => (r.wing || "left") === wg).sort(order);
    const cols = Math.max(1, ...floors.map((f) => Math.max(Math.ceil(zone(f, "left").length / ROWS), Math.ceil(zone(f, "right").length / ROWS))));
    const wingW = cols * CW_, D = ROWS * CH_, rad = ANG * Math.PI / 180;
    const FW = 2 * wingW * Math.cos(rad) + MID_W + 2 * PAD, FH = D + wingW * Math.sin(rad) + 2 * PAD, cx = wingW * Math.cos(rad) + PAD;
    const total = Math.max(0, floors.length - 1) * FLOOR_GAP + WALL_H;
    const slabs = floors.map((f, i) => {
      const left = zone(f, "left"), right = zone(f, "right"), mid = zone(f, "center");
      const wing = (rooms, side) => { const wf = Math.max(1, Math.ceil(rooms.length / ROWS)) * CW_; return h("div", { class: `zone3d ${side}`, style: { left: `${side === "left" ? cx - wf : cx + MID_W}px`, top: `${PAD}px`, width: `${wf}px`, height: `${D}px`,
          transformOrigin: side === "left" ? "100% 100%" : "0 100%", transform: `rotateZ(${side === "left" ? -ANG : ANG}deg)` } },
        rooms.map((r, k) => { const col = Math.floor(k / ROWS), row = k % ROWS; const x = side === "left" ? wf - (col + 1) * CW_ : col * CW_;
          return room3d(r, f, x + 3, row * CH_ + 3, CW_ - 6, CH_ - 6); })); };
      const midRows = Math.max(1, mid.length), mh = D / midRows;
      const center = h("div", { class: "zone3d center", style: { left: `${cx}px`, top: `${PAD}px`, width: `${MID_W}px`, height: `${D}px` } },
        mid.map((r, k) => room3d(r, f, 3, k * mh + 3, MID_W - 6, mh - 6)));
      return h("div", { class: "floor3d", style: { width: `${FW}px`, height: `${FH}px`, transform: `translateZ(${i * FLOOR_GAP}px)` } },
        h("span", { class: "floor3d-name" }, h("b", {}, mapName(f.name))), wing(left, "left"), center, wing(right, "right"));
    });
    world.style.width = `${FW}px`; world.style.height = `${FH}px`;
    world.style.setProperty("--half", `${total / 2}px`);
    world.replaceChildren(h("div", { class: "ground3d" }), ...slabs);
    building.replaceChildren(scene, floors.length ? null : h("div", { class: "map-empty" }, t("mp_empty")));
    applyView();
  }
  const world = h("div", { class: "world3d" });
  const scene = h("div", { class: "scene3d", title: t("mp_drag_hint") }, world);
  scene.addEventListener("pointerdown", (e) => {
    scene._dragged = false; const x0 = e.clientX, y0 = e.clientY, az0 = view.az, t0 = view.tilt;
    const mv = (ev) => {
      const dx = ev.clientX - x0, dy = ev.clientY - y0;
      if (Math.abs(dx) + Math.abs(dy) > 5) scene._dragged = true;
      if (scene._dragged) { view.az = az0 + dx * 0.35; view.tilt = Math.max(15, Math.min(80, t0 - dy * 0.25)); applyView(); }
    };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); setTimeout(() => { scene._dragged = false; }, 0); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  scene.addEventListener("wheel", (e) => { if (!e.ctrlKey) return; e.preventDefault(); view.zoom = Math.max(0.35, Math.min(1.6, view.zoom * (e.deltaY < 0 ? 1.08 : 0.92))); applyView(); }, { passive: false });
  const viewBtns = h("div", { class: "row small", style: { marginTop: ".5rem" } },
    h("button", { class: "btn small", onClick: () => { Object.assign(view, VIEW0); applyView(); } }, t("mp_view_reset")),
    h("button", { class: "btn small", onClick: () => { Object.assign(view, { az: 0, tilt: 78 }); applyView(); } }, t("mp_view_front")),
    h("button", { class: "btn small", onClick: () => { Object.assign(view, { az: 0, tilt: 16 }); applyView(); } }, t("mp_view_top")),
    h("button", { class: "btn small", onClick: () => { view.az += 90; applyView(); } }, t("mp_view_turn")),
    h("button", { class: "btn small icon", "aria-label": "+", onClick: () => { view.zoom = Math.min(1.6, view.zoom * 1.15); applyView(); } }, "+"),
    h("button", { class: "btn small icon", "aria-label": "-", onClick: () => { view.zoom = Math.max(0.35, view.zoom / 1.15); applyView(); } }, "−"));
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
        h("div", { class: "row" }, h("button", { class: "btn primary", onClick: () => { const n = { id: rnd(), name: t("mp_new_room"), kind: "class", x: 0, y: 0, w: 4, h: 3, room_id: "", notes: "", person: "", phone: "", wing: "left" }; f.rooms.push(n); memo.sel = n.id; save(); draw(); } }, icon("plus"), t("mp_add_room")),
          h("button", { class: "btn ghost", onClick: async () => { if (!(await confirmBox(t("mp_del_floor_confirm")))) return; floors.splice(floors.indexOf(f), 1); memo.floor = floors[0]?.id || ""; memo.sel = ""; save(); draw(); } }, icon("trash"), t("mp_del_floor"))));
      else bar.push(h("p", { class: "muted" }, t("mp_need_floor")));
      if (r) {
        const set = (k) => (e) => { r[k] = e.target.value; save(); if (k === "name") canvas.querySelector(".map-room.sel span").textContent = r.name || "?"; };
        const kind = h("select", { onChange: (e) => { r.kind = e.target.value; save(); drawCanvas(); } }, map.kinds.map((k) => h("option", { value: k }, label(k)))); kind.value = r.kind;
        const wing = h("select", { onChange: (e) => { r.wing = e.target.value; save(); } }, (map.wings || ["left", "center", "right"]).map((k) => h("option", { value: k }, t(`mp_wing_${k}`)))); wing.value = r.wing || "left";
        const link = h("select", { onChange: (e) => { r.room_id = e.target.value; save(); } }, h("option", { value: "" }, "—"), structure.rooms.map((x) => h("option", { value: x.id }, roomLabel(x, structure)))); link.value = r.room_id;
        bar.push(h("hr"), h("label", { class: "field" }, h("span", { class: "label" }, t("mp_name")), h("input", { type: "text", value: r.name, onInput: set("name") })),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_kind")), kind),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_wing")), wing),
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
      r.notes ? h("p", { class: "pre" }, r.notes) : null,
      linked ? h("div", { class: "map-actions" },
        h("p", { class: "muted small" }, t("mp_students_n", { n: linked.student_count || 0 })),
        h("a", { class: "btn small", href: `#/classes?room=${linked.id}` }, icon("classes"), t("mp_act_students")),
        h("a", { class: "btn small", href: `#/log?room=${linked.id}` }, icon("book"), t("mp_act_log")),
        h("a", { class: "btn small", href: `#/docs?room=${linked.id}` }, icon("file"), t("mp_act_docs"))) : null);
  }
  function draw() {
    tabs.hidden = !edit; viewBtns.hidden = edit;
    if (edit) { drawTabs(); drawCanvas(); stage.replaceChildren(canvas); } else { drawBuilding(); stage.replaceChildren(building); }
    drawSide();
  }

  const legend = h("div", { class: "map-legend" }, map.kinds.map((k) => h("span", {}, h("i", { class: `k-${k}` }), label(k))));
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_map")), h("p", {}, t("mp_lead"))), h("div", { class: "row" }, search, editBtn)),
    tabs, h("div", { class: "map-wrap" }, h("div", {}, stage, viewBtns, legend), side)));
  draw();
}
