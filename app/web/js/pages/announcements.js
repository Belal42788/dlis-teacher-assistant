import { h, icon, confirmBox, readFileB64 } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { announceCard } from "../components/announce_list.js";
import { todayIso } from "../labels.js";
import { dateField } from "../components/date3.js";

// Announcements from the administration (principal, HR). Everyone signed in to the school server reads them; only admins write.
export async function renderAnnouncements(root) {
  let editing = null;
  async function load() {
    const d = await api.get("/api/announcements");
    const kids = [h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_announcements")), h("p", {}, t("an_lead"))))];
    if (!d.connected) {
      kids.push(h("div", { class: "panel" }, h("p", {}, d.problem === "cloud_offline" ? t("an_offline") : t("an_not_connected")), h("a", { class: "btn", href: "#/settings" }, icon("settings"), t("nav_settings"))));
    } else {
      if (d.role === "admin") {
        const title = h("input", { type: "text", maxlength: 120, placeholder: t("an_title") });
        const body = h("textarea", { rows: 4, maxlength: 2000, placeholder: t("an_body") });
        const aud = h("select", {}, ["staff", "parents", "all"].map((a) => h("option", { value: a }, t(`an_aud_${a}`))));
        const from = dateField({ value: todayIso(), label: t("an_from") }), to = dateField({ label: t("an_to") });
        const pic = h("input", { type: "file", accept: "image/*" });
        if (editing) { title.value = editing.title; body.value = editing.body || ""; aud.value = editing.audience; from.value = editing.starts_on || ""; to.value = editing.ends_on || ""; }
        const drop = h("input", { type: "checkbox" });
        kids.push(h("div", { class: "panel", id: "an-form" }, h("h3", {}, editing ? t("an_editing") : t("an_new")),
          h("label", { class: "field" }, h("span", { class: "label" }, t("an_title")), title),
          h("label", { class: "field" }, h("span", { class: "label" }, t("an_body")), body),
          h("div", { class: "grid2" },
            h("label", { class: "field" }, h("span", { class: "label" }, t("an_for")), aud),
            h("div", { class: "field" }, h("span", { class: "label" }, t("an_from")), from),
            h("div", { class: "field" }, h("span", { class: "label" }, t("an_to")), to)),
          h("label", { class: "field" }, h("span", { class: "label" }, t("an_pic")), pic),
          editing && editing.image_url ? h("label", { class: "row" }, drop, t("an_drop_pic")) : null,
          h("div", { class: "row" },
            h("button", { class: "btn primary", onClick: () => guarded(async () => {
              const f = pic.files[0], img = f ? { data_b64: await readFileB64(f) } : undefined;
              const data = { title: title.value, body: body.value, audience: aud.value, starts_on: from.value, ends_on: to.value, image: img };
              if (editing) await api.post(`/api/announcements/${editing.id}/update`, { ...data, remove_image: drop.checked });
              else await api.post("/api/announcements", data);
              editing = null; await load();
            }) }, icon(editing ? "check" : "send"), editing ? t("an_save") : t("an_post")),
            editing ? h("button", { class: "btn ghost", onClick: () => { editing = null; load(); } }, t("cancel")) : null)));
      }
      const del = d.role === "admin" ? (a) => guarded(async () => { if (await confirmBox(t("an_del_confirm"))) { await api.post(`/api/announcements/${a.id}/delete`, {}); await load(); } }) : null;
      const edit = d.role === "admin" ? (a) => { editing = a; load().then(() => document.getElementById("an-form")?.scrollIntoView({ block: "start" })); } : null;
      kids.push(d.items.length ? h("div", { class: "ann-list" }, d.items.map((a) => announceCard(a, del, edit))) : h("p", { class: "muted" }, t("an_none")));
    }
    root.replaceChildren(h("div", { class: "page" }, ...kids));
  }
  await load();
}
