import { h, modal } from "../dom.js";
import { t } from "../i18n.js";
import { roomLabel, fmt12 } from "../labels.js";

// The two small dialogs of the Today page. `change(body)` is the page's own "save a one-day change" function.
const busyBy = (d, structure, p) => { const s = d.sessions.find((x) => x.period === p); const room = s && structure.rooms.find((r) => r.id === s.room_id); return room ? roomLabel(room, structure) : ""; };
const periodLabel = (p) => `${t("ch_period_n", { n: p.name })} · ${fmt12(p.start)}`;

export function coverDialog(d, structure, change) {
  const free = d.periods.filter((p) => !busyBy(d, structure, p.name));
  const period = h("select", {}, free.map((p) => h("option", { value: p.name }, periodLabel(p))));
  const room = h("select", {}, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const note = h("input", { type: "text", maxlength: 80, placeholder: t("ch_note") });
  modal({ title: t("ch_cover_title"), body: h("div", { class: "grid-gap" },
    h("p", { class: "muted small" }, t("ch_today_only")),
    h("label", { class: "field" }, h("span", { class: "label" }, t("ch_period")), period),
    h("label", { class: "field" }, h("span", { class: "label" }, t("ch_class")), room),
    h("label", { class: "field" }, h("span", { class: "label" }, t("ch_note")), note)),
    actions: [{ label: t("cancel") }, { label: t("ch_add"), kind: "primary", onClick: () => change({ action: "cover", period: period.value, room_id: room.value, note: note.value }) }] });
}

export function moveDialog(d, structure, s, change) {
  const others = d.periods.filter((p) => p.name !== s.period);
  const to = h("select", {}, others.map((p) => { const who = busyBy(d, structure, p.name);
    return h("option", { value: p.name }, `${periodLabel(p)} — ${who ? t("ch_swap_with", { what: who }) : t("ch_free")}`); }));
  modal({ title: t("ch_move_title"), body: h("div", { class: "grid-gap" }, h("p", { class: "muted small" }, t("ch_today_only")), to),
    actions: [{ label: t("cancel") }, { label: t("ch_move_do"), kind: "primary", onClick: () => change({ action: "move", period: s.period, to: to.value }) }] });
}
