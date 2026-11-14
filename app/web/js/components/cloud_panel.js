import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { confirmBox } from "../dom.js";

// Settings > School server: connect to the school's free Supabase server and sign in (the password is never saved).
function codesBox() {
  const res = h("p", { class: "small" });
  return h("div", {}, h("hr"), h("h3", {}, t("cd_title")), h("p", { class: "muted" }, t("cd_lead")),
    h("button", { class: "btn primary", onClick: () => guarded(async () => {
      res.textContent = t("cl_testing");
      const r = await api.post("/api/codes/prepare", {});
      res.replaceChildren(`${t("cd_done", { n: r.new, total: r.total })} `, h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path })) }, icon("file"), t("cd_open")));
    }) }, icon("file"), t("cd_make")), res);
}

function backupBox() {
  const res = h("p", { class: "small" });
  return h("div", {}, h("hr"), h("h3", {}, t("bk_srv_title")), h("p", { class: "muted" }, t("bk_srv_lead")),
    h("button", { class: "btn", onClick: () => guarded(async () => {
      res.textContent = t("cl_testing");
      const r = await api.post("/api/cloud/backup", {});
      res.replaceChildren(`${t("bk_srv_done", { n: Object.values(r.counts).reduce((a, b) => a + b, 0) })} `, h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: true })) }, icon("folder"), t("d_open_folder")));
    }) }, icon("file"), t("bk_srv_make")), res);
}

export function cloudPanel() {
  const box = h("div", { class: "panel" });
  const out = h("p", { class: "small", style: { marginTop: ".6rem" } });
  const roleName = (r) => t(`cl_role_${r || "none"}`);
  // administration only: the server's address and key, and the school code that teachers type once
  function adminBox(c) {
    const url = h("input", { type: "url", dir: "ltr", value: c.url, placeholder: "https://xxxx.supabase.co", required: true, "data-label": t("cl_url") });
    const key = h("input", { type: "password", dir: "ltr", placeholder: c.key_set ? "••••••••" : "anon public key", "data-label": t("cl_key"), ...(c.key_set ? {} : { required: true }) });
    const school = h("input", { type: "text", value: c.school, placeholder: t("cl_school_ph") });
    const code = h("textarea", { rows: 3, readonly: true, dir: "ltr", class: "mono" });
    return h("details", { class: "fold", "data-form": "", open: false }, h("summary", {}, t("cl_admin")), h("p", { class: "muted small" }, t("cl_admin_lead")),
      h("label", { class: "field" }, h("span", { class: "label" }, t("cl_school")), school),
      h("label", { class: "field" }, h("span", { class: "label" }, t("cl_url")), url),
      h("label", { class: "field" }, h("span", { class: "label" }, t("cl_key")), key),
      h("div", { class: "row" },
        h("button", { class: "btn", "data-check": "", onClick: () => guarded(async () => { await api.put("/api/cloud", { url: url.value, key: key.value, school: school.value }); out.textContent = t("saved"); await draw(); }) }, icon("check"), t("save")),
        c.signed_in && c.role === "admin" ? h("button", { class: "btn primary", onClick: () => guarded(async () => { const r = await api.post("/api/cloud/code", {}); code.value = r.code; code.select(); }) }, icon("file"), t("cl_code_make")) : null),
      h("p", { class: "muted small" }, t("cl_code_hint")), code);
  }
  async function draw() {
    const c = await api.get("/api/cloud");
    const email = h("input", { type: "email", dir: "ltr", value: c.email, required: true, "data-label": t("cl_email") });
    const pass = h("input", { type: "password", dir: "ltr", required: true, "data-label": t("cl_pass") });
    const code = h("input", { type: "text", dir: "ltr", placeholder: "DLIS-…", required: true, "data-label": t("cl_code") });
    const admin = c.role === "admin";
    if (!c.configured) {
      box.replaceChildren(h("h3", {}, t("cl_title")), h("p", { class: "muted" }, t("cl_join_lead")),
        h("label", { class: "field" }, h("span", { class: "label" }, t("cl_code")), code),
        h("button", { class: "btn primary", onClick: () => guarded(async () => { await api.post("/api/cloud/join", { code: code.value }); out.textContent = ""; await draw(); }) }, icon("check"), t("cl_join")),
        h("hr"), adminBox(c), out);
      return;
    }
    box.replaceChildren(h("h3", {}, t("cl_title")), c.school ? h("p", {}, icon("user"), " ", h("b", {}, c.school)) : null,
      c.signed_in
        ? h("div", {}, h("p", {}, icon("user"), " ", h("b", {}, c.email), " · ", roleName(c.role)),
            h("div", { class: "row" },
              h("button", { class: "btn", onClick: () => guarded(async () => { out.textContent = t("cl_testing"); const r = await api.post("/api/cloud/test", {}); out.textContent = `${t("cl_ok")} · ${roleName(r.role)}`; }) }, icon("check"), t("cl_test")),
              h("button", { class: "btn ghost", onClick: () => guarded(async () => { await api.post("/api/cloud/logout", {}); out.textContent = ""; await draw(); }) }, t("cl_logout"))))
        : h("div", {}, h("label", { class: "field" }, h("span", { class: "label" }, t("cl_email")), email), h("label", { class: "field" }, h("span", { class: "label" }, t("cl_pass")), pass),
            h("div", { class: "row" },
              h("button", { class: "btn primary", onClick: () => guarded(async () => { out.textContent = t("cl_testing"); await api.post("/api/cloud/login", { email: email.value, password: pass.value }); out.textContent = ""; await draw(); }) }, t("cl_login")),
              h("button", { class: "btn ghost", onClick: () => guarded(async () => { if (await confirmBox(t("cl_forget_confirm"), { okLabel: t("cl_forget"), danger: true })) { await api.post("/api/cloud/forget", {}); await draw(); } }) }, t("cl_forget")))),
      admin ? h("div", {}, h("hr"), adminBox(c)) : null,
      admin ? codesBox() : null,
      admin ? backupBox() : null,
      out);
  }
  guarded(draw);
  return box;
}
