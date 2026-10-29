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

async function request(method, path, body) {
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

export const api = {
  get: (p) => request("GET", p),
  put: (p, b) => request("PUT", p, b ?? {}),
  post: (p, b) => request("POST", p, b ?? {}),
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
