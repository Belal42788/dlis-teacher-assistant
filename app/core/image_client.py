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
