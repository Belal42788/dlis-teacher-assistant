"""Talks to AI services. Two dialects cover almost everything: OpenAI-compatible and Anthropic.

Uses only the standard library (plus certifi's certificates when installed).
"""
from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.request

from .errors import AppError

TIMEOUT = 90


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _http(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = TIMEOUT) -> dict:
    """The one place that touches the network (tests replace it). Some school networks re-sign secure traffic with their
    own certificate, which only the computer's own certificate store knows: if our bundle refuses, try the system's once."""
    try:
        return _http_once(method, url, headers, body, timeout, _ssl_context())
    except AppError as e:
        if e.code != "ai_ssl":
            raise
    return _http_once(method, url, headers, body, timeout, ssl.create_default_context())


def _http_once(method: str, url: str, headers: dict, body: dict | None, timeout: int, ctx: ssl.SSLContext) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "DLIS-Teacher-Assistant", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            raw = json.loads(e.read().decode("utf-8", "replace"))
            err = raw.get("error", raw) if isinstance(raw, dict) else raw
            detail = (err.get("message") if isinstance(err, dict) else str(err)) or ""
        except Exception:
            pass
        raise _map_status(e.code, detail) from e
    except TimeoutError as e:
        raise AppError("ai_timeout", "The AI service took too long to answer.", status=504) from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            raise AppError("ai_ssl", "This network does not allow a secure connection to the AI service (a school firewall?).", status=502) from e
        if isinstance(e.reason, TimeoutError):
            raise AppError("ai_timeout", "The AI service took too long to answer.", status=504) from e
        raise AppError("ai_offline", "Could not reach the AI service. Check the internet connection (or that Ollama is running).", status=502) from e
    except (OSError, http.client.HTTPException) as e:  # connection dropped half-way
        raise AppError("ai_offline", "The connection to the AI service was cut. Try again.", status=502) from e
    except ValueError as e:
        raise AppError("ai_server", "The AI service sent an answer the app could not read.", status=502) from e


def _map_status(code: int, detail: str) -> AppError:
    d = (detail or "")[:300]
    if code in (401, 403):
        return AppError("ai_bad_key", f"The key was refused. {d}".strip(), status=502)
    if code == 404:
        return AppError("ai_bad_model", f"Model or address not found. {d}".strip(), status=502)
    if code == 429:
        return AppError("ai_rate_limit", f"Too many requests or the free limit is used up. {d}".strip(), status=502)
    if 400 <= code < 500:
        return AppError("ai_bad_request", f"The AI service did not accept the request. {d}".strip(), status=502)
    return AppError("ai_server", f"The AI service has a problem right now. {d}".strip(), status=502)


def _base(cfg: dict) -> str:
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise AppError("ai_bad_url", "The service address must start with http:// or https://", status=400)
    return base


def _headers(cfg: dict) -> dict:
    key = cfg.get("api_key") or ""
    if cfg.get("type") == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _with_images(cfg: dict, text: str, images: list[bytes]) -> list:
    import base64
    enc = [base64.b64encode(i).decode() for i in images]
    if cfg.get("type") == "anthropic":
        return [*({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": e}} for e in enc), {"type": "text", "text": text}]
    return [{"type": "text", "text": text}, *({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{e}"}} for e in enc)]


def chat(cfg: dict, system: str, user: str, max_tokens: int = 3000, temperature: float = 0.4, messages: list | None = None,
         images: list[bytes] | None = None) -> str:
    """cfg: type, base_url, api_key, model. `messages` (role/content list) replaces `user` for a conversation.
    `images` (JPEG bytes) are attached to the user message, for models that can see."""
    convo = messages or [{"role": "user", "content": _with_images(cfg, user, images) if images else user}]
    if not cfg.get("model"):
        raise AppError("ai_no_model", "Choose a model first.", status=400)
    base = _base(cfg)
    if cfg["type"] == "anthropic":
        out = _http("POST", f"{base}/v1/messages", _headers(cfg), {
            "model": cfg["model"], "max_tokens": max_tokens, "temperature": temperature, "system": system,
            "messages": convo})
        text = "".join(p.get("text", "") for p in out.get("content", []) if isinstance(p, dict))
    else:
        out = _http("POST", f"{base}/chat/completions", _headers(cfg), {
            "model": cfg["model"], "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "system", "content": system}, *convo]})
        try:
            text = out["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
    if not text.strip():
        raise AppError("ai_empty", "The AI service sent an empty answer. Try again.", status=502)
    return text.strip()


def list_models(cfg: dict) -> list[str]:
    base = _base(cfg)
    if cfg["type"] == "anthropic":
        out = _http("GET", f"{base}/v1/models", _headers(cfg))
    else:
        out = _http("GET", f"{base}/models", _headers(cfg))
    items = out.get("data") or out.get("models") or []
    ids = []
    for m in items:
        mid = m.get("id") or m.get("name") if isinstance(m, dict) else str(m)
        if mid:
            ids.append(str(mid).removeprefix("models/"))
    return sorted(set(ids))
