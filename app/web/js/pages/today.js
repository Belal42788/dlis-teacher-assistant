import { h, icon, modal } from "../dom.js";
import { api, guarded } from "../api.js";
import { logDialog, lastLine } from "../components/log_dialog.js";
import { forgetDay } from "../reminders.js";
import { t, getLang } from "../i18n.js";
import { state } from "../state.js";
import { announceCard } from "../components/announce_list.js";
import { tasksTable } from "../components/tasks_table.js";

const aiHint = { hidden: false };   // "not now" hides the AI hint until the program is opened again
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
    const annBox = h("div", {});
    const aiBox = h("div", {});     // shown at the start while the AI is not set up: a button that explains how to turn it on
    if (isToday && !aiHint.hidden) api.get("/api/ai").then((r) => {
      if (r.ready) return;
      aiBox.append(h("div", { class: "banner info", style: { marginBottom: ".8rem" } }, icon("spark"),
        h("div", { class: "grow" }, h("b", {}, t("aih_title")), h("div", { class: "small muted" }, t("aih_text"))),
        h("a", { class: "btn small primary", href: "#/help?open=ai" }, t("aih_how")),
        h("a", { class: "btn small", href: "#/settings" }, t("aih_settings")),
        h("button", { class: "btn small ghost", onClick: () => { aiHint.hidden = true; aiBox.replaceChildren(); } }, t("aih_later"))));
    }).catch(() => {});
    const prepBox = h("div", {});   // "prepare my week": how many classes already have their lesson plan
    if (isToday) api.get("/api/week-prep").then((r) => {
      if (!r.total) return;
      const done = r.ready >= r.total;
      prepBox.append(h("div", { class: `banner ${done ? "ok" : "info"}`, style: { marginBottom: ".8rem" } }, icon(done ? "check" : "file"),
        h("div", { class: "grow" }, h("b", {}, done ? t("pw_all_ready") : t("pw_status", { a: r.ready, b: r.total })), done ? null : h("div", { class: "small muted" }, (() => { const m = r.grades.filter((g) => !g.has_plan); return m.slice(0, 5).map((g) => g.name + (g.topic ? ` (${g.topic})` : "")).join(" · ") + (m.length > 5 ? ` +${m.length - 5}` : ""); })())),
        done ? null : h("a", { class: "btn small primary", href: "#/docs" }, icon("spark"), t("pw_go")))); }).catch(() => {});
    if (isToday) Promise.all([api.get("/api/announcements"), api.get("/api/cloud").catch(() => ({}))]).then(([a, c]) => {
      const live = (a.items || []).filter((x) => x.active).slice(0, 3), admin = c.role === "admin";
      if (live.length || admin) annBox.append(h("div", { class: "panel", style: { marginTop: ".9rem" } },
        h("div", { class: "row" }, h("h3", { style: { margin: 0 } }, t("an_today")), h("span", { class: "grow" }),
          admin ? h("a", { class: "btn small primary", href: "#/announcements" }, icon("plus"), t("an_add_short")) : null),
        ...live.map((x) => announceCard(x)))); }).catch(() => {});
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

  const fmtLeft = (m) => { m = Math.max(0, Math.ceil(m)); if (m < 60) return t("td_min", { n: m }); const hh = Math.floor(m / 60), mm = m % 60; return mm ? t("td_hm", { h: hh, m: mm }) : t("td_h", { h: hh }); };
  // Marks the lesson that is running now, fades the ones that are over, writes the time left on each row and keeps the "next lesson" bar current
  // (re-checked every 15 seconds while the page is open).
  function trackNow(items, nextBox) {
    const lessons = items.filter((x) => x.lesson && mins(x.start) !== null && mins(x.end) !== null);
    let shown = null;
    const tick = () => {
      const rows = document.querySelectorAll(".slot[data-s]");
      if (!rows.length) { clearInterval(timer); return; }
      const n = nowMins();
      rows.forEach((el) => {
        const a = mins(el.dataset.s), b = mins(el.dataset.e);
        const st = a === null || b === null ? "" : n >= b ? "past" : n >= a ? "now" : "";
        el.dataset.state = st;
        const u = el.querySelector(".until");
        if (u && a !== null) { u.textContent = st === "past" ? t("td_done") : st === "now" ? t("td_now") : t("td_in", { x: fmtLeft(a - n) }); u.className = "until" + (st === "past" ? " done" : st === "now" || a - n <= 15 ? " soon" : ""); }
      });
      if (!nextBox) return;
      const cur = lessons.find((x) => n < mins(x.end));
      if (!cur) { nextBox.replaceChildren(); shown = null; return; }
      if (cur !== shown) { shown = cur; nextBox.replaceChildren(cur.banner()); }
      const a = mins(cur.start), running = n >= a, left = running ? mins(cur.end) - n : a - n;
      const num = nextBox.querySelector(".nb-num"), unit = nextBox.querySelector(".nb-unit"), lab = nextBox.querySelector(".nb-lab");
      const big = Math.max(0, Math.ceil(left));
      if (num) { num.textContent = big < 60 ? String(big) : `${Math.floor(big / 60)}:${String(big % 60).padStart(2, "0")}`; unit.textContent = big < 60 ? t("td_unit_min") : t("td_unit_h"); }
      if (lab) lab.textContent = running ? t("td_left", { x: fmtLeft(left) }) : t("td_next_at", { time: fmt12(cur.start) });
      nextBox.firstChild?.classList.toggle("running", running);
    };
    const timer = setInterval(tick, 15000);
    setTimeout(tick, 0);
    return lessons.length;
  }

  const slot = (x) => h("div", { class: "slot", style: { "--tone": x.tone || "var(--blue)" }, "data-s": x.live ? x.start : "", "data-e": x.live ? x.end || "" : "" },
    h("div", { class: "slot-time", dir: "ltr" }, x.start && x.start !== "99" ? [h("b", {}, fmt12(x.start)), x.end ? h("span", {}, fmt12(x.end)) : null] : null, x.live ? h("span", { class: "until" }) : null),
    x.node());

  const nextBanner = (s, structure) => {
    const room = structure.rooms.find((r) => r.id === s.room_id);
    return h("div", { class: "nextbar" },
      h("div", { class: "nb-cd" }, h("b", { class: "nb-num" }, "—"), h("small", { class: "nb-unit" })),
      h("div", { class: "nb-txt" }, h("div", { class: "nb-lab" }),
        h("h2", {}, room ? roomLabel(room, structure) : s.room_id, " · ", t("ch_period_n", { n: s.period })),
        s.plan && s.plan.topic ? h("div", { class: "nb-plan" }, icon("file"), " ", s.plan.topic, s.plan.slides ? ` · ${t("tn_slides_n", { n: s.plan.slides })}` : "") : null),
      h("div", { class: "nb-btns" },
        h("button", { class: "btn primary", onClick: () => openLog(s) }, icon("file"), logged(s) ? t("log_edit") : t("log_lesson")),
        h("a", { class: "btn", href: `#/docs?room=${s.room_id}` }, icon("spark"), t("nav_docs"))));
  };

  const coverOut = h("div", {});
  function sessionsView(d, structure, isToday, nextBox) {
    const items = [
      ...d.sessions.map((s) => ({ start: s.start || "99", end: s.end, live: true, lesson: true, tone: stageTone(s.grade_id), label: sessionLabel(s, structure), banner: () => nextBanner(s, structure), node: () => {
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
              h("button", { class: "btn small primary", onClick: () => openLog(s) }, icon("file"), logged(s) ? t("log_edit") : t("log_lesson")),
              h("details", { class: "lesson-more" }, h("summary", { class: "btn small ghost", "aria-label": t("more") }, "⋯"),
                h("div", { class: "row small" },
                  h("a", { class: "btn small ghost go", href: `#/docs?room=${s.room_id}` }, icon("file"), t("nav_docs")),
                  isToday ? h("button", { class: "btn small ghost", onClick: () => moveDialog(d, structure, s) }, t("ch_move")) : null,
                  isToday ? h("button", { class: "btn small ghost", onClick: () => change({ action: "cancel", period: s.period }) }, t("ch_cancel")) : null)))),
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
        isToday ? trackNow(items, nextBox) && null : null,
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
