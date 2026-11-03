import { h, icon, toast } from "../dom.js";
import { api, guarded } from "../api.js";
import { t } from "../i18n.js";
import { roomLabel } from "../labels.js";
import { hubTabs } from "../components/hubtabs.js";

// The week plan parents see: homework, extra links and quiz alerts. Nothing shows to parents until the teacher presses Publish.
export async function renderParentWeek(root) {
  const [structure, today, cloud] = await Promise.all([api.get("/api/structure"), api.get("/api/today"), api.get("/api/cloud")]);
  const pos = today.position || {};
  const staff = cloud.signed_in && (cloud.role === "teacher" || cloud.role === "admin");
  if (pos.state !== "in_term" || !structure.rooms.length) {
    root.replaceChildren(h("div", { class: "page" }, hubTabs("parents", "parentweek"), h("div", { class: "banner info" }, icon("info"), h("div", {}, t("pw_need")))));
    return;
  }
  let room = structure.rooms[0].id, tri = pos.trimester, week = pos.week;
  const sel = h("select", { onChange: (e) => { room = e.target.value; load(); } }, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
  const wk = h("input", { type: "number", min: 1, max: 30, value: week, style: { width: "5em" }, onChange: (e) => { week = +e.target.value || 1; load(); } });
  const body = h("div", {});
  const asLines = (a) => a.join("\n");
  async function load() {
    const d = await guarded(() => api.get(`/api/parent-week?room=${room}&tri=${tri}&week=${week}`)); if (!d) return;
    const hw = h("textarea", { rows: 4, placeholder: t("pw_hw_ph") }, asLines(d.homework));
    const mat = h("textarea", { rows: 4, dir: "ltr", placeholder: "Video: fractions | https://youtu.be/..." }, d.material.map((m) => `${m.title} | ${m.url}`).join("\n"));
    const qz = h("textarea", { rows: 3, placeholder: t("pw_quiz_ph") }, d.quiz_alerts.map((a) => (a.date ? `${a.title} | ${a.date}` : a.title)).join("\n"));
    const payload = () => ({ room_id: room, trimester: tri, week, homework: hw.value, material: mat.value, quiz_alerts: qz.value });
    // a ready message for the parents' WhatsApp group, built from what is on the screen (never contains student names)
    const message = (lang) => {
      const L = { ar: { hi: "السلام عليكم ورحمة الله، أولياء الأمور الكرام 🌷", wk: "ملخص الأسبوع", did: "📚 اللي اتشرح:", hw: "📝 الواجب:", mat: "🔗 مصادر مساعدة:", qz: "⏰ اختبارات قادمة:", end: "شكرًا لتعاونكم." },
                  en: { hi: "Dear parents,", wk: "Week summary", did: "📚 This week we learned:", hw: "📝 Homework:", mat: "🔗 Helpful links:", qz: "⏰ Upcoming quizzes:", end: "Thank you for your support." } }[lang];
      const lines = (v) => v.split("\n").map((x) => x.trim()).filter(Boolean);
      const block = (title, items) => (items.length ? [title, ...items.map((x) => "• " + x), ""] : []);
      return [L.hi, `${L.wk} ${week}`, "", ...block(L.did, d.topics), ...block(L.hw, lines(hw.value)), ...block(L.mat, lines(mat.value).map((x) => { const [a, ...b] = x.split("|"); return b.length ? `${a.trim()}: ${b.join("|").trim()}` : x; })),
        ...block(L.qz, lines(qz.value).map((x) => x.replace(/\s*\|\s*/, " – "))), L.end].join("\n").trim();
    };
    const copy = (lang) => guarded(async () => { await navigator.clipboard.writeText(message(lang)); toast(t("pw_copied")); });
    body.replaceChildren(
      d.topics.length ? h("div", { class: "banner info" }, icon("info"), h("div", {}, h("b", {}, t("pw_taught")), " ", d.topics.join(" · "))) : null,
      h("div", { class: "panel" },
        h("label", { class: "field" }, h("span", { class: "label" }, t("pw_hw")), hw),
        h("label", { class: "field" }, h("span", { class: "label" }, t("pw_mat")), mat),
        h("label", { class: "field" }, h("span", { class: "label" }, t("pw_quiz")), qz),
        h("div", { class: "row" },
          h("button", { class: "btn", onClick: () => guarded(async () => { await api.put("/api/parent-week", payload()); toast(t("saved")); await load(); }) }, t("save")),
          staff ? h("button", { class: "btn primary", onClick: () => guarded(async () => { await api.post("/api/parent-week/publish", payload()); toast(t("pw_published")); await load(); }) }, icon("send"), t("pw_publish")) : h("span", { class: "muted small" }, t("an_not_connected")),
          staff && d.approved ? h("button", { class: "btn ghost", onClick: () => guarded(async () => { await api.post("/api/parent-week/unpublish", payload()); await load(); }) }, t("pb_unapprove")) : null,
          d.approved ? h("span", { class: "chip on small" }, t("pb_live")) : null),
        h("div", { class: "row", style: { marginTop: ".6rem" } }, h("span", { class: "muted small" }, t("pw_msg")),
          h("button", { class: "btn small", onClick: () => copy("ar") }, icon("copy"), "عربي"), h("button", { class: "btn small", onClick: () => copy("en") }, icon("copy"), "English"))));
  }
  root.replaceChildren(h("div", { class: "page" }, hubTabs("parents", "parentweek"),
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, t("nav_parentweek")), h("p", {}, t("pw_lead")))),
    h("div", { class: "panel" }, h("div", { class: "grid2" }, h("label", { class: "field" }, h("span", { class: "label" }, t("d_class")), sel), h("label", { class: "field" }, h("span", { class: "label" }, t("week")), wk))), body));
  await load();
}
