"use strict";
// "New" marks: this device remembers when each section was last opened, and anything published after that is new.
// Nothing is stored on the school server; a different phone starts with the last 7 days as new.
import { me } from "./core.js";

const WEEK = 7 * 864e5;
const key = (code, kind) => `seen.${me().uid || "x"}.${code}.${kind}`;
const fallback = () => new Date(Date.now() - WEEK).toISOString();
export const lastSeen = (code, kind) => { try { return localStorage.getItem(key(code, kind)) || fallback(); } catch { return fallback(); } };
// opening a section: returns the time of the visit before this one, and remembers this visit
export function enter(code, kind) {
  const since = lastSeen(code, kind);
  try { localStorage.setItem(key(code, kind), new Date().toISOString()); } catch { /* private window: nothing remembered */ }
  return since;
}
export const isNew = (row, since) => !!row.created_at && new Date(row.created_at) > new Date(since);
