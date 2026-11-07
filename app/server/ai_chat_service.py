"""AI chat and editable prompts.

* The teacher can change the wording (role + guidance) of every helper; the output format stays fixed in code,
  because the app depends on it.
* Chat history lives on the screen only; every message is cleaned of student names before it leaves.
"""
from __future__ import annotations

import json

from ..core import paths
from ..core.errors import AppError
from .ai_service import redact

EDITABLE = ("lesson", "quiz", "trimester", "slides", "revision", "chat")
MAX_MSGS, MAX_CHARS = 20, 6000


# What the app always adds itself (the teacher sees it, but it stays fixed so the files keep working).
FIXED_PARTS = {
    "lesson": ["Answer with ONE JSON object only, no other text.", "The JSON keys are fixed (topic, objectives, one key per teaching day, activities, resources, differentiation, assessment...) because they fill the Word template.",
               "Only the days this class really has a lesson are asked for.", "Student names are never sent; they are replaced before the request leaves the computer."],
    "quiz": ["Follow the requested format exactly: numbered questions, a), b), c) choices, 'term = match' lines, an 'Answer:' line.", "For every part you choose in the quiz page the app adds: the type, the number of questions, the number of choices and the topic.",
             "If you choose 'use the exact wording of the material', the app adds: use the material word for word and add no facts that are not in it.", "Student names are never sent."],
    "trimester": ["Answer with ONE JSON object only, no other text.", "The week list (with holidays marked as no classes) is added by the app.", "Student names are never sent."],
    "slides": ["Answer with ONE JSON object only, no other text.", "Each slide must have: title, bullets, an explanation paragraph, speaker notes and a picture idea.", "The number of slides and the words per slide for each stage come from the stage you pick.", "Student names are never sent."],
    "revision": ["Answer with ONE JSON object only, no other text: words (term + meaning), points, questions (q + a).", "When you use a slide file, the app adds: use ONLY what the source says.", "Student names are never sent."],
    "chat": ["Student names are removed from everything you write before it is sent.", "Only your last messages in the conversation are sent."],
}


def default_prompts() -> dict:
    return json.loads((paths.resources_dir() / "ai_prompts.json").read_text(encoding="utf-8"))


class AiChatMixin:
    def _prompts_path(self):
        return self._need_store().root / "ai_prompts.json"

    def _prompts_custom(self) -> dict:
        data = self._need_store().read_json(self._prompts_path(), {}) or {}
        return {k: v for k, v in data.items() if k in EDITABLE and isinstance(v, dict)}

    def prompt_text(self, key: str) -> tuple[str, str]:
        """(system, guidance) the teacher's version if they changed it, otherwise ours."""
        base = default_prompts()[key]
        mine = self._prompts_custom().get(key, {})
        system = str(mine.get("system") or base["system"]).strip()
        guidance = str(mine["guidance"] if "guidance" in mine else base.get("guidance", "")).strip()
        return system, guidance

    def ai_prompts_get(self) -> dict:
        d = default_prompts()
        custom = self._prompts_custom()
        return {"defaults": {k: d[k] for k in EDITABLE}, "custom": custom, "templates": d["templates"], "fixed": FIXED_PARTS}

    def ai_prompts_put(self, b: dict) -> dict:
        key = str(b.get("key", ""))
        if key not in EDITABLE:
            raise AppError("bad_request", "Unknown prompt.")
        data = self._need_store().read_json(self._prompts_path(), {}) or {}
        if b.get("reset"):
            data.pop(key, None)
        else:
            entry = {"system": str(b.get("system", ""))[:4000].strip()}
            if key != "chat":
                entry["guidance"] = str(b.get("guidance", ""))[:4000].strip()
            if not entry["system"]:
                raise AppError("bad_request", "The prompt cannot be empty.")
            data[key] = entry
        self._need_store().write_json(self._prompts_path(), data)
        return self.ai_prompts_get()

    # ------------------------------------------------------------ chat
    def ai_chat(self, b: dict) -> dict:
        raw = b.get("messages")
        if not isinstance(raw, list) or not raw:
            raise AppError("bad_request", "Write a message first.")
        msgs = []
        for m in raw[-MAX_MSGS:]:
            role = "assistant" if isinstance(m, dict) and m.get("role") == "assistant" else "user"
            text = str((m or {}).get("content", "")).strip()[:MAX_CHARS] if isinstance(m, dict) else ""
            if text:
                msgs.append({"role": role, "content": text})
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        if not msgs or msgs[-1]["role"] != "user":
            raise AppError("bad_request", "Write a message first.")
        s = self._need_store().load_settings()
        system, _ = self.prompt_text("chat")
        context = f"\n\nAbout this teacher: subject = {s.subject or 'not set'}."
        gid = str(b.get("grade_id", ""))
        if gid:
            grade = self._grade(gid)
            context += f" Grade being discussed = {self._grade_label(grade)}."
        context += self.source_block(b.get("source_id"), b.get("source_pages"), cite=True)
        names = self._all_student_names()
        cfg = self._ai_config()
        text, model = self._chat_auto(cfg, redact(system + context, names), "", messages=[{**m, "content": redact(m["content"], names)} for m in msgs],
                                      max_tokens=1800, temperature=0.6)
        return {"reply": text, "model": model}
