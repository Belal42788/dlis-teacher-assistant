"""Saved plan topics + slide helpers.

* When a lesson plan or trimester plan is created, its topics are remembered (plans.json) so slides can start from them.
* The NotebookLM helper writes a ready prompt (and, with AI, a source text to paste as the notebook's source).
"""
from __future__ import annotations

import base64
import re
import uuid
from datetime import date
from pathlib import Path

from ..core import documents as D
from ..core import image_client, paths
from ..core.errors import AppError
from ..core.pptx_builder import build_deck

# What suits each stage: age, how much text, and how the pictures should look.
STAGES = {
    "kg": {"age": "4-6 years old", "words": "2 short lines of 4-6 words each, plus one short sentence of explanation", "n": "2", "size": "very large letters",
           "look": "cartoon", "extra": "Use friendly animal or child characters, one big object per slide, bright primary colours, rounded shapes and repetition. Letters and numbers can be shown big and playful."},
    "lower": {"age": "6-9 years old", "words": "3 short sentences of 6-10 words each, plus a 1-2 sentence explanation", "n": "3", "size": "very large letters",
              "look": "storybook", "extra": "Use a warm storybook illustration style with one or two friendly recurring characters guiding the lesson. Show the idea as a picture first, words second."},
    "upper": {"age": "9-12 years old", "words": "4 bullet points of 10-15 words each (full sentences), plus a 2-3 sentence explanation with an example", "n": "4", "size": "large, easy-to-read letters",
              "look": "colorful", "extra": "Use colourful flat illustrations with simple labelled diagrams, step-by-step arrows and 'did you know?' callouts. Keep a fun but not childish tone."},
    "middle": {"age": "12-15 years old", "words": "5 bullet points of 12-20 words each (full informative sentences), plus a 3-4 sentence explanation with an example", "n": "5", "size": "large, clear letters",
               "look": "infographic", "extra": "Use a modern infographic style: icons, flow charts, timelines, comparison tables and labelled diagrams. Clean layout, strong visual hierarchy, real-world examples."},
    "high": {"age": "15-18 years old", "words": "5 bullet points of 15-25 words each (precise full sentences), plus a 3-4 sentence explanation with an example", "n": "5", "size": "clear, professional letters",
             "look": "pro", "extra": "Use a clean, professional and mature style: precise technical diagrams, charts, realistic or semi-realistic images, and well-defined terms. Scientific/technical accuracy matters more than decoration."},
}
IMG_STYLE = {"simple": "minimal flat icon style", "colorful": "bright colourful flat illustration", "cartoon": "cute friendly cartoon style for children",
             "storybook": "warm soft storybook illustration", "diagram": "simple educational diagram style with no labels",
             "infographic": "modern flat infographic style with no text", "pro": "clean realistic technical illustration"}
LOOKS = {
    "simple": "clean and simple: lots of white space, one big illustration per slide, very little text",
    "colorful": "bright and colourful flat illustrations, friendly icons, large readable text",
    "cartoon": "cartoon-style characters and playful illustrations that young children enjoy",
    "storybook": "warm storybook illustrations with friendly recurring characters",
    "diagram": "diagram-focused: labelled diagrams, flow charts and comparison tables with short labels",
    "infographic": "modern infographic: icons, flow charts, timelines and comparison tables",
    "pro": "clean, professional and mature: precise technical diagrams, charts and realistic images",
}
BRAND = "sky blue (#2F82A8), fresh green (#A2C65A) and white, with dark navy (#1F2A5C) for text"


def stage_of(grade_id: str) -> str:
    if re.fullmatch(r"kg\d", grade_id):
        return "kg"
    m = re.fullmatch(r"g(\d+)", grade_id)
    n = int(m.group(1)) if m else 6
    return "lower" if n <= 3 else "upper" if n <= 6 else "middle" if n <= 9 else "high"


def _key(grade_id: str, tri: int, week: int) -> str:
    return f"{grade_id}|{tri}|{week}"


