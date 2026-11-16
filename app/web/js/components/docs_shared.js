import { play } from "../motion.js";
import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";

// What the parts of the "Create files" page share: the AI helper button, the "file made" banner and the small helpers around them.
export function docsShared(ai) {
  const aiNeeded = () => ai.ready ? null : h("div", { class: "banner" }, icon("info"), h("div", { class: "small" }, h("a", { href: "#/settings" }, t("ai_setup_link"))));
  const aiButton = (label, run) => {
    const b = h("button", { class: "btn", disabled: !ai.ready, onClick: async () => {
      b.disabled = true; b.classList.add("working"); const old = b.lastChild.textContent; const t0 = Date.now();
      const clock = () => { b.lastChild.textContent = `${t("ai_writing")} ${Math.round((Date.now() - t0) / 1000)} ${t("sec_short")}`; }; clock();
      const timer = setInterval(clock, 1000);   // the real time so far: the AI usually needs half a minute or so
      try { const ok = await guarded(run); if (ok !== undefined) toast(t("ai_filled")); } finally { clearInterval(timer); b.disabled = false; b.classList.remove("working"); b.lastChild.textContent = old; }
    } }, icon("spark"), label);
    return b;
  };
  const sid = (p) => (p ? p.value() : "");
  const result = h("div", {});
  function showResult(r, extra) {
    const banner = h("div", { class: "banner ok" }, icon("check"),
      h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel), extra || null),
      h("div", { class: "row" },
        h("button", { class: "btn small primary", onClick: () => open(r.path, false) }, icon("file"), t("d_open_file")),
        h("button", { class: "btn small", onClick: () => open(r.path, true) }, icon("folder"), t("d_open_folder")),
        /grading|lesson_plan|trimester_plan|Certificates_|Cards_|\.txt$/i.test(r.name) ? null : h("a", { class: "btn small", href: `#/library?share=${encodeURIComponent(r.rel.replace(/\\/g, "/"))}` }, icon("send"), t("lb_share"))));
    result.replaceChildren(banner);
    play(banner, "fresh", 700);   // the finished file drops in, so it is noticed
    result.scrollIntoView({ block: "nearest" });
  }
  const open = (path, folder) => guarded(() => api.post("/api/open", { path, folder }));
  const run = async (btn, fn) => { btn.disabled = true; btn.classList.add("working"); try { return await guarded(fn); } finally { btn.disabled = false; btn.classList.remove("working"); } };
  return { aiNeeded, aiButton, sid, open, run, result, showResult };
}
