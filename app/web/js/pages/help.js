import { h } from "../dom.js";
import { t, getLang } from "../i18n.js";

// "**bold**" inside a help step becomes bold text
function rich(text) {
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? h("b", {}, part) : part));
}

export async function renderHelp(root) {
  let content = null;
  try { content = await (await fetch("/js/help_content.json")).json(); } catch { /* shown below */ }
  const sections = (content && (content[getLang()] || content.en)) || [];
  const want = new URLSearchParams((location.hash.split("?")[1]) || "").get("open");   // e.g. #/help?open=ai opens that section
  root.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_help")), h("p", {}, t("help_lead")))),
    sections.length ? sections.map((s, i) => h("details", { class: "panel help", open: want ? s.id === want : i === 0, id: `help-${s.id}` },
      h("summary", {}, s.title), h("ol", {}, s.steps.map((x) => h("li", {}, rich(x)))))) : h("div", { class: "banner warn" }, t("err_page"))));
  if (want) document.getElementById(`help-${want}`)?.scrollIntoView({ block: "start" });
}
