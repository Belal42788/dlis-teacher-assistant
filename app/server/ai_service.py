"""AI helpers: settings (kept on THIS computer only), a real connection test, and three writing helpers.

Privacy rules:
* API keys live in the app-support folder, never in the data folder (which may sync to the cloud),
  and are never sent back to the screen.
* Student names are replaced by "[student]" in every prompt before it leaves the computer.
"""
from __future__ import annotations

import json
import os
import re
import webbrowser
from typing import Optional

from ..core import ai_client
from ..core import documents as D
from ..core import paths
from ..core.errors import AppError
from ..core.names import english_name
from ..core.translit import to_english

DAY_KEYS = ["sunday", "monday", "tuesday", "wednesday", "thursday"]
LESSON_KEYS = ["topic", "objectives", *DAY_KEYS, "practice_pages", "activities", "resources", "differentiation", "assessment", "reflection"]


def registry() -> list[dict]:
    data = json.loads((paths.resources_dir() / "ai_providers.json").read_text(encoding="utf-8"))
    return data["providers"]


_SKIP = re.compile(r"embed|tts|whisper|audio|speech|transcri|image|imagen|dall|veo|video|realtime|rerank|moderat|guard|safeguard|vision-only|aqa|lyria|learnlm|computer-use|robotics|search-preview|diffusion|sdxl|stable-", re.I)
_GOOD = re.compile(r"flash|mini|small|haiku|instant|lite|nano|8b|20b|oss|turbo|free", re.I)
_BAD = re.compile(r"preview|exp|beta|thinking|deep|reason|latest-?experimental", re.I)
_BIG = re.compile(r"pro\b|opus|large|ultra|405b|120b|70b|maverick", re.I)


def rank_models(ids: list[str], provider_id: str = "") -> list[str]:
    """Keep the models that can write text, best first: fast and cheap ones lead (they suit free plans), newest first."""
    keep = [m for m in dict.fromkeys(ids) if not _SKIP.search(m)]
    if provider_id == "openrouter":
        free = [m for m in keep if m.endswith(":free") or m == "openrouter/free"]
        keep = free or keep

    def score(m: str):
        pts = (3 if _GOOD.search(m) else 0) - (2 if _BAD.search(m) else 0) - (1 if _BIG.search(m) else 0)
        if m == "openrouter/free":
            pts += 5
        return (-pts, m)

    ordered = sorted(keep, key=score)
    # within the same score, higher version numbers first (e.g. 2.5 before 2.0)
    def ver(m: str):
        nums = re.findall(r"\d+(?:\.\d+)?", m)
        return -float(nums[0]) if nums else 0.0
    return sorted(ordered, key=lambda m: (score(m)[0], ver(m)))


def redact(text: str, names: list[str]) -> str:
    """Replace every known student name. Longest first so 'Ali Omar Hassan' goes before 'Ali Omar'."""
    out = text
    for n in sorted({" ".join(n.split()) for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
        pattern = r"\s+".join(re.escape(p) for p in n.split())
        out = re.sub(pattern, "[student]", out, flags=re.I)
    return out


def _json_from(text: str) -> dict:
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text.strip(), flags=re.I)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
    try:
        data = json.loads(text[a:b + 1])
    except ValueError as e:
        raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502) from e
    return data if isinstance(data, dict) else {}


def _as_text(v) -> str:
    if isinstance(v, list):
        return "\n".join(f"- {_as_text(x)}" if not isinstance(x, (list, dict)) else _as_text(x) for x in v)
    if isinstance(v, dict):
        return "\n".join(f"{k}: {_as_text(x)}" for k, x in v.items())
    return "" if v is None else str(v).strip()


