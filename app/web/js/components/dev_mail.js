import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

// A problem report goes to the developer's own email: the mail program opens with the version and the system already written.
let boot = { version: "", platform: "", dev_email: "" };
export async function devEmail() {
  if (!boot.dev_email) { try { const b = await api.get("/api/bootstrap"); boot = { version: b.version, platform: b.platform, dev_email: b.dev_email }; } catch { /* the button then does nothing */ } }
  return boot.dev_email;
}

export async function mailDeveloper(note = "", page = "") {
  const to = await devEmail(); if (!to) return;
  const body = [note.trim().slice(0, 900), "", "—", `DLIS Teacher Assistant v${boot.version}`, `System: ${boot.platform}`, page ? `Page: ${page}` : ""].filter((x, i) => x || i === 1).join("\n");
  const url = `mailto:${to}?subject=${encodeURIComponent(`DLIS Teacher Assistant v${boot.version}`)}&body=${encodeURIComponent(body)}`.replace(/%0A/g, "%0D%0A");
  await guarded(() => api.post("/api/open-url", { url }));
}

// The box on the help page: the address (so it can be copied when no mail program is set up) and the two buttons.
export async function supportPanel() {
  const to = await devEmail();
  if (!to) return null;
  const copy = () => { navigator.clipboard?.writeText(to).then(() => toast(t("fb_copied")), () => {}); };
  return h("div", { class: "panel support" },
    h("div", { class: "support-ic" }, icon("mail")),
    h("div", { class: "grow" }, h("h2", {}, t("help_support")), h("p", { class: "muted" }, t("help_support_lead")), h("div", { class: "support-mail dir-ltr" }, to)),
    h("div", { class: "support-acts" },
      h("button", { class: "btn primary", onClick: () => mailDeveloper() }, icon("mail"), t("fb_mail")),
      h("button", { class: "btn", onClick: copy }, icon("copy"), t("fb_copy_mail"))));
}
