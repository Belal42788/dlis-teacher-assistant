import { h, icon } from "../dom.js";
import { api, guarded } from "../api.js";
import { logDialog, lastLine } from "../components/log_dialog.js";
import { forgetDay } from "../reminders.js";
import { t, getLang } from "../i18n.js";
import { state } from "../state.js";
import { tasksTable } from "../components/tasks_table.js";
import { fmtDate, roomLabel, todayIso, addDays, fmt12, stageTone } from "../labels.js";
import { menuItem, moreMenu } from "../components/lesson_menu.js";
import { coverDialog as openCover, moveDialog as openMove } from "../components/today_dialogs.js";
import { sideBoxes, weekBadge, notices, trackNow } from "../components/today_parts.js";

export async function renderToday(root) {
  let day = todayIso();
  let logInfo = { last: {}, today: [] };

  async function load() {
    const [d, structure, tasks, lastRes, dayLog] = await Promise.all([api.get(`/api/today?date=${day}`), api.get("/api/structure"), api.get("/api/tasks"),
      api.get("/api/log/last"), api.get(`/api/log?date=${day}`)]);
    logInfo = { last: lastRes.last, today: dayLog.entries };
    state.structure = structure;
    const isToday = day === todayIso();
    const { aiBox, prepBox, annBox } = sideBoxes(isToday);
    const pos = d.position;
    const nameNow = (getLang() === "ar" ? state.boot?.teacher_name_ar : state.boot?.teacher_name_en) || state.settings?.teacher_name;   // Arabic letters in the Arabic app
    const first = String(nameNow || "").trim().split(/\s+/)[0] || "";
    const nextBox = h("div", {});   // the next lesson with the time left (only today)
    root.replaceChildren(h("div", { class: "page wide" },
      h("div", { class: "today-head" },
        h("div", {}, h("h1", {}, isToday && first ? t("td_hello", { name: first }) : isToday ? t("today") : fmtDate(day)),
          h("div", { class: "muted today-sub" }, isToday ? [fmtDate(day, { weekday: "long", day: "numeric", month: "long" }), d.school_day ? ` · ${t("td_day_sum", { a: d.sessions.length, b: (d.duties || []).length })}` : ""] : [t("today_other_day"), " ", fmtDate(day)])),
        weekBadge(pos), h("span", { class: "grow" }),
        h("div", { class: "row" },
          h("button", { class: "btn small", "aria-label": t("previous_day"), onClick: () => { day = addDays(day, -1); load(); } }, icon("back"), t("previous_day")),
          isToday ? null : h("button", { class: "btn small", onClick: () => { day = todayIso(); load(); } }, t("back_to_today")),
          h("button", { class: "btn small", "aria-label": t("next_day"), onClick: () => { day = addDays(day, 1); load(); } }, t("next_day"), icon("chevron")))),
      notices(d, structure),
      h("div", { class: "today-cols" },
        h("div", { class: "today-main" }, nextBox, sessionsView(d, structure, isToday, nextBox)),
        h("div", { class: "today-side" }, aiBox, prepBox, isToday ? tasksSection(tasks) : null, annBox))));
  }

  function tasksSection(data) {
    return h("div", { class: "today-tasks" },
      h("h3", { class: "sec" }, icon("tasks"), t("nav_tasks"), data.overdue ? h("span", { class: "tag" }, t("tasks_late_n", { n: data.overdue })) : null),
      tasksTable(data, { limit: 3, onChange: () => load() }));
  }

  const logged = (s) => logInfo.today.find((e) => e.room_id === s.room_id && String(e.period) === String(s.period));
  const openLog = (s) => {
    const mine = logged(s);
    const prev = mine ? null : logInfo.last[s.room_id];
    logDialog({ room_id: s.room_id, date: day, period: s.period, entry: mine, last: prev || undefined, plan: s.plan, onSaved: () => load() });
  };

  const change = async (body) => { const r = await guarded(() => api.post("/api/today/change", body)); if (r) { forgetDay(); load(); } };

  const coverDialog = (d, structure) => openCover(d, structure, change);
  const moveDialog = (d, structure, s) => openMove(d, structure, s, change);

  const sessionLabel = (s, structure) => { const room = structure.rooms.find((r) => r.id === s.room_id); return room ? roomLabel(room, structure) : s.room_id; };

  const slot = (x) => {
    const until = x.live ? h("span", { class: "until" }) : null;   // "in 20 min" / "now" / "done": written by trackNow, shown inside the card
    return h("div", { class: "slot", style: { "--tone": x.tone || "var(--blue)" }, "data-s": x.live ? x.start : "", "data-e": x.live ? x.end || "" : "" },
      h("div", { class: "slot-time", dir: "ltr" }, x.start && x.start !== "99" ? [h("b", {}, fmt12(x.start)), x.end ? h("span", {}, fmt12(x.end)) : null] : null),
      x.node(until));
  };

  const nextBanner = (s, structure) => {
    const room = structure.rooms.find((r) => r.id === s.room_id);
    return h("div", { class: "nextbar" },
      h("div", { class: "nb-cd" }, h("b", { class: "nb-num" }, "—"), h("small", { class: "nb-unit" })),
      h("div", { class: "nb-txt" }, h("div", { class: "nb-lab" }),
        h("h2", {}, room ? roomLabel(room, structure) : s.room_id, " · ", t("ch_period_n", { n: s.period })),
        s.plan && s.plan.topic ? h("div", { class: "nb-plan" }, icon("file"), " ", s.plan.topic, s.plan.slides ? ` · ${t("tn_slides_n", { n: s.plan.slides })}` : "") : null),
      h("div", { class: "nb-btns" },
        h("button", { class: "btn small primary", onClick: () => openLog(s) }, icon("file"), logged(s) ? t("log_edit") : t("log_lesson")),
        h("a", { class: "btn small", href: `#/docs?room=${s.room_id}` }, icon("spark"), t("nav_docs"))));
  };

  const coverOut = h("div", {});
  function sessionsView(d, structure, isToday, nextBox) {
    const items = [
      ...d.sessions.map((s) => ({ start: s.start || "99", end: s.end, live: true, lesson: true, tone: stageTone(s.grade_id), label: sessionLabel(s, structure), banner: () => nextBanner(s, structure), node: (until) => {
        const room = structure.rooms.find((r) => r.id === s.room_id);
        const plan = s.plan && s.plan.topic ? h("span", { class: "plan-line small" }, icon("file"), " ", h("b", {}, s.plan.topic), s.plan.slides ? h("span", { class: "muted" }, ` · ${t("tn_slides_n", { n: s.plan.slides })}`) : null) : null;
        const last = lastLine(logInfo.last[s.room_id]);
        return h("div", { class: `lesson${s.extra ? " extra" : ""}` },
          h("div", { class: "no" }, s.period),
          h("div", { class: "what" },
            h("div", { class: "l1" }, h("b", {}, room ? roomLabel(room, structure) : s.room_id),
              s.kind ? h("span", { class: `kind ${s.kind}` }, t(`ch_kind_${s.kind}`)) : null,
              h("span", { class: "muted small meta" }, t("students_n", { n: room?.student_count ?? 0 })),
              s.note ? h("span", { class: "muted small" }, s.note) : null),
            plan || last ? h("div", { class: "l2" }, plan, last) : null),
          h("div", { class: "acts" }, until,
            h("button", { class: "btn small primary", onClick: () => openLog(s) }, icon("file"), logged(s) ? t("log_edit") : t("log_lesson")),
            moreMenu([menuItem(t("nav_docs"), null, { href: `#/docs?room=${s.room_id}`, icon: "file" }),
              isToday ? menuItem(t("ch_move"), () => moveDialog(d, structure, s), { icon: "timetable" }) : null,
              isToday ? menuItem(t("ch_cancel"), () => change({ action: "cancel", period: s.period }), { danger: true, icon: "trash" }) : null])));
      } })),
      ...(d.cancelled || []).map((s) => ({ start: s.start || "99", node: () => {
        const room = structure.rooms.find((r) => r.id === s.room_id);
        return h("div", { class: "lesson cancelled" },
          h("div", { class: "no" }, s.period),
          h("div", { class: "what" }, h("div", { class: "l1" }, h("b", {}, room ? roomLabel(room, structure) : s.room_id), h("span", { class: "kind cancelled" }, t("ch_cancelled")))),
          h("div", { class: "acts" }, h("button", { class: "btn small ghost", onClick: () => change({ action: "uncancel", period: s.period }) }, t("ch_undo"))));
      } })),
      ...(d.duties || []).map((u) => ({ start: u.start, end: u.end, live: true, tone: "var(--pencil)", label: t(`duty_${u.kind}`), node: (until) => h("div", { class: "lesson duty" },
        h("div", { class: "no" }, icon("clock")),
        h("div", { class: "what" }, h("div", { class: "l1" }, h("b", {}, t(`duty_${u.kind}`)))),
        h("div", { class: "acts" }, until, isToday ? h("button", { class: "btn small ghost", onClick: () => change({ action: "cancel_duty", kind: u.kind }) }, t("duty_cancel")) : null)) })),
      ...(d.cancelled_duties || []).map((u) => ({ start: u.start, node: () => h("div", { class: "lesson cancelled" },
        h("div", { class: "no" }, icon("clock")),
        h("div", { class: "what" }, h("div", { class: "l1" }, h("b", {}, t(`duty_${u.kind}`)), h("span", { class: "kind cancelled" }, t("duty_cancelled")))),
        h("div", { class: "acts" }, h("button", { class: "btn small ghost", onClick: () => change({ action: "restore_duty", kind: u.kind }) }, t("duty_restore")))) })),
    ].sort((a, b) => a.start.localeCompare(b.start));
    if (items.length) {
      return h("div", {},
        coverOut,
        isToday ? trackNow(items, nextBox) && null : null,
        h("div", { class: "ladder" }, items.map(slot)),
        isToday && d.school_day ? h("div", { class: "row ladder-foot" },
          h("button", { class: "btn small", onClick: () => coverDialog(d, structure) }, icon("plus"), t("ch_cover")),
          d.sessions.length ? h("button", { class: "btn small", onClick: async () => {
            const r = await guarded(() => api.post("/api/docs/cover-sheet", { date: day })); if (!r) return;
            coverOut.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel)),
              h("div", { class: "row" }, h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: false })) }, icon("file"), t("d_open_file")),
                h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: true })) }, icon("folder"), t("d_open_folder")))));
          } }, icon("file"), t("tn_cover_sheet")) : null,
          d.changed ? h("button", { class: "btn small ghost", onClick: () => change({ action: "restore" }) }, t("ch_restore")) : null) : null,
        h("p", { class: "muted small", style: { marginTop: ".5rem" } }, t("sessions_count", { n: d.sessions.length })));
    }
    const addCover = isToday && d.school_day ? h("div", { style: { marginBottom: ".6rem" } }, h("button", { class: "btn small", onClick: () => coverDialog(d, structure) }, icon("plus"), t("ch_cover"))) : null;
    const reason = d.holiday ? t("no_school_today") : d.weekend ? t("weekend_today") : !d.school_day ? t("outside_term") : t("no_sessions_today");
    return h("div", {}, addCover, h("div", { class: "paper empty" },
      h("h3", {}, reason),
      d.next_school_day ? h("p", { class: "muted" }, t("next_school_day", { date: fmtDate(d.next_school_day) })) : null,
      h("a", { class: "btn", href: "#/timetable" }, icon("timetable"), t("open_timetable"))));
  }

  await load();
}