class AiMixin:
    # ------------------------------------------------------------ local settings
    def _ai_path(self):
        return paths.app_support_dir() / "ai.json"

    def _ai_data(self) -> dict:
        try:
            d = json.loads(self._ai_path().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _ai_write(self, d: dict) -> None:
        p = self._ai_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(p)

    @staticmethod
    def _provider(pid: str) -> dict:
        p = next((x for x in registry() if x["id"] == pid), None)
        if not p:
            raise AppError("ai_unknown_provider", "Unknown AI service.", status=404)
        return p

    def _ai_config(self, over: Optional[dict] = None) -> dict:
        """The settings to use now: saved ones, with anything typed on screen on top."""
        d, over = self._ai_data(), over or {}
        pid = over.get("provider") or d.get("provider") or ""
        if not pid:
            raise AppError("ai_not_set", "Choose an AI service in Settings first.", status=409)
        p = self._provider(pid)
        saved = (d.get("providers") or {}).get(pid, {})
        key = (over.get("api_key") or "").strip() or saved.get("api_key", "")
        model = (over.get("model") or "").strip() or saved.get("model") or ""
        base = (over.get("base_url") or "").strip() or saved.get("base_url") or p["base_url"]
        if p.get("needs_key") and not key:
            raise AppError("ai_no_key", "Paste your key first.", status=409)
        if not key.isascii():
            raise AppError("ai_bad_key", "The key has characters that are not allowed. Copy it again.", status=400)
        return {"provider": pid, "type": p["type"], "base_url": base, "api_key": key, "model": model}

    def ai_state(self) -> dict:
        d = self._ai_data()
        provs = []
        for p in registry():
            saved = (d.get("providers") or {}).get(p["id"], {})
            provs.append({**p, "has_key": bool(saved.get("api_key")), "saved_model": saved.get("model", ""),
                          "saved_base_url": saved.get("base_url", "")})
        pid = d.get("provider", "")
        ready = False
        if pid:
            try:
                self._ai_config()
                ready = True
            except AppError:
                ready = False
        return {"provider": pid, "ready": ready, "providers": provs}

    def ai_save(self, b: dict) -> dict:
        pid = str(b.get("provider", ""))
        p = self._provider(pid)
        d = self._ai_data()
        d.setdefault("providers", {})
        cur = d["providers"].setdefault(pid, {})
        key = b.get("api_key")
        if key == "__clear__":
            cur.pop("api_key", None)
        elif isinstance(key, str) and key.strip():
            if not key.strip().isascii():
                raise AppError("ai_bad_key", "The key has characters that are not allowed. Copy it again.")
            cur["api_key"] = key.strip()
        if str(b.get("model", "")).strip():
            cur["model"] = str(b["model"]).strip()
        if p.get("custom") and str(b.get("base_url", "")).strip():
            cur["base_url"] = str(b["base_url"]).strip()
        d["provider"] = pid
        self._ai_write(d)
        return self.ai_state()

    def ai_off(self) -> dict:
        d = self._ai_data()
        d["provider"] = ""
        self._ai_write(d)
        return self.ai_state()

    # ---- models come from the service itself, never from a list stored in the app
    _models_cache: dict = {}

    def _models_for(self, cfg: dict, force: bool = False) -> list[str]:
        import hashlib
        import time

        k = (cfg["provider"], cfg["base_url"], hashlib.sha1(cfg["api_key"].encode()).hexdigest())
        hit = self._models_cache.get(k)
        if hit and not force and time.time() - hit[0] < 600:
            return hit[1]
        ids = rank_models(ai_client.list_models(cfg), cfg["provider"])
        self._models_cache[k] = (time.time(), ids)
        return ids

    def _chat_auto(self, cfg: dict, system: str, user: str, **kw) -> tuple[str, str]:
        """Write with the model the teacher picked, or (automatic) the best working model the service offers now.
        Returns (text, model_used)."""
        if cfg.get("model"):
            return ai_client.chat(cfg, system, user, **kw), cfg["model"]
        last = None
        tried: list[str] = []
        for attempt in range(2):  # second round: ask the service again in case the list was stale
            try:
                ids = self._models_for(cfg, force=attempt == 1)
            except AppError as e:
                if e.code in ("ai_bad_key", "ai_offline", "ai_timeout", "ai_rate_limit"):
                    raise
                ids = []
            for m in [x for x in ids if x not in tried][:4]:
                tried.append(m)
                try:
                    return ai_client.chat({**cfg, "model": m}, system, user, **kw), m
                except AppError as e:
                    last = e
                    if e.code not in ("ai_bad_model", "ai_bad_request", "ai_empty", "ai_server", "ai_rate_limit"):
                        raise
        if last:
            raise last
        raise AppError("ai_no_model", "The service has no model this app can use. Choose one by hand.", status=409)

    def ai_test(self, b: dict) -> dict:
        cfg = self._ai_config(b)
        reply, model = self._chat_auto(cfg, "You are a connection test. Answer with one word.", "Say: ready", max_tokens=20, temperature=0)
        try:
            models = self._models_for(cfg)
        except AppError:
            models = []
        return {"ok": True, "model": model, "auto": not cfg.get("model"), "reply": reply[:60], "models": models}

    def ai_models(self, b: dict) -> dict:
        cfg = self._ai_config(b)
        models = self._models_for(cfg, force=True)
        return {"models": models, "recommended": models[0] if models else ""}

    def open_url(self, url: str) -> dict:
        allowed = {p["key_url"] for p in registry() if p.get("key_url")} | {"https://notebooklm.google.com/", "https://dash.cloudflare.com/profile/api-tokens", "https://dash.cloudflare.com/"}
        if url == getattr(self, "_update_url", None) and url.startswith("https://"):
            allowed.add(url)   # the page of the newer version, announced by the school's own update address
        mail = f"mailto:{paths.DEV_EMAIL}"
        if url == mail or (url.startswith(mail + "?") and "\n" not in url and len(url) < 1800):
            allowed.add(url)   # a problem report to the developer: the address is ours, the subject and text are the teacher's
        if url not in allowed:
            raise AppError("bad_url", "That address is not allowed.", status=403)
        if not os.environ.get("DLIS_NO_OPEN"):
            webbrowser.open(url)
        return {"ok": True}

    # ------------------------------------------------------------ safe sending
    def _all_student_names(self) -> list[str]:
        store = self._need_store()
        names: list[str] = []
        for r in store.load_structure().rooms:
            for x in store.load_students_full(r.id):
                names += [x["name"], x["english"], to_english(x["name"])]
        return [n for n in names if n]

    def _ask(self, system: str, user: str, **kw) -> str:
        """Every request goes through here, so names are always removed."""
        cfg = self._ai_config()
        names = self._all_student_names()
        text, self.last_model = self._chat_auto(cfg, redact(system, names), redact(user, names), **kw)
        return text

    def _system_for(self, key: str, fixed: str) -> str:
        """The teacher's (or our) wording, then the rules the app needs for its own output format."""
        system, guidance = self.prompt_text(key)
        return " ".join(x for x in (system, guidance, fixed) if x)

    def _ai_context(self, b: dict) -> dict:
        grade = self._grade(str(b.get("grade_id", "")))
        s = self._need_store().load_settings()
        sid, pages = b.get("source_id"), b.get("source_pages")
        if not sid:   # nothing picked by hand: use the source planned for this topic in the scheme of work
            sid, pages = self.scheme_source(grade.id, b.get("topic"))
        goals = self.scheme_objectives(grade.id, b.get("topic"))
        goal_text = ("\nCURRICULUM OBJECTIVES for this topic (cover them, do not go beyond them):\n" + goals) if goals else ""
        return {"grade": grade, "label": self._grade_label(grade), "subject": s.subject or "the subject",
                "notes": str(b.get("notes", "")).strip()[:600] + goal_text + self.source_block(sid, pages)}

    # ------------------------------------------------------------ writing helpers
    def ai_generate_lesson(self, b: dict) -> dict:
        c = self._ai_context(b)
        topic = str(b.get("topic", "")).strip()
        if not topic:
            raise AppError("ai_need_topic", "Write the lesson topic first.")
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 1))
        info = self._week_info(tri, week)
        teach = self._teach_days(c["grade"].id)  # only the days this grade has a lesson; the file says "No session" for the rest
        days = [d for d in DAY_KEYS if d.capitalize() in info["day_dates"] and d.capitalize() not in info["day_notes"] and d.capitalize() in teach]
        system = self._system_for("lesson", "Answer with ONE JSON object only, no other text.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']}\nTopic of the week: {topic}\n"
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + f"Teaching days this week: {', '.join(days) or 'none'}\n\n"
                "Return a JSON object with these keys (all values are plain strings, short lists use lines starting with '- '):\n"
                '"topic" (short title), "objectives" (2-3 learning objectives), '
                + ", ".join(f'"{d}" (what happens in that lesson, 2-3 short steps)' for d in days)
                + ', "practice_pages" (leave empty ""), "activities" (2-3 activities), "resources" (materials needed), '
                  '"differentiation" (support and challenge ideas), "assessment" (how learning is checked), "reflection" (leave empty "").')
        data = _json_from(self._ask(system, user, max_tokens=2500))
        content = {k: _as_text(data.get(k)) for k in LESSON_KEYS}
        content["topic"] = content["topic"] or topic
        for d in DAY_KEYS:
            if d not in days:
                content[d] = ""
        return {"content": content}

    def ai_generate_quiz(self, b: dict) -> dict:
        c = self._ai_context(b)
        general = str(b.get("topic", "")).strip()
        level = {"easy": "easy", "hard": "hard"}.get(str(b.get("difficulty", "")), "medium")
        sections = b.get("sections")
        if not isinstance(sections, list) or not sections:  # old shape: one multiple-choice section
            sections = [{"type": "mcq", "count": b.get("count", 5), "options": 4, "topic": ""}]
        plan = []
        for sec in sections[:12]:
            if not isinstance(sec, dict):
                continue
            kind = str(sec.get("type", "mcq"))
            kind = kind if kind in D.QUESTION_TYPES else "mcq"
            plan.append({"type": kind, "count": max(1, min(20, int(sec.get("count", 3) or 3))), "options": max(2, min(6, int(sec.get("options", 4) or 4))),
                         "topic": str(sec.get("topic", "")).strip()[:300] or general})
        has_src = bool(b.get("source_id"))
        if not plan or (not has_src and not all(p["topic"] for p in plan)):
            raise AppError("ai_need_topic", "Write the quiz topic first.")
        for p in plan:
            p["topic"] = p["topic"] or "the whole of the teacher's material"
        total = sum(p["count"] for p in plan)
        guide = {
            "mcq": lambda p: f"{p['count']} multiple-choice questions, each with exactly {p['options']} choices (a, b, c ...) and ONE correct answer. Format:\n"
                             "1. Question?\na) choice\nb) choice\nAnswer: b",
            "tf": lambda p: f"{p['count']} true/false statements. Format:\n1. Statement.\na) True\nb) False\nAnswer: a",
            "match": lambda p: f"{p['count']} matching question(s), each with 4 to 6 pairs. Format:\n1. Match each item with its description:\nitem one = its match\nitem two = its match\n(no Answer line)",
            "essay": lambda p: f"{p['count']} essay / short-answer questions. Format:\n1. Question?\nAnswer: a short model answer",
            "fill": lambda p: f"{p['count']} fill-in-the-blank sentences, with the missing word shown as ____ . Format:\n1. Sentence with a ____ here.\nAnswer: missing word",
        }
        parts = [f"SECTION {i}: {guide[p['type']](p)}\nTopic of this section: {p['topic']}" for i, p in enumerate(plan, 1)]
        verb = ""
        if b.get("verbatim"):
            verb = ("\nUse the teacher's material word for word: take questions, statements, terms and answers from its exact wording, and do not "
                    "add facts that are not in it.")
        system = self._system_for("quiz", "Follow the requested format exactly and add no explanations or extra text.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']}\nDifficulty: {level}\n"
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + f"\nWrite {total} questions in {len(plan)} section(s), in this order. Number the questions continuously from 1 across all sections; "
                  "do not write section titles. Leave a blank line between questions.\n\n" + "\n\n".join(parts) + verb)
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", self._ask(system, user, max_tokens=4000).strip(), flags=re.I)
        qs = D.parse_quiz(text) if re.search(r"^\s*(?:Q\s*)?\d+\s*[\.\)\-:]", text, re.M) else []
        if not qs:
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
        return {"text": text, "questions": len(qs)}

    def ai_generate_trimester(self, b: dict) -> dict:
        c = self._ai_context(b)
        tri = int(b.get("trimester", 0))
        weeks = self._calendar_service().trimester_weeks(tri)
        if not weeks:
            raise AppError("week_not_found", "Set the trimester dates in the Calendar first.", status=409)
        lines = []
        for w in weeks:
            tag = "NO CLASSES" if w["school_days"] == 0 else ""
            hol = [english_name(h["name"]) for h in w["holidays"] if h["name"]]
            if hol and not tag:
                tag = "holiday: " + hol[0]
            lines.append(f"Week {w['number']}" + (f" ({tag})" if tag else ""))
        system = self._system_for("trimester", "Answer with ONE JSON object only, no other text.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']}\n"
                + (f"Textbooks or topics to cover: {str(b.get('textbooks', '')).strip()[:600]}\n" if b.get("textbooks") else "")
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + "\nWeeks:\n" + "\n".join(lines)
                + '\n\nReturn {"lessons": [...]} with exactly one short lesson title (max 8 words) per week, in order. '
                  'Use "" for weeks with no classes or holidays.')
        data = _json_from(self._ask(system, user, max_tokens=1800))
        raw = data.get("lessons")
        if not isinstance(raw, list):
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
        lessons = [_as_text(x).replace("\n", " ")[:120] for x in raw][:len(weeks)]
        lessons += [""] * (len(weeks) - len(lessons))
        return {"lessons": lessons}
