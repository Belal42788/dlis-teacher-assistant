import { h, icon, confirmBox, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { hubTabs } from "../components/hubtabs.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { roomLabel, fmtDate, todayIso } from "../labels.js";
import { dateField } from "../components/date3.js";

// What the teacher shares with parents: nothing shows up for them until the teacher approves it. A quiz needs a "show from" date (after it ends).
export async function renderPublish(root) {
  const KINDS = ["presentation", "quiz", "revision", "link", "other"];
  const structure = await api.get("/api/structure");
  async function load() {
    const d = await api.get("/api/publications");
    const kids = [hubTabs("library", "publish"), h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_publish")), h("p", {}, t("pb_lead"))))];
    if (!d.connected) {
      kids.push(h("div", { class: "panel" }, h("p", {}, d.problem === "cloud_offline" ? t("an_offline") : t("an_not_connected")), h("a", { class: "btn", href: "#/settings" }, icon("settings"), t("nav_settings"))));
    } else if (d.role !== "admin" && d.role !== "teacher") {
      kids.push(h("div", { class: "panel" }, h("p", {}, t("cl_role_none"))));
    } else {
      const room = h("select", {}, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
      const kind = h("select", {}, KINDS.map((k) => h("option", { value: k }, t(`pb_k_${k}`))));
      const title = h("input", { type: "text", maxlength: 120, placeholder: t("pb_title") });
      const link = h("input", { type: "url", dir: "ltr", placeholder: "https://…" });
      const file = h("input", { type: "file" });
      const from = dateField({ label: t("pb_from") }), until = dateField({ label: t("pb_until") });
      const hint = h("p", { class: "muted small" });
      const syncHint = () => { hint.textContent = kind.value === "quiz" ? t("pb_quiz_hint") : ""; };
      kind.addEventListener("change", syncHint); syncHint();
      kids.push(h("div", { class: "panel" }, h("h3", {}, t("pb_new")),
        h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("pb_class")), room), h("label", { class: "field" }, h("span", { class: "label" }, t("pb_kind")), kind)),
        h("label", { class: "field" }, h("span", { class: "label" }, t("pb_title")), title),
        h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("pb_file")), file), h("label", { class: "field" }, h("span", { class: "label" }, t("pb_link")), link)),
        h("div", { class: "grid2" }, h("div", { class: "field" }, h("span", { class: "label" }, t("pb_from")), from), h("div", { class: "field" }, h("span", { class: "label" }, t("pb_until")), until)),
        hint,
        h("button", { class: "btn primary", onClick: () => guarded(async () => {
          const f = file.files[0];
          await api.post("/api/publications", { class_id: room.value, kind: kind.value, title: title.value, url: link.value, visible_from: from.value, visible_until: until.value, file: f ? { filename: f.name, data_b64: await readFileB64(f) } : undefined });
          await load();
        }) }, icon("upload"), t("pb_add")), h("p", { class: "muted small" }, t("pb_after_add"))));
      const label = (id) => { const r = structure.rooms.find((x) => x.id === id); return r ? roomLabel(r, structure) : id; };
      const status = (p) => (!p.approved ? t("pb_wait") : p.visible_from && new Date(p.visible_from) > new Date() ? `${t("pb_will")} ${fmtDate(p.visible_from.slice(0, 10), { day: "numeric", month: "long" })}` : t("pb_live"));
      kids.push(h("h3", {}, t("pb_list")), d.items.length ? d.items.map((p) => h("div", { class: `pub-row ${p.approved ? "live" : "wait"}` },
        h("div", { class: "row", style: { justifyContent: "space-between" } }, h("b", {}, p.title), h("span", { class: "chip on small" }, t(`pb_k_${p.kind}`))),
        h("div", { class: "muted small" }, label(p.class_id), " · ", status(p)),
        p.url ? h("a", { href: p.url, target: "_blank", rel: "noopener", dir: "ltr", class: "small" }, p.url) : null,
        h("div", { class: "row" },
          h("button", { class: `btn small${p.approved ? "" : " primary"}`, onClick: () => guarded(async () => { await api.post(`/api/publications/${p.id}`, { approved: !p.approved }); await load(); }) }, icon("check"), p.approved ? t("pb_unapprove") : t("pb_approve")),
          h("button", { class: "btn small ghost", onClick: () => guarded(async () => { if (await confirmBox(t("pb_del_confirm"))) { await api.post(`/api/publications/${p.id}/delete`, {}); await load(); } }) }, icon("trash"), t("remove"))))) : h("p", { class: "muted" }, t("pb_none")));
    }
    root.replaceChildren(h("div", { class: "page" }, ...kids));
  }
  await load();
}