class SlidesMixin:
    def _plans_path(self):
        return self._need_store().root / "plans.json"

    def _plans(self) -> dict:
        def ok(d):
            if not isinstance(d, dict) or not isinstance(d.get("lesson", {}), dict) or not isinstance(d.get("trimester", {}), dict):
                raise ValueError("plans.json has the wrong shape")
        data = self._need_store().read_json(self._plans_path(), {}, check=ok) or {}
        data.setdefault("lesson", {})
        data.setdefault("trimester", {})
        return data

    # --- remember what the teacher planned (called when the Word files are made)
    def remember_lesson(self, grade_id: str, tri: int, week: int, content: dict) -> None:
        keep = {k: str(v).strip() for k, v in (content or {}).items() if k in ("topic", "objectives", "activities") and str(v).strip()}
        if not keep.get("topic"):
            return
        try:
            data = self._plans()
            data["lesson"][_key(grade_id, tri, week)] = keep
            self._need_store().write_json(self._plans_path(), data)
        except AppError:
            pass

    def remember_trimester(self, grade_id: str, tri: int, numbers: list[int], lessons: list[str]) -> None:
        titles = {str(n): t.strip() for n, t in zip(numbers, lessons) if t and t.strip()}
        if not titles:
            return
        try:
            data = self._plans()
            data["trimester"][f"{grade_id}|{tri}"] = titles
            self._need_store().write_json(self._plans_path(), data)
        except AppError:
            pass

    def slide_topics(self, grade_id: str, tri: int) -> dict:
        """For each week of the trimester: the topic from the lesson plan, else from the trimester plan, else empty."""
        self._grade(grade_id)
        cal = self._calendar_service()
        data = self._plans()
        tri_titles = data["trimester"].get(f"{grade_id}|{tri}", {})
        extra = data.get("scheme", {}).get(f"{grade_id}|{tri}", {})
        out = []
        for w in cal.trimester_weeks(tri):
            lp = data["lesson"].get(_key(grade_id, tri, w["number"]))
            e = extra.get(str(w["number"]), {})
            more = {"pages": e.get("pages", ""), "source_id": e.get("source_id", ""), "unit": e.get("unit", ""), "curriculum": e.get("objectives", "")}   # from the scheme of work
            if lp:
                out.append({"week": w["number"], "topic": lp["topic"], "source": "lesson", "objectives": lp.get("objectives", ""), **more})
            elif tri_titles.get(str(w["number"])):
                out.append({"week": w["number"], "topic": tri_titles[str(w["number"])], "source": "trimester", "objectives": "", **more})
            else:
                out.append({"week": w["number"], "topic": "", "source": "", "objectives": "", **more})
        return {"weeks": out}

    # --- NotebookLM
    def notebooklm_prompt(self, b: dict) -> dict:
        grade = self._grade(str(b.get("grade_id", "")))
        topic = " ".join(str(b.get("topic", "")).split())[:200]
        if not topic:
            raise AppError("ai_need_topic", "Write the lesson topic first.")
        n = max(6, min(30, int(b.get("slides", 10) or 10)))
        stage = STAGES[stage_of(grade.id)]
        look_key = str(b.get("look", ""))
        look = LOOKS.get(look_key) or LOOKS[stage["look"]]
        arabic = str(b.get("language", "en")) == "ar"
        subject = self._need_store().load_settings().subject or "the subject"
        objectives = [x.strip(" -•\t") for x in str(b.get("objectives", "")).splitlines() if x.strip(" -•\t")][:6]
        notes = str(b.get("notes", "")).strip()[:600]
        core = n - 5  # title, objectives, hook, recap, closing are fixed; the rest explain the lesson
        label = grade.name
        L = []
        L.append(f"Create a slide deck of exactly {n} slides that EXPLAINS the lesson \"{topic}\" for the school subject \"{subject}\".")
        L.append("Use ONLY the source I added as the content. If something is missing, keep it simple and accurate; do not invent facts.")
        L += ["", "## Audience", f"- Students of {label}, {stage['age']}.",
              "- The teacher will show the slides on a classroom screen and explain them aloud, so the slides support the teacher; they do not replace the teacher."]
        L += ["", "## Lesson", f"- Topic: {topic}"]
        if objectives:
            L.append("- By the end, students should be able to:")
            L += [f"  - {o}" for o in objectives]
        L += ["", "## Slide-by-slide plan",
              "1. Title slide: lesson title, subject, grade, with one strong picture that represents the topic.",
              "2. \"What we will learn\": the learning goals as 2-3 very short points, each with a small icon.",
              "3. Hook: a surprising picture or a question from real life that makes students curious about the topic (this is NOT an exercise).",
              f"4-{3 + core}. Core explanation ({core} slides): one idea per slide, in a logical order from simple to deeper. For each slide give a short title, "
              "the key point in plain words, and a picture or diagram that EXPLAINS the idea. Include a clear definition of every new term, "
              "at least two real-life examples the students know, and one common misunderstanding with the correct idea.",
              f"{4 + core}. Recap: the 3 most important points of the lesson in one picture.",
              f"{5 + core}. Closing slide: a short friendly closing sentence and a picture. No quiz and no homework."]
        L += ["", "## Text rules",
              f"- {stage['words'][0].upper() + stage['words'][1:]}. Use {stage['size']}.",
              "- Short titles. Simple words that suit the age. No long paragraphs and no crowded slides.",
              "- Put the explanation the teacher will say in the speaker notes (2-3 sentences per slide), not on the slide.",
              f"- Write all slide text and notes in {'Arabic: correct, clear, right-to-left layout, a clear Arabic font, and keep technical terms in English in brackets the first time they appear' if arabic else 'simple, clear English'}."]
        L += ["", "## Visual style",
              f"- Style: {look}.",
              f"- {stage['extra']}" if look_key in ("", "auto") else f"- Keep it suitable for {stage['age']}.",
              "- Every slide must have a clear picture, illustration or diagram that helps explain the idea (not just decoration). Labels on diagrams must be short and correct.",
              f"- Colours: {BRAND}. Same colours, fonts and layout on every slide so the deck looks like one set.",
              "- High contrast between text and background so it can be read from the back of the classroom.",
              "- Leave the top corner (right corner for Arabic, left for English) empty on every slide: the school logo will be added there.",
              "- Do not show student names, real people's faces, brand logos or any text in the pictures that is not needed."]
        if notes:
            L += ["", "## Extra notes from the teacher", notes]
        L += ["", "## Do not", "- Do not add exercises, quizzes, worksheets or homework (a separate revision sheet is made elsewhere).",
              "- Do not add information that is not suitable for this age."]
        return {"prompt": "\n".join(L), "stage": stage_of(grade.id)}

    def notebooklm_source(self, b: dict) -> dict:
        """AI writes a short explanation text to paste into NotebookLM as its source."""
        c = self._ai_context(b)
        topic = " ".join(str(b.get("topic", "")).split())[:200]
        if not topic:
            raise AppError("ai_need_topic", "Write the lesson topic first.")
        arabic = str(b.get("language", "en")) == "ar"
        objectives = str(b.get("objectives", "")).strip()[:600]
        system = ("You write clear, accurate teaching notes for school teachers. Use simple language that suits the grade. "
                  "Use short headings and short paragraphs. Do not include exercises.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']}\nTopic: {topic}\n"
                + (f"Learning objectives: {objectives}\n" if objectives else "")
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + f"\nWrite an explanation of this topic in about 400-600 words, in {'Arabic' if arabic else 'English'}, "
                  "with definitions, 2-3 real-life examples and a short summary. Plain text only.")
        text = self._ask(system, user, max_tokens=1800)
        return {"text": re.sub(r"^```[a-z]*\s*|\s*```$", "", text.strip(), flags=re.I)}

    # ------------------------------------------------------------ slides made inside the app
    def _image_dir(self) -> Path:
        d = paths.app_support_dir() / "slide_images"
        d.mkdir(parents=True, exist_ok=True)
        files = sorted(d.glob("*.jpg"), key=lambda f: f.stat().st_mtime)
        for old in files[:-150]:  # keep the last 150 pictures only
            old.unlink(missing_ok=True)
        return d

    def image_state(self) -> dict:
        d = self._ai_data()
        img = d.get("image") or {}
        cf_ok = bool(img.get("account_id") and img.get("api_token"))
        provider = img.get("provider") or ("cloudflare" if cf_ok else "pollinations")
        ready = {"pollinations": True, "wikimedia": True, "cloudflare": cf_ok, "huggingface": bool(img.get("hf_token")),
                 "gemini": bool(((d.get("providers") or {}).get("gemini") or {}).get("api_key"))}
        return {"provider": provider, "configured": bool(ready.get(provider)), "ready": ready,
                "providers": [{"id": p["id"], "label": p["label"], "real": p["real"]} for p in image_client.IMAGE_PROVIDERS],
                "account_id": img.get("account_id", ""), "has_token": bool(img.get("api_token")), "has_hf": bool(img.get("hf_token"))}

    def image_save(self, b: dict) -> dict:
        d = self._ai_data()
        cur = d.setdefault("image", {})
        if b.get("provider"):
            if b["provider"] not in {p["id"] for p in image_client.IMAGE_PROVIDERS}:
                raise AppError("bad_request", "Unknown picture service.", status=400)
            cur["provider"] = b["provider"]
        if b.get("api_token") == "__clear__":
            cur.pop("api_token", None)
        else:
            acc = str(b.get("account_id", "")).strip()
            tok = str(b.get("api_token", "")).strip()
            hf = str(b.get("hf_token", "")).strip()
            if acc:
                if not re.fullmatch(r"[0-9a-fA-F]{16,64}", acc):
                    raise AppError("img_bad_account", "The Account ID looks wrong. It is about 32 letters and numbers.", status=400)
                cur["account_id"] = acc
            for key, val in (("api_token", tok), ("hf_token", hf)):
                if val:
                    if not val.isascii():
                        raise AppError("ai_bad_key", "The key has characters that are not allowed. Copy it again.", status=400)
                    cur[key] = val
        self._ai_write(d)
        return self.image_state()

    def _cf(self) -> tuple[str, str]:
        img = self._ai_data().get("image") or {}
        if not (img.get("account_id") and img.get("api_token")):
            raise AppError("img_not_set", "Set up the picture service first.", status=409)
        return img["account_id"], img["api_token"]

    def _make_picture(self, prompt: str, search: str, steps: int = 8) -> bytes:
        st = self.image_state()
        prov = st["provider"]
        if not st["ready"].get(prov):
            raise AppError("img_not_set", "Set up the picture service first.", status=409)
        d = self._ai_data()
        if prov == "pollinations":
            return image_client.pollinations_image(prompt)
        if prov == "huggingface":
            return image_client.huggingface_image(d["image"]["hf_token"], prompt)
        if prov == "gemini":
            return image_client.gemini_image(d["providers"]["gemini"]["api_key"], prompt)
        if prov == "wikimedia":
            return image_client.wikimedia_image(search)
        acc, tok = self._cf()
        return image_client.cloudflare_image(acc, tok, prompt, steps=steps)

    def image_test(self, b: dict) -> dict:
        self.image_save(b)
        raw = self._make_picture("a simple blue circle on a white background", "blue circle", steps=2)
        return {"ok": True, "bytes": len(raw)}

    def slide_image(self, b: dict) -> dict:
        prompt = " ".join(str(b.get("prompt", "")).split())[:600]
        if not prompt:
            raise AppError("img_need_prompt", "Write what the picture should show.", status=400)
        stage = STAGES[stage_of(str(b.get("grade_id", "g4")))]
        look = IMG_STYLE.get(str(b.get("look", ""))) or IMG_STYLE.get(stage["look"], "bright colourful flat illustration")
        names = self._all_student_names()
        from .ai_service import redact
        full = (f"{redact(prompt, names)}. {look}. Clean flat vector illustration like a classroom poster, one clear subject in the centre, "
                f"simple shapes, bold clean outlines, bright friendly colours, plain white background, sharp and uncluttered. "
                f"No text, no letters, no numbers, no words, no logos, no watermark.")
        raw = _as_jpeg(self._make_picture(full, redact(prompt, names)))
        iid = uuid.uuid4().hex
        (self._image_dir() / f"{iid}.jpg").write_bytes(raw)
        return {"id": iid, "data_url": "data:image/jpeg;base64," + base64.b64encode(raw).decode()}

    def slide_plan(self, b: dict) -> dict:
        c = self._ai_context(b)
        topic = " ".join(str(b.get("topic", "")).split())[:200]
        if not topic:
            raise AppError("ai_need_topic", "Write the lesson topic first.")
        n = max(4, min(25, int(b.get("slides", 8) or 8)))
        arabic = str(b.get("language", "en")) == "ar"
        stage = STAGES[stage_of(c["grade"].id)]
        objectives = str(b.get("objectives", "")).strip()[:600]
        system = self._system_for("slides", "Answer with ONE JSON object only, no other text.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']} ({stage['age']})\nLesson: {topic}\n"
                + (f"Learning objectives:\n{objectives}\n" if objectives else "")
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + f"\nThe lesson topic is \"{topic}\". Make the slides about this topic only, even if the notes or material mention something else.\n"
                + f"\nMake exactly {n} slides (not counting the title slide). Slide 1 is what we will learn, the last slide is a short recap. "
                  f"Each slide: {stage['words']}. The slides must be rich and useful for teaching, not empty. "
                  f"Write title, bullets and notes in {'Arabic' if arabic else 'simple English'}. "
                  "explain = a short paragraph under the bullets that explains the idea in simple words. notes = what the teacher says (2-3 sentences). image_prompt = ONE English sentence describing a clear illustration "
                  "that explains the idea (no text inside the picture).\n"
                  '\nReturn: {"slides": [{"title": "...", "bullets": ["..."], "explain": "...", "notes": "...", "image_prompt": "..."}]}')
        data = _json_from_slides(self._ask(system, user, max_tokens=6000))
        slides = []
        for x in data[:n]:
            if not isinstance(x, dict):
                continue
            bl = x.get("bullets")
            bl = [str(i).strip() for i in bl] if isinstance(bl, list) else [str(bl).strip()] if bl else []
            slides.append({"title": str(x.get("title", "")).strip()[:120], "bullets": [i for i in bl if i][:5],
                           "explain": str(x.get("explain", "")).strip()[:700], "notes": str(x.get("notes", "")).strip()[:800], "image_prompt": str(x.get("image_prompt", "")).strip()[:400]})
        if not slides:
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
        return {"slides": slides, "stage": stage_of(c["grade"].id), "model": getattr(self, "last_model", "")}

    def slide_build(self, b: dict) -> dict:
        store = self._need_store()
        grade = self._grade(str(b.get("grade_id", "")))
        title = " ".join(str(b.get("title", "")).split())[:160]
        if not title:
            raise AppError("ai_need_topic", "Write the lesson topic first.")
        raw = b.get("slides")
        if not isinstance(raw, list) or not raw:
            raise AppError("no_slides", "There are no slides to make yet.", status=400)
        slides = []
        for x in raw[:60]:
            if not isinstance(x, dict):
                continue
            image = ""
            iid = str(x.get("image_id", ""))
            if re.fullmatch(r"[0-9a-f]{32}", iid) and (self._image_dir() / f"{iid}.jpg").is_file():
                image = str(self._image_dir() / f"{iid}.jpg")
            bl = x.get("bullets")
            slides.append({"title": D._clean(x.get("title")), "bullets": [D._clean(i) for i in (bl if isinstance(bl, list) else [])],
                           "explain": D._clean(x.get("explain")), "notes": D._clean(x.get("notes")), "image_path": image})
        subject = store.load_settings().subject
        deck = {"title": D._clean(title), "subtitle": " · ".join(p for p in (subject, grade.name) if p),
                "language": "ar" if b.get("language") == "ar" else "en", "stage": stage_of(grade.id), "slides": slides}
        try:
            tri, week = int(b.get("trimester", -1)), int(b.get("week", 0))
        except (TypeError, ValueError):
            tri, week = -1, 0
        safe = re.sub(r'[\\/:*?"<>|]+', "-", title).strip()[:60] or "Slides"
        prefix = f"T{tri + 1}-W{week:02d}_" if tri >= 0 and week > 0 else ""
        out = store.root / "Slides" / re.sub(r'[\\/:*?"<>|]+', "-", grade.name) / f"{prefix}{safe}.pptx"
        try:
            build_deck(out, deck)
        except PermissionError:
            raise AppError("file_in_use", f"Close this file in PowerPoint first: {out.name}", status=409)
        try:
            self._made_source(out, [{"text": deck["title"] + ("\n" + deck["subtitle"] if deck["subtitle"] else "")}] + [
                {"text": "\n".join([x["title"]] + x["bullets"] + ([x["explain"]] if x["explain"] else [])), "notes": x["notes"]} for x in slides])
        except Exception:
            pass  # the deck itself is made; listing it under "my slides" is a bonus
        if tri >= 0 and week > 0:  # remember how many slides this lesson has (the lesson log can show "slide 12 of 18")
            data = self._plans()
            data.setdefault("slides", {})[_key(grade.id, tri, week)] = {"count": len(slides) + 1, "file": out.name}
            store.write_json(self._plans_path(), data)
        res = self._result(out)
        res["slides"] = len(slides) + 1
        return res


def _as_jpeg(raw: bytes) -> bytes:
    """Whatever the picture service sent, keep one small JPEG (the slides need nothing bigger)."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((1400, 1400))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return raw


def _json_from_slides(text: str) -> list:
    from .ai_service import _json_from
    data = _json_from(text)
    items = data.get("slides") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []
