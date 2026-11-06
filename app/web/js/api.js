import { t, hasKey } from "./i18n.js";
import { toast } from "./dom.js";

const TOKEN = document.querySelector('meta[name="dlis-token"]').content;

export class ApiError extends Error {
  constructor(data, status) {
    super(data.message || data.error || "error");
    this.code = data.error || "error";
    this.details = data.details || {};
    this.status = status;
  }
  // Message in the user's language when we have one; otherwise the server's English text.
  get friendly() {
    const key = `err_${this.code}`;
    return hasKey(key) ? (this.code === "internal" && this.message ? `${t(key)} (${this.message})` : t(key)) : this.message;
  }
}

async function send(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { "X-DLIS-Token": TOKEN, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError({ error: "offline", message: "The app stopped. Close it and open it again." }, 0);
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new ApiError(data || { error: "internal" }, res.status);
  return data;
}

// Reading the same thing twice in a row is wasted time, and every tab click does that (menus, structure, settings...).
// Reads are kept for 30 seconds and thrown away the moment anything is saved; the same read asked for twice at once is
// sent once. Only things that change by themselves (alerts, running jobs, the file browser, one chat while it is answering)
// are never kept. A page's reads are also remembered, so pointing at its tab can fetch them before the click happens.
const NEVER = /^\/api\/(ping|bootstrap|reminders|background|alarms|status\/|fs\/|chats\/|sources\/)/;
const KEEP_MS = 30000;
const kept = new Map(), flying = new Map();
let gen = 0;
export function forgetReads() { gen++; kept.clear(); flying.clear(); }

let pageNow = "";
const pageReads = new Map();      // page id -> the reads that page made last time
export function readsFor(id) { return [...(pageReads.get(id) || [])]; }
export function inPage(id) { pageNow = id; pageReads.set(id, new Set(pageReads.get(id) || [])); }

function read(path) {
  if (pageNow && !NEVER.test(path)) pageReads.get(pageNow)?.add(path);
  const hit = kept.get(path);
  if (hit && Date.now() - hit.at < KEEP_MS) return Promise.resolve(structuredClone(hit.data));
  if (flying.has(path)) return flying.get(path).then((d) => structuredClone(d));
  const mine = gen;
  const p = send("GET", path).then((data) => {
    if (mine === gen && !NEVER.test(path)) kept.set(path, { at: Date.now(), data });
    return data;
  }).finally(() => { if (flying.get(path) === p) flying.delete(path); });
  flying.set(path, p);
  return p.then((d) => structuredClone(d));
}

// fetch ahead of time, quietly: a failure here must never show anything to the teacher
export function warm(paths) { for (const path of paths) if (!NEVER.test(path) && !kept.has(path) && !flying.has(path)) read(path).catch(() => {}); }

async function write(method, path, body) {
  forgetReads();
  try { return await send(method, path, body); } finally { forgetReads(); }
}

export const api = {
  get: (p) => read(p),
  put: (p, b) => write("PUT", p, b ?? {}),
  post: (p, b) => write("POST", p, b ?? {}),
  // a note to the server that changes nothing the screens show (page-use counter): must not empty the kept reads
  note: (p, b) => send("POST", p, b ?? {}),
};

// Run an action and show a friendly message when it fails.
export async function guarded(fn) {
  try { return await fn(); }
  catch (e) {
    if (e instanceof ApiError) toast(e.friendly, "error");
    else { console.error(e); toast(t("err_internal"), "error"); }
    return undefined;
  }
}
