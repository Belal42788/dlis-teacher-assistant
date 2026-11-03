"""Picture makers for slides. Cloudflare Workers AI (FLUX) has a free daily allowance and needs no card."""
from __future__ import annotations

import base64

from . import ai_client
from .errors import AppError

CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def cloudflare_image(account_id: str, token: str, prompt: str, steps: int = 4) -> bytes:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODEL}"
    out = ai_client._http("POST", url, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, {"prompt": prompt[:2000], "steps": steps})
    try:
        b64 = (out.get("result") or {}).get("image") or out.get("image") or ""
        raw = base64.b64decode(b64)
    except (ValueError, AttributeError) as e:
        raise AppError("img_bad", "The picture service sent something the app could not read.", status=502) from e
    if len(raw) < 200:
        errs = out.get("errors") if isinstance(out, dict) else None
        raise AppError("img_bad", f"The picture service did not send a picture. {errs or ''}"[:300], status=502)
    return raw


# ---- other picture makers (each returns the picture's bytes). Names shown to the teacher live in IMAGE_PROVIDERS.
IMAGE_PROVIDERS = [
    {"id": "pollinations", "needs": "", "label": "Pollinations (FLUX) — free, no account", "real": False},
    {"id": "huggingface", "needs": "token", "label": "Hugging Face (FLUX.1) — free token", "real": False},
    {"id": "gemini", "needs": "ai_key", "label": "Google Gemini image — uses your Gemini key", "real": False},
    {"id": "wikimedia", "needs": "", "label": "Real pictures from Wikimedia Commons — free", "real": True},
    {"id": "cloudflare", "needs": "cloudflare", "label": "Cloudflare (FLUX schnell) — free account", "real": False},
]


def pollinations_image(prompt: str, width: int = 1280, height: int = 896) -> bytes:
    import random
    import urllib.parse
    q = urllib.parse.quote(prompt[:900], safe="")
    url = f"https://image.pollinations.ai/prompt/{q}?width={width}&height={height}&model=flux&nologo=true&enhance=true&seed={random.randint(1, 999999)}"
    raw = ai_client.http_bytes("GET", url, timeout=150)
    return _check_picture(raw)


def huggingface_image(token: str, prompt: str, model: str = "black-forest-labs/FLUX.1-schnell") -> bytes:
    raw = ai_client.http_bytes("POST", f"https://router.huggingface.co/hf-inference/models/{model}",
                               {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "image/jpeg"}, {"inputs": prompt[:1500]}, timeout=150)
    return _check_picture(raw)


def gemini_image(api_key: str, prompt: str, model: str = "gemini-2.5-flash-image") -> bytes:
    out = ai_client._http("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                          {"Content-Type": "application/json"},
                          {"contents": [{"parts": [{"text": prompt[:1500]}]}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}, timeout=150)
    for cand in (out.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return _check_picture(base64.b64decode(data))
    raise AppError("img_bad", "Gemini did not send a picture (the free plan may not include picture making).", status=502)


def wikimedia_image(query: str) -> bytes:
    """A real picture or diagram from Wikimedia Commons that matches the words."""
    import json
    import re
    import urllib.parse
    words = re.sub(r"[^\w\s-]", " ", query).split()
    stop = {"a", "an", "the", "of", "on", "in", "with", "and", "to", "for", "clear", "simple", "illustration", "picture", "image", "showing", "that", "explains"}
    q = " ".join([w for w in words if w.lower() not in stop][:6]) or query[:60]
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit=12"
           f"&gsrsearch={urllib.parse.quote('filetype:bitmap ' + q)}&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=1280")
    data = json.loads(ai_client.http_bytes("GET", url, timeout=40).decode("utf-8", "replace") or "{}")
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") in ("image/jpeg", "image/png") and (info.get("width") or 0) >= 500 and info.get("thumburl"):
            try:
                return _check_picture(ai_client.http_bytes("GET", info["thumburl"], timeout=60))
            except AppError:
                continue
    raise AppError("img_none", "No real picture was found for these words. Try other words.", status=404)


def _check_picture(raw: bytes) -> bytes:
    if len(raw) < 1000 or not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:4] == b"RIFF"):
        raise AppError("img_bad", "The picture service did not send a picture. Try again in a moment.", status=502)
    return raw
