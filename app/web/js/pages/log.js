import { hubTabs } from "../components/hubtabs.js";
import { h, icon, confirmBox } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { roomLabel, fmtDate } from "../labels.js";
import { logDialog, lastLine } from "../components/log_dialog.js";

export async function renderLog(root) {
  const structure = await api.get("/api/structure");
  const q = new URLSearchParams((location.hash.split("?")[1]) || "");
  if (!structure.rooms.length) {
    root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "log"), h("div", { class: "banner warn" }, icon("warn"), h("div", {}, t("d_need_rooms"), " ", h("a", { href: "#/classes" }, t("nav_classes"))))));
    return;
  }
  // open on the class asked for, else the class logged most recently
  const lastAll = Object.values((await api.get("/api/log/last")).last).sort((a, b) => `${b.date}${b.created}`.localeCompare(`${a.date}${a.created}`));
  let room = (structure.rooms.find((r) => r.id === q.get("room")) || structure.rooms.find((r) => r.id === lastAll[0]?.room_id) || structure.rooms[0]).id;
  const sel = h("select", { "aria-label": t("d_class"), onChange: (e) => { room = e.target.value; draw(); } },
    structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  sel.value = room;
  const body = h("div", {});

  async function draw() {
    const { entries } = await guarded(() => api.get(`/api/log?room=${room}`)) || { entries: [] };
    body.replaceChildren(
      entries.length ? lastLine(entries[0]) : null,
      h("div", { class: "row", style: { margin: ".6rem 0" } },
        h("button", { class: "btn small", onClick: () => logDialog({ room_id: room, date: new Date().toISOString().slice(0, 10), period: "", last: entries[0], onSaved: draw }) }, icon("plus"), t("log_add"))),
      entries.length ? h("div", { class: "paper" }, h("table", { class: "tasks-table" },
        h("thead", {}, h("tr", {}, h("th", {}, t("log_date")), h("th", {}, t("log_topic")), h("th", {}, t("log_reached")), h("th", {}, t("log_note")), h("th", { class: "c-act" }, ""))),
        h("tbody", {}, entries.map((e) => h("tr", {},
          h("td", { style: { whiteSpace: "nowrap" } }, fmtDate(e.date, { day: "numeric", month: "short" })),
          h("td", {}, h("b", {}, e.topic || "—"), e.next_note ? h("div", { class: "small muted" }, `📌 ${e.next_note}`) : null),
          h("td", { dir: "ltr", style: { whiteSpace: "nowrap" } }, e.slide ? `${e.slide}${e.total ? " / " + e.total : ""}` : "—"),
          h("td", { class: "small" }, e.note || ""),
          h("td", { class: "c-act" },
            h("button", { class: "btn small ghost", onClick: () => logDialog({ room_id: room, date: e.date, period: e.period, entry: e, onSaved: draw }) }, t("edit")),
            h("button", { class: "btn icon ghost", "aria-label": t("remove"), onClick: async () => { if (await confirmBox(t("log_delete_confirm"), { okLabel: t("remove") })) { await guarded(() => api.post(`/api/log/${e.id}/delete`, {})); draw(); } } }, icon("trash")))))))) :
        h("div", { class: "paper empty" }, h("h3", {}, t("log_none"))));
  }
  root.replaceChildren(h("div", { class: "page" }, hubTabs("classes", "log"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_log")), h("p", {}, t("log_lead")))),
    h("div", { class: "panel" }, h("label", {}, h("span", { class: "label" }, t("d_class")), sel)), body));
  await draw();
}
