"""Tiny client for the school's free Supabase server (sign in + read/write tables). Standard library only.
Passwords are never saved; only the refresh token is kept so the teacher stays signed in."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import AppError


def clean_url(u: str) -> str:
    u = (u or "").strip().rstrip("/")
    if u and not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", u):
        raise AppError("cloud_bad_url", "The server address should look like https://xxxx.supabase.co", status=400)
    return u


class Cloud:
    def __init__(self, url: str, anon_key: str, refresh_token: str = "", timeout: int = 20):
        self.url, self.key, self.refresh, self.timeout = clean_url(url), (anon_key or "").strip(), refresh_token, timeout
        self.access, self.access_until, self.user = "", 0.0, {}

    def _call(self, method: str, path: str, body=None, token: str = "", extra: dict | None = None):
        if not self.url or not self.key:
            raise AppError("cloud_not_set", "The server address and key are not set yet.", status=400)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", f"Bearer {token or self.key}")
        req.add_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                j = json.loads(e.read() or b"{}")
                msg = str(j.get("msg") or j.get("message") or j.get("error_description") or j.get("error") or "")
            except Exception:
                pass
            if e.code in (400, 401, 403) and "/auth/" in path:
                raise AppError("cloud_bad_login", "The email or password is not right.", status=401)
            raise AppError("cloud_error", f"The server said no ({e.code}). {msg}".strip(), status=502)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AppError("cloud_offline", "Could not reach the server. Check the internet and the server address.", status=502)
        return json.loads(raw) if raw else None

    def _take(self, j: dict) -> None:
        self.access = j.get("access_token", "")
        self.access_until = time.time() + int(j.get("expires_in") or 3000) - 60
        self.refresh = j.get("refresh_token", self.refresh)
        self.user = j.get("user") or self.user

    def sign_in(self, email: str, password: str) -> dict:
        self._take(self._call("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": password}))
        return self.user

    def _token(self) -> str:
        if self.access and time.time() < self.access_until:
            return self.access
        if not self.refresh:
            raise AppError("cloud_signed_out", "Sign in to the school server first.", status=401)
        self._take(self._call("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.refresh}))
        return self.access

    def role(self) -> str:
        rows = self.select("profiles", "select=role,full_name&limit=1")
        return rows[0]["role"] if rows else "none"

    def select(self, table: str, query: str = "select=*") -> list:
        return self._call("GET", f"/rest/v1/{table}?{query}", token=self._token()) or []

    def upsert(self, table: str, rows: list, on_conflict: str = "") -> list:
        q = f"?on_conflict={urllib.parse.quote(on_conflict)}" if on_conflict else ""
        return self._call("POST", f"/rest/v1/{table}{q}", rows, token=self._token(),
                          extra={"Prefer": "resolution=merge-duplicates,return=representation"}) or []

    def delete(self, table: str, query: str) -> None:
        self._call("DELETE", f"/rest/v1/{table}?{query}", token=self._token())
