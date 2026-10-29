import { h, icon, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { logDialog, lastLine } from "../components/log_dialog.js";
import { forgetDay } from "../reminders.js";
import { t } from "../i18n.js";
import { state } from "../state.js";
import { tasksTable } from "../components/tasks_table.js";
import { fmtDate, fmtShort, fmtDay, roomLabel, gradeName, todayIso, addDays, triName, localName, fmt12, stageTone } from "../labels.js";

export async function renderToday(root) {
  let day = todayIso();
  let logInfo = { last: {}, today: [] };

  async function load() {
    const [d, structure, tasks, lastRes, dayLog] = await Promise.all([api.get(`/api/today?date=${day}`), api.get("/api/structure"), api.get("/api/tasks"),
      api.get("/api/log/last"), api.get(`/api/log?date=${day}`)]);
    logInfo = { last: lastRes.last, today: dayLog.entries };
    state.structure = structure;
    const isToday = day === todayIso();
    const pos = d.position;
    root.replaceChildren(h("div", { class: "page" },
      h("div", { class: "date-head" },
        h("h1", {}, isToday ? t("today") + " · " + fmtDate(day, { day: "numeric", month: "long" }) : fmtDate(day)),
        weekBadge(pos)),
      h("div", { class: "row", style: { marginBottom: "1.2rem" } },
        h("button", { class: "btn", "aria-label": t("previous_day"), onClick: () => { day = addDays(day, -1); load(); } }, icon("back"), t("previous_day")),
        isToday ? null : h("button", { class: "btn", onClick: () => { day = todayIso(); load(); } }, t("back_to_today")),
        h("button", { class: "btn", "aria-label": t("next_day"), onClick: () => { day = addDays(day, 1); load(); } }, t("next_day"), icon("chevron")),
        isToday ? null : h("span", { class: "muted" }, fmtDate(day))),
      notices(d, structure),
      sessionsView(d, structure, isToday),
      isToday ? tasksSection(tasks) : null));
  }

  function tasksSection(data) {
    return h("div", { class: "today-tasks" },
      h("h3", { class: "sec" }, icon("tasks"), t("nav_tasks"), data.overdue ? h("span", { class: "tag" }, t("tasks_late_n", { n: data.overdue })) : null),
      tasksTable(data, { limit: 6, onChange: () => load() }));
  }

  const logged = (s) => logInfo.today.find((e) => e.room_id === s.room_id && String(e.period) === String(s.period));
  const openLog = (s) => {
    const mine = logged(s);
    const prev = mine ? null : logInfo.last[s.room_id];
    logDialog({ room_id: s.room_id, date: day, period: s.period, entry: mine, last: prev || undefined, plan: s.plan, onSaved: () => load() });
  };

  const change = async (body) => { const r = await guarded(() => api.post("/api/today/change", body)); if (r) { forgetDay(); load(); } };

  const busyBy = (d, structure, p) => { const s = d.sessions.find((x) => x.period === p); const room = s && structure.rooms.find((r) => r.id === s.room_id); return room ? roomLabel(room, structure) : ""; };
  const periodLabel = (p) => `${t("ch_period_n", { n: p.name })} · ${fmt12(p.start)}`;

  function coverDialog(d, structure) {
    const free = d.periods.filter((p) => !busyBy(d, structure, p.name));
    const period = h("select", {}, free.map((p) => h("option", { value: p.name }, periodLabel(p))));
    const room = h("select", {}, structure.rooms.map((r) => h("option", { value: r.id }, roomLabel(r, structure))));
    const note = h("input", { type: "text", maxlength: 80, placeholder: t("ch_note") });
    modal({ title: t("ch_cover_title"), body: h("div", { class: "grid-gap" },
      h("p", { class: "muted small" }, t("ch_today_only")),
      h("label", { class: "field" }, h("span", { class: "label" }, t("ch_period")), period),
      h("label", { class: "field" }, h("span", { class: "label" }, t("ch_class")), room),
      h("label", { class: "field" }, h("span", { class: "label" }, t("ch_note")), note)),
      actions: [{ label: t("cancel") }, { label: t("ch_add"), kind: "primary", onClick: () => change({ action: "cover", period: period.value, room_id: room.value, note: note.value }) }] });
  }

  function moveDialog(d, structure, s) {
    const others = d.periods.filter((p) => p.name !== s.period);
    const to = h("select", {}, others.map((p) => { const who = busyBy(d, structure, p.name);
      return h("option", { value: p.name }, `${periodLabel(p)} — ${who ? t("ch_swap_with", { what: who }) : t("ch_free")}`); }));
    modal({ title: t("ch_move_title"), body: h("div", { class: "grid-gap" }, h("p", { class: "muted small" }, t("ch_today_only")), to),
      actions: [{ label: t("cancel") }, { label: t("ch_move_do"), kind: "primary", onClick: () => change({ action: "move", period: s.period, to: to.value }) }] });
  }

  function weekBadge(pos) {
    if (pos.state === "in_term") return h("span", { class: "week-badge" }, `${triName(pos.trimester_name)} · ${t("week_n", { n: pos.week })}`);
    if (pos.state === "no_calendar") return h("span", { class: "week-badge quiet" }, t("no_calendar_badge"));
    if (pos.state === "before_term" || pos.state === "between_terms")
      return h("span", { class: "week-badge quiet" }, t("next_term_starts", { name: triName(pos.next_name), date: fmtShort(pos.next_start) }));
    return h("span", { class: "week-badge quiet" }, t("year_finished"));
  }

  function notices(d, structure) {
    const out = [];
    if (d.holiday) out.push(h("div", { class: "banner holiday" }, icon("calendar"), h("div", {}, h("b", {}, localName(d.holiday.name) || t("holiday")), h("div", {}, d.holiday.end && d.holiday.end !== d.holiday.start ? `${fmtDay(d.holiday.start)} → ${fmtDay(d.holiday.end)}` : fmtDay(d.holiday.start)), h("div", {}, t("no_school_today")))));
    for (const e of d.events) out.push(h("div", { class: "banner warn" }, icon("info"), h("b", {}, e)));
    if (d.position.state === "no_calendar") out.push(h("div", { class: "banner warn" }, icon("warn"),
      h("div", {}, t("calendar_missing"), " ", h("a", { href: "#/calendar" }, t("set_calendar")))));
    if (!structure.rooms.length) out.push(h("div", { class: "banner warn" }, icon("warn"),
      h("div", {}, t("no_classes_yet"), " ", h("a", { href: "#/classes" }, t("add_classes")))));
    return out;
  }

  const timeCell = (start, end) => h("div", { class: "time", dir: "ltr" }, start ? [h("span", { class: "dir-ltr" }, fmt12(start)), end ? [" – ", h("span", { class: "dir-ltr" }, fmt12(end))] : null] : null);

  const sessionLabel = (s, structure) => { const room = structure.rooms.find((r) => r.id === s.room_id); return room ? roomLabel(room, structure) : s.room_id; };
  const mins = (hhmm) => { const m = /^(\d{1,2}):(\d{2})/.exec(hhmm || ""); return m ? +m[1] * 60 + +m[2] : null; };
  const nowMins = () => { const n = new Date(); return n.getHours() * 60 + n.getMinutes(); };

  // Marks the lesson that is running now and fades the ones that are over (re-checked every half minute while the page is open).
  function trackNow(items) {
    const live = items.filter((x) => x.live && mins(x.start) !== null && mins(x.end) !== null);
    const tick = () => {
      const rows = document.querySelectorAll(".slot[data-s]");
      if (!rows.length) { clearInterval(timer); return; }
      const n = nowMins();
      rows.forEach((el) => {
        const a = mins(el.dataset.s), b = mins(el.dataset.e);
        el.dataset.state = a === null || b === null ? "" : n >= b ? "past" : n >= a ? "now" : "";
      });
    };
    const timer = setInterval(tick, 30000);
    setTimeout(tick, 0);
    return live.length;
  }

  const slot = (x) => h("div", { class: "slot", style: { "--tone": x.tone || "var(--blue)" }, "data-s": x.live ? x.start : "", "data-e": x.live ? x.end || "" : "" },
    h("div", { class: "slot-time", dir: "ltr" }, x.start && x.start !== "99" ? [h("b", {}, fmt12(x.start)), x.end ? h("span", {}, fmt12(x.end)) : null] : null),
    x.node());

  const coverOut = h("div", {});
  function sessionsView(d, structure, isToday) {
    const items = [
      ...d.sessions.map((s) => ({ start: s.start || "99", end: s.end, live: true, tone: stageTone(s.grade_id), label: sessionLabel(s, structure), node: () => {
        const room = structure.rooms.find((r) => r.id === s.room_id);
        const grade = structure.grades.find((g) => g.id === s.grade_id);
        return h("div", { class: `lesson${s.extra ? " extra" : ""}` },
          h("div", { class: "no" }, s.period),
          h("div", { class: "what" }, h("b", {}, room ? roomLabel(room, structure) : s.room_id),
            s.kind ? h("span", { class: `kind ${s.kind}` }, t(`ch_kind_${s.kind}`)) : null,
            s.note ? h("span", { class: "muted small" }, ` ${s.note}`) : null,
            grade ? h("div", { class: "muted small" }, `${gradeName(grade)} · ${t("students_n", { n: room?.student_count ?? 0 })}`) : null,
            s.plan && s.plan.topic ? h("div", { class: "plan-line small" }, icon("file"), " ", t("tn_planned"), " ", h("b", {}, s.plan.topic), s.plan.slides ? h("span", { class: "muted" }, ` · ${t("tn_slides_n", { n: s.plan.slides })}`) : null) : null,
            lastLine(logInfo.last[s.room_id]),
            h("div", { class: "row small" },
              h("button", { class: "btn small ghost", onClick: () => openLog(s) }, icon("file"), logged(s) ? t("log_edit") : t("log_lesson")),
              h("a", { class: "btn small ghost go", href: `#/docs?room=${s.room_id}` }, icon("file"), t("nav_docs")),
              isToday ? h("button", { class: "btn small ghost", onClick: () => moveDialog(d, structure, s) }, t("ch_move")) : null,
              isToday ? h("button", { class: "btn small ghost", onClick: () => change({ action: "cancel", period: s.period }) }, t("ch_cancel")) : null)),
          timeCell(s.start, s.end));
      } })),
      ...(d.cancelled || []).map((s) => ({ start: s.start || "99", node: () => {
        const room = structure.rooms.find((r) => r.id === s.room_id);
        return h("div", { class: "lesson cancelled" },
          h("div", { class: "no" }, s.period),
          h("div", { class: "what" }, h("b", {}, room ? roomLabel(room, structure) : s.room_id), h("span", { class: "kind cancelled" }, t("ch_cancelled")),
            h("div", {}, h("button", { class: "btn small ghost", onClick: () => change({ action: "uncancel", period: s.period }) }, t("ch_undo")))),
          timeCell(s.start, s.end));
      } })),
      ...(d.duties || []).map((u) => ({ start: u.start, end: u.end, live: true, tone: "var(--pencil)", label: t(`duty_${u.kind}`), node: () => h("div", { class: "lesson duty" },
        h("div", { class: "no" }, icon("clock")),
        h("div", { class: "what" }, h("b", {}, t(`duty_${u.kind}`)),
          isToday ? h("div", {}, h("button", { class: "btn small ghost", onClick: () => change({ action: "cancel_duty", kind: u.kind }) }, t("duty_cancel"))) : null),
        timeCell(u.start, u.end)) })),
      ...(d.cancelled_duties || []).map((u) => ({ start: u.start, node: () => h("div", { class: "lesson cancelled" },
        h("div", { class: "no" }, icon("clock")),
        h("div", { class: "what" }, h("b", {}, t(`duty_${u.kind}`)), h("span", { class: "kind cancelled" }, t("duty_cancelled")),
          h("div", {}, h("button", { class: "btn small ghost", onClick: () => change({ action: "restore_duty", kind: u.kind }) }, t("duty_restore")))),
        timeCell(u.start, u.end)) })),
    ].sort((a, b) => a.start.localeCompare(b.start));
    if (items.length) {
      return h("div", {},
        coverOut,
        isToday && d.school_day ? h("div", { class: "row", style: { marginBottom: ".6rem" } },
          h("button", { class: "btn small", onClick: () => coverDialog(d, structure) }, icon("plus"), t("ch_cover")),
          d.sessions.length ? h("button", { class: "btn small", onClick: async () => {
            const r = await guarded(() => api.post("/api/docs/cover-sheet", { date: day })); if (!r) return;
            coverOut.replaceChildren(h("div", { class: "banner ok" }, icon("check"), h("div", { class: "grow" }, h("b", {}, t("d_created")), h("div", { class: "dir-ltr small" }, r.rel)),
              h("div", { class: "row" }, h("button", { class: "btn small primary", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: false })) }, icon("file"), t("d_open_file")),
                h("button", { class: "btn small", onClick: () => guarded(() => api.post("/api/open", { path: r.path, folder: true })) }, icon("folder"), t("d_open_folder")))));
          } }, icon("file"), t("tn_cover_sheet")) : null,
          d.changed ? h("button", { class: "btn small ghost", onClick: () => change({ action: "restore" }) }, t("ch_restore")) : null) : null,
        isToday ? trackNow(items) && null : null,
        h("div", { class: "ladder" }, items.map(slot)),
        h("p", { class: "muted small", style: { marginTop: ".8rem" } }, t("sessions_count", { n: d.sessions.length })));
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
