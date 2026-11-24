"use strict";
// What the portal reads from the school server, with a short cache so switching tabs does not ask again.
import { api, me, NetErr } from "./core.js";

export const S = { role: "", kids: [], cur: 0, unread: 0, flash: "" };
export const kid = () => S.kids[S.cur];
export const kidName = (k) => (k && (k.display_name || k.code)) || "";
const q = encodeURIComponent;

const cache = new Map();
export const forget = () => cache.clear();
async function cached(key, make, ms = 45000) {
  const hit = cache.get(key); if (hit && Date.now() - hit.at < ms) return hit.v;
  const v = await make(); cache.set(key, { at: Date.now(), v }); return v;
}

export async function loadAccount() {
  const prof = await api("GET", "/rest/v1/profiles?select=role&limit=1");
  S.role = (prof[0] && prof[0].role) || "parent";
  if (S.role !== "parent" && S.role !== "student") return;
  const links = await api("GET", S.role === "student" ? "/rest/v1/student_accounts?select=student_code" : "/rest/v1/parent_students?select=student_code");
  S.kids = links.length ? await api("GET", "/rest/v1/students?select=code,class_id,grade_id,display_name&code=in.(" + links.map((l) => q(l.student_code)).join(",") + ")") : [];
  S.cur = Math.min(S.cur, Math.max(0, S.kids.length - 1));
}

const cls = (k) => q(k.class_id);
export const pubs = (k) => cached("pubs" + k.code, () => api("GET", `/rest/v1/publications?select=id,kind,title,url,file_path,created_at,note,trimester,week,body&class_id=eq.${cls(k)}&order=created_at.desc&limit=300`));
export const plans = (k) => cached("plans" + k.code, () => api("GET", `/rest/v1/week_plans?select=trimester,week,subject,homework,material,quiz_alerts&class_id=eq.${cls(k)}&order=trimester.desc,week.desc&limit=120`));
export const grades = (k) => cached("grades" + k.code, () => api("GET", `/rest/v1/grades?select=trimester,week,subject,item,score,max_score&student_code=eq.${q(k.code)}&order=trimester,subject,week.desc,item&limit=1000`));
export const news = () => cached("news", () => api("GET", "/rest/v1/announcements?select=title,body,starts_on,image_path&order=starts_on.desc,created_at.desc&limit=40"));
export const teachers = (k) => cached("teachers" + k.code, async () => {
  const rows = await api("GET", `/rest/v1/teacher_classes?select=teacher_id,subject,teacher_name&class_id=eq.${cls(k)}`);
  const by = new Map();
  rows.forEach((r) => { const x = by.get(r.teacher_id) || by.set(r.teacher_id, { id: r.teacher_id, name: "", subjects: [] }).get(r.teacher_id); if (r.teacher_name) x.name = r.teacher_name; if (r.subject && !x.subjects.includes(r.subject)) x.subjects.push(r.subject); });
  return [...by.values()].sort((a, b) => a.name.localeCompare(b.name));
}, 120000);

// the weeks that have anything in them: key "term|week" -> { tri, wk, files, plans }, newest first
export function weekIndex(files, planRows) {
  const m = new Map();
  const slot = (tri, wk) => { const key = `${tri}|${wk}`; return m.get(key) || m.set(key, { key, tri, wk, files: [], plans: [] }).get(key); };
  files.filter((p) => p.week).forEach((p) => slot(p.trimester ?? 0, p.week).files.push(p));
  planRows.forEach((p) => slot(p.trimester, p.week).plans.push(p));
  return [...m.values()].sort((a, b) => b.tri - a.tri || b.wk - a.wk);
}

// ---------------------------------------------------------------- conversations
export const MY_KIND = () => (S.role === "student" ? "student_teacher" : "parent_teacher");
export async function threadsFor(k) {
  const threads = await api("GET", `/rest/v1/threads?select=id,kind,teacher_id,last_at&student_code=eq.${q(k.code)}&order=last_at.desc`);
  const out = { threads, last: {}, unread: {}, count: 0 };
  if (!threads.length) return out;
  const ids = threads.map((x) => x.id).join(",");
  const [reads, msgs] = await Promise.all([
    api("GET", `/rest/v1/thread_reads?select=thread_id,read_at&thread_id=in.(${ids})`),
    api("GET", `/rest/v1/messages?select=id,thread_id,sender_id,sender_role,sender_name,body,created_at&thread_id=in.(${ids})&order=created_at.desc&limit=80`)]);
  const read = Object.fromEntries(reads.map((r) => [r.thread_id, r.read_at]));
  msgs.forEach((m) => { if (!out.last[m.thread_id]) out.last[m.thread_id] = m; });
  threads.forEach((th) => { const m = out.last[th.id]; out.unread[th.id] = !!m && m.sender_id !== me().uid && (!read[th.id] || new Date(read[th.id]) < new Date(m.created_at)); if (out.unread[th.id]) out.count++; });
  return out;
}
export async function refreshUnread() {
  if (!S.kids.length) { S.unread = 0; return 0; }
  try { let n = 0; for (const k of S.kids) n += (await threadsFor(k)).count; S.unread = n; } catch (e) { if (!(e instanceof NetErr)) throw e; }
  return S.unread;
}
export const markRead = (threadId) => api("POST", "/rest/v1/thread_reads?on_conflict=thread_id,user_id", { thread_id: threadId, read_at: new Date().toISOString() }, { Prefer: "resolution=merge-duplicates,return=minimal" });
