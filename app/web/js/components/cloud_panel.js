import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

// Settings > School server: connect to the school's free Supabase server and sign in (the password is never saved).
export function cloudPanel() {
  const box = h("div", { class: "panel" });
  const out = h("p", { class: "small", style: { marginTop: ".6rem" } });
  const roleName = (r) => t(`cl_role_${r || "none"}`);
  async function draw() {
    const c = await api.get("/api/cloud");
    const url = h("input", { type: "text", dir: "ltr", value: c.url, placeholder: "https://xxxx.supabase.co" });
    const key = h("input", { type: "password", dir: "ltr", placeholder: c.key_set ? "••••••••" : "anon public key" });
    const email = h("input", { type: "email", dir: "ltr", value: c.email });
    const pass = h("input", { type: "password", dir: "ltr" });
    box.replaceChildren(h("h3", {}, t("cl_title")), h("p", { class: "muted" }, t("cl_lead")),
      h("label", { class: "field" }, h("span", { class: "label" }, t("cl_url")), url),
      h("label", { class: "field" }, h("span", { class: "label" }, t("cl_key")), key),
      h("div", { class: "row" }, h("button", { class: "btn", onClick: () => guarded(async () => { await api.put("/api/cloud", { url: url.value, key: key.value }); out.textContent = t("saved"); await draw(); }) }, icon("check"), t("save"))),
      h("hr"),
      c.signed_in
        ? h("div", {}, h("p", {}, icon("user"), " ", h("b", {}, c.email), " · ", roleName(c.role)),
            h("div", { class: "row" },
              h("button", { class: "btn", onClick: () => guarded(async () => { out.textContent = t("cl_testing"); const r = await api.post("/api/cloud/test", {}); out.textContent = `${t("cl_ok")} · ${roleName(r.role)}`; }) }, icon("check"), t("cl_test")),
              h("button", { class: "btn ghost", onClick: () => guarded(async () => { await api.post("/api/cloud/logout", {}); out.textContent = ""; await draw(); }) }, t("cl_logout"))))
        : h("div", {}, h("label", { class: "field" }, h("span", { class: "label" }, t("cl_email")), email), h("label", { class: "field" }, h("span", { class: "label" }, t("cl_pass")), pass),
            h("button", { class: "btn primary", disabled: !c.url || !c.key_set, onClick: () => guarded(async () => { out.textContent = t("cl_testing"); await api.post("/api/cloud/login", { email: email.value, password: pass.value }); out.textContent = ""; await draw(); }) }, t("cl_login")),
            !c.url || !c.key_set ? h("p", { class: "muted small" }, t("cl_need")) : null),
      out);
  }
  guarded(draw);
  return box;
}
