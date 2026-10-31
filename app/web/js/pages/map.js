import { h, icon, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { roomLabel, mapName } from "../labels.js";

const memo = { floor: "", sel: "" };
const rnd = () => Math.random().toString(36).slice(2, 10);

export async function renderMap(root) {
  const [map, structure] = await Promise.all([api.get("/api/map"), api.get("/api/structure")]);
  let edit = false, query = "";
  const floors = map.floors;
  if (!floors.some((f) => f.id === memo.floor)) memo.floor = floors[0]?.id || "";
  const curFloor = () => floors.find((f) => f.id === memo.floor);
  const findRoom = () => curFloor()?.rooms.find((r) => r.id === memo.sel);
  let saveTimer = 0;
  const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => guarded(() => api.put("/api/map", { floors })), 400); };

  const tabs = h("div", { class: "map-tabs" });
  const side = h("div", { class: "panel map-side" });
  const search = h("input", { type: "search", placeholder: t("mp_search"), "aria-label": t("mp_search"), onInput: (e) => { query = e.target.value.trim().toLowerCase(); draw(); } });
  const editBtn = h("button", { class: "btn", onClick: () => { edit = !edit; editBtn.classList.toggle("primary", edit); draw(); } }, icon("edit"), t("mp_edit"));

  function matches(r) { return query && (r.name.toLowerCase().includes(query) || mapName(r.name).toLowerCase().includes(query) || r.person.toLowerCase().includes(query) || r.notes.toLowerCase().includes(query)); }
  function drawTabs() {
    tabs.replaceChildren(...floors.map((f) => h("button", { class: "btn" + (f.id === memo.floor ? " primary" : ""), onClick: () => { memo.floor = f.id; memo.sel = ""; draw(); } }, f.name)),
      edit ? h("button", { class: "btn ghost", onClick: () => { const f = { id: rnd(), name: t("mp_floor_n", { n: floors.length + 1 }), rooms: [] }; floors.push(f); memo.floor = f.id; save(); draw(); } }, icon("plus"), t("mp_add_floor")) : null);
  }
  // The whole school as one solid building seen from above: an upside-down V (administration at the back, a class wing on each side
  // coming towards you). Every floor is open at once. Drag to turn it a little, + / − to zoom. Rooms are drawn in list order inside their wing.
  const NS = "http://www.w3.org/2000/svg";
  const KC = { class: ["#eef6ff", "#a8cdef"], lab: ["#eaf8d8", "#b6d98b"], office: ["#fff0d6", "#e9c387"], admin: ["#ffe3ea", "#e8a9b8"], facility: ["#efe8fb", "#c3b3e6"], other: ["#f1f1f1", "#cfcfcf"] };
  const CW = 150, CH = 112, COR = 42, MID = 340, ANG = 15 * Math.PI / 180, D = 2 * CH + COR + 32, GAP = 430, T = 30, WH = 70, RH = 26, WT = 14;
  const view = { az: 0, tilt: 50 }, VIEW0 = { az: 0, tilt: 50 };
  let zoom = 1;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "bld3"); svg.setAttribute("role", "group"); svg.setAttribute("aria-label", t("nav_map"));
  const wrap3 = h("div", { class: "bld3-wrap", title: t("mp_drag_hint") }, svg);
  const sv = (tag, attrs = {}, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.append(e); return e; };

  function drawBuilding() {
    svg.replaceChildren();
    const ca = Math.cos(view.az * Math.PI / 180), sa = Math.sin(view.az * Math.PI / 180), ct = Math.cos(view.tilt * Math.PI / 180), st = Math.sin(view.tilt * Math.PI / 180);
    const S = 0.9; let ZO = 0;
    const proj = (x, y, z0) => { const z = z0 + ZO, rx = x * ca - y * sa, ry = x * sa + y * ca; return [rx * S, (ry * ct - z * st) * S]; };
    const depth = (x, y) => x * sa + y * ca;
    const P3 = (p, z) => proj(p[0], p[1], z);
    const poly = (pts, fill, extra = {}, parent = svg) => sv("polygon", { points: pts.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" "), fill, ...extra }, parent);
    function prism(pts, z0, z1, top, side, opt = {}) {
      const n = pts.length, cx = pts.reduce((a, p) => a + p[0], 0) / n, cy = pts.reduce((a, p) => a + p[1], 0) / n, parent = opt.parent || svg;
      for (let i = 0; i < n; i++) {
        const a = pts[i], b = pts[(i + 1) % n]; let nx = b[1] - a[1], ny = -(b[0] - a[0]);
        if (nx * ((a[0] + b[0]) / 2 - cx) + ny * ((a[1] + b[1]) / 2 - cy) < 0) { nx = -nx; ny = -ny; }
        const d = nx * sa + ny * ca;
        if (d > 0.001) poly([P3(a, z0), P3(b, z0), P3(b, z1), P3(a, z1)], opt.shade ? opt.shade(d) : side, { stroke: opt.stroke || "none" }, parent);
      }
      poly(pts.map((p) => P3(p, z1)), top, { stroke: opt.topStroke || "none", "stroke-width": opt.sw || 1.5 }, parent);
    }
    const zone = (f, wg) => f.rooms.filter((r) => (r.wing || "left") === wg);
    const dirL = [-Math.cos(ANG), Math.sin(ANG)], dirR = [Math.cos(ANG), Math.sin(ANG)], nrmL = [Math.sin(ANG), Math.cos(ANG)], nrmR = [-Math.sin(ANG), Math.cos(ANG)];
    const wingOf = (side, len) => { const J = side === "L" ? [-MID / 2, 0] : [MID / 2, 0], dir = side === "L" ? dirL : dirR, nr = side === "L" ? nrmL : nrmR;
      const at = (u, v) => [J[0] + dir[0] * u + nr[0] * v, J[1] + dir[1] * u + nr[1] * v]; return { at, quad: [at(0, 0), at(len, 0), at(len, D), at(0, D)] }; };
    const wingLen = (list) => Math.max(1, Math.ceil(list.length / 2)) * CW;
    const maxWl = Math.max(1, ...floors.map((f) => Math.max(wingLen(zone(f, "left")), wingLen(zone(f, "right")))));
    const hits = [];
    const wordWrap = (txt) => { const ws = txt.split(" "); if (ws.length <= 2) return [txt]; const k = Math.ceil(ws.length / 2); return [ws.slice(0, k).join(" "), ws.slice(k).join(" ")]; };
    floors.forEach((f, idx) => {
      ZO = idx * GAP;
      const left = zone(f, "left"), right = zone(f, "right"), cen = zone(f, "center"), wl = wingLen(left), wr = wingLen(right);
      const WL = wingOf("L", wl), WR = wingOf("R", wr), mid = [[-MID / 2, 0], [MID / 2, 0], [MID / 2 + D * nrmR[0], D * nrmR[1]], [-MID / 2 + D * nrmL[0], D * nrmL[1]]];
      const g = sv("g", { class: "bld3-floor" });
      const slab = (pts) => prism(pts, -T, 0, "#cfe5fa", "#92bfec", { shade: (d) => (d > 0.7 ? "#9cc8f0" : "#8fbbe8"), parent: g });
      slab(WL.quad); slab(WR.quad); slab(mid);
      const wall = (a, b) => poly([P3(a, 0), P3(b, 0), P3(b, WH), P3(a, WH)], "rgba(214,233,252,.78)", { stroke: "#a9cdf0" }, g);
      const bl = WL.at(0, 0), bl2 = WL.at(wl, 0), br = WR.at(0, 0), br2 = WR.at(wr, 0), back = [[bl2, bl], [bl, br], [br, br2]];
      back.forEach(([a, b]) => wall(a, b)); wall(WL.at(wl, 0), WL.at(wl, D)); wall(WR.at(wr, 0), WR.at(wr, D));
      back.forEach(([a, b]) => { const nx = -(b[1] - a[1]), ny = b[0] - a[0], l = Math.hypot(nx, ny), o = [WT * nx / l, WT * ny / l];
        poly([P3(a, WH), P3(b, WH), P3([b[0] + o[0], b[1] + o[1]], WH), P3([a[0] + o[0], a[1] + o[1]], WH)], "#5c97dc", {}, g); });
      [[WL, wl], [WR, wr]].forEach(([W, len]) => poly([W.at(0, 16 + CH), W.at(len, 16 + CH), W.at(len, 16 + CH + COR), W.at(0, 16 + CH + COR)].map((p) => P3(p, 0.5)), "rgba(255,255,255,.55)", {}, g));
      const rooms = [];
      const place = (W, list, side, len) => { const half = Math.ceil(list.length / 2);
        list.forEach((r, k) => { const row = k < half ? 0 : 1, col = row === 0 ? k : k - half, u0 = side === "L" ? len - (col + 1) * CW : col * CW, v0 = row === 0 ? 22 : 16 + CH + COR + 6;
          rooms.push({ r, pts: [W.at(u0 + 8, v0), W.at(u0 + CW - 8, v0), W.at(u0 + CW - 8, v0 + CH - 12), W.at(u0 + 8, v0 + CH - 12)], h: RH }); }); };
      place(WL, left, "L", wl); place(WR, right, "R", wr);
      const cp = (s_, t_) => { const Lx = -MID / 2 + t_ * D * nrmL[0], Ly = t_ * D * nrmL[1], Rx = MID / 2 + t_ * D * nrmR[0], Ry = t_ * D * nrmR[1]; return [Lx + s_ * (Rx - Lx), Ly + s_ * (Ry - Ly)]; };
      cen.forEach((r, k) => { const n = cen.length, a = k / n + 0.06, b = (k + 1) / n - 0.06; rooms.push({ r, pts: [cp(a, 0.1), cp(b, 0.1), cp(b, 0.9), cp(a, 0.9)], h: RH + 10 }); });
      if (!cen.length) { const c = proj(0, D / 2, 0); sv("text", { x: c[0], y: c[1], "text-anchor": "middle", fill: "#7d9cc4", "font-size": 20 }, g).textContent = t("mp_lobby"); }
      rooms.sort((a, b) => a.pts.reduce((s_, p) => s_ + depth(p[0], p[1]), 0) - b.pts.reduce((s_, p) => s_ + depth(p[0], p[1]), 0));
      rooms.forEach(({ r, pts, h: rh }) => {
        const [top, side] = KC[r.kind] || KC.other, isSel = r.id === memo.sel, isHit = matches(r);
        const rg = sv("g", { class: `bld3-room${isSel ? " sel" : ""}${isHit ? " hit" : ""}`, tabindex: 0, role: "button", "aria-label": mapName(r.name) }, g);
        prism(pts, 0, rh, top, side, { topStroke: isSel ? "#e8590c" : isHit ? "#e8a317" : "#fff", sw: isSel || isHit ? 4 : 2.5, parent: rg });
        const c = pts.reduce((a, p) => [a[0] + p[0] / 4, a[1] + p[1] / 4], [0, 0]), q = P3(c, rh);
        const tx = sv("text", { x: q[0], y: q[1] + 5, "text-anchor": "middle", fill: "#173a73", "font-weight": 700, "font-size": 16, "pointer-events": "none" }, rg);
        const lines = wordWrap(mapName(r.name));
        if (lines.length > 1) lines.forEach((ln, i) => { const ts = sv("tspan", { x: q[0], dy: i ? 17 : -6 }, tx); ts.textContent = ln; }); else tx.textContent = lines[0];
        const pick = () => { if (svg._dragged) return; memo.sel = r.id; memo.floor = f.id; draw(); };
        rg.addEventListener("click", pick); rg.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
      });
      const c = proj(-(maxWl * Math.cos(ANG) + MID / 2) - 40, D / 2 + maxWl * Math.sin(ANG) / 2, 0);
      const chip = sv("g", { class: "bld3-chip" }, g), nm = mapName(f.name), w = 70 + nm.length * 12, x0 = c[0] - w;
      sv("rect", { x: x0, y: c[1] - 24, width: w, height: 48, rx: 24, fill: f.id === memo.floor ? "#cfe3f8" : "#e1effc" }, chip);
      sv("circle", { cx: x0 + 24, cy: c[1], r: 20, fill: "#1d6fc4" }, chip);
      sv("text", { x: x0 + 24, y: c[1] + 8, "text-anchor": "middle", fill: "#fff", "font-size": 22, "font-weight": 700 }, chip).textContent = String(idx);
      sv("text", { x: x0 + 54, y: c[1] + 7, fill: "#173a73", "font-size": 20, "font-weight": 700 }, chip).textContent = nm;
    });
    const bb = svg.getBBox(), m = 18;
    svg.setAttribute("viewBox", `${bb.x - m} ${bb.y - m} ${bb.width + 2 * m} ${bb.height + 2 * m}`);
    svg.style.width = `${zoom * 100}%`;
    if (!floors.length) svg.replaceChildren();
  }
  svg.addEventListener("pointerdown", (e) => {
    svg._dragged = false; const x0 = e.clientX, y0 = e.clientY, az0 = view.az, t0 = view.tilt;
    const mv = (ev) => {
      const dx = ev.clientX - x0, dy = ev.clientY - y0;
      if (Math.abs(dx) + Math.abs(dy) > 6) svg._dragged = true;
      if (svg._dragged) { view.az = Math.max(-40, Math.min(40, az0 + dx * 0.2)); view.tilt = Math.max(35, Math.min(75, t0 - dy * 0.2)); drawBuilding(); }
    };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); setTimeout(() => { svg._dragged = false; }, 0); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  const setZoom = (z) => { zoom = Math.max(1, Math.min(2.6, z)); drawBuilding(); };
  wrap3.addEventListener("wheel", (e) => { if (!e.ctrlKey) return; e.preventDefault(); setZoom(zoom * (e.deltaY < 0 ? 1.1 : 0.9)); }, { passive: false });
  const viewBtns = h("div", { class: "row small", style: { marginTop: ".5rem" } },
    h("button", { class: "btn small", onClick: () => { Object.assign(view, VIEW0); zoom = 1; drawBuilding(); } }, t("mp_view_reset")),
    h("button", { class: "btn small", onClick: () => { Object.assign(view, { az: 0, tilt: 70 }); drawBuilding(); } }, t("mp_view_top")),
    h("button", { class: "btn small", onClick: () => { Object.assign(view, { az: 0, tilt: 36 }); drawBuilding(); } }, t("mp_view_front")),
    h("button", { class: "btn small icon", "aria-label": "+", onClick: () => setZoom(zoom * 1.2) }, "+"),
    h("button", { class: "btn small icon", "aria-label": "-", onClick: () => setZoom(zoom / 1.2) }, "−"));
  const label = (k) => t(`mp_k_${k}`);
  const sibs = (f, r) => f.rooms.filter((x) => (x.wing || "left") === (r.wing || "left"));
  function nudge(f, r, dir) {
    const list = sibs(f, r), i = list.indexOf(r), o = list[i + dir];
    if (!o) return;
    const a = f.rooms.indexOf(r), b = f.rooms.indexOf(o); [f.rooms[a], f.rooms[b]] = [f.rooms[b], f.rooms[a]];
    save(); draw();
  }
  function drawSide() {
    const f = curFloor(), r = findRoom();
    if (edit) {
      const bar = [];
      if (f) bar.push(h("label", { class: "field" }, h("span", { class: "label" }, t("mp_floor_name")), h("input", { type: "text", value: f.name, onInput: (e) => { f.name = e.target.value.slice(0, 40); save(); drawTabs(); drawBuilding(); } })),
        h("p", { class: "muted small" }, t("mp_add_to")),
        h("div", { class: "row" }, ["left", "center", "right"].map((wg) => h("button", { class: "btn small primary", onClick: () => { const n = { id: rnd(), name: t("mp_new_room"), kind: wg === "center" ? "admin" : "class", x: 0, y: 0, w: 4, h: 3, room_id: "", notes: "", person: "", phone: "", wing: wg }; f.rooms.push(n); memo.sel = n.id; save(); draw(); } }, icon("plus"), t(`mp_wing_${wg}`)))),
        h("div", { class: "row" }, h("button", { class: "btn ghost", onClick: async () => { if (!(await confirmBox(t("mp_del_floor_confirm")))) return; floors.splice(floors.indexOf(f), 1); memo.floor = floors[0]?.id || ""; memo.sel = ""; save(); draw(); } }, icon("trash"), t("mp_del_floor"))));
      else bar.push(h("p", { class: "muted" }, t("mp_need_floor")));
      if (r) {
        const set = (k) => (e) => { r[k] = e.target.value; save(); if (k === "name") drawBuilding(); };
        const kind = h("select", { onChange: (e) => { r.kind = e.target.value; save(); drawBuilding(); } }, map.kinds.map((k) => h("option", { value: k }, label(k)))); kind.value = r.kind;
        const wing = h("select", { onChange: (e) => { r.wing = e.target.value; save(); draw(); } }, (map.wings || ["left", "center", "right"]).map((k) => h("option", { value: k }, t(`mp_wing_${k}`)))); wing.value = r.wing || "left";
        const link = h("select", { onChange: (e) => { r.room_id = e.target.value; save(); } }, h("option", { value: "" }, "—"), structure.rooms.map((x) => h("option", { value: x.id }, roomLabel(x, structure)))); link.value = r.room_id;
        bar.push(h("hr"), h("label", { class: "field" }, h("span", { class: "label" }, t("mp_name")), h("input", { type: "text", value: r.name, onInput: set("name") })),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_kind")), kind),
          h("label", { class: "field" }, h("span", { class: "label" }, t("mp_wing")), wing),
          h("div", { class: "row" }, h("button", { class: "btn small", onClick: () => nudge(f, r, -1) }, t("mp_move_prev")), h("button", { class: "btn small", onClick: () => nudge(f, r, 1) }, t("mp_move_next"))),
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
    tabs.hidden = !edit;
    if (edit) drawTabs();
    drawBuilding();
    drawSide();
  }

  const legend = h("div", { class: "map-legend" }, map.kinds.map((k) => h("span", {}, h("i", { class: `k-${k}` }), label(k))));
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_map")), h("p", {}, t("mp_lead"))), h("div", { class: "row" }, search, editBtn)),
    tabs, h("div", { class: "map-wrap" }, h("div", {}, wrap3, viewBtns, legend), side)));
  draw();
}
