"""Sources: the teacher's own slides/notes (PDF, PowerPoint, Word, text) read by the app, so every writing helper can use them.

NotebookLM slides are usually pictures. Pages with no real text are shown to an AI service that can see images and are
transcribed. Page pictures stay on THIS computer only (app-support folder); the text and the digest live in the data folder.
"""
from __future__ import annotations

import base64
import io
import re
import shutil
import uuid
from datetime import date

from ..core import paths
from ..core.errors import AppError
from .ai_service import _json_from, registry

MAX_PAGES = 60
MIN_TEXT = 60          # fewer characters than this on a page = the page is a picture
BATCH = 3
MAX_CLIP = 7000        # characters of source handed to the writing helpers
EXTS = (".pdf", ".pptx", ".docx", ".txt", ".md")


def _jpeg(img, side: int = 1400) -> bytes:
    from PIL import Image
    img = img.convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _clean(t: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", str(t or "").replace("\r", ""))).strip()


def extract_pdf(raw: bytes):
    import pypdfium2 as pdfium
    try:
        pdf = pdfium.PdfDocument(raw)
    except Exception as e:  # noqa: BLE001
        raise AppError("file_unreadable", "This PDF cannot be opened.", status=400) from e
    pages = []
    for i in range(min(len(pdf), MAX_PAGES)):
        page = pdf[i]
        text = _clean(page.get_textpage().get_text_range())
        img = None
        if len(text) < MIN_TEXT:
            w, h = page.get_size()
            img = _jpeg(page.render(scale=min(2.5, 1500 / max(w, h, 1))).to_pil())
        pages.append({"text": text, "image": img})
    pdf.close()
    return pages


def extract_pptx(raw: bytes):
    from pptx import Presentation
    from PIL import Image
    try:
        prs = Presentation(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise AppError("file_unreadable", "This PowerPoint cannot be opened.", status=400) from e
    pages = []
    for slide in list(prs.slides)[:MAX_PAGES]:
        parts, best, area = [], None, 0
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                parts.append(sh.text_frame.text.strip())
            if getattr(sh, "has_table", False) and sh.has_table:
                parts += [" | ".join(c.text for c in r.cells) for r in sh.table.rows]
            if sh.shape_type == 13:
                try:
                    a = (sh.width or 0) * (sh.height or 0)
                    if a > area:
                        best, area = sh.image.blob, a
                except Exception:  # noqa: BLE001
                    pass
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        text = _clean("\n".join(parts))
        img = None
        if len(text) < MIN_TEXT and best:
            try:
                img = _jpeg(Image.open(io.BytesIO(best)))
            except Exception:  # noqa: BLE001
                img = None
        pages.append({"text": text, "image": img, "notes": _clean(notes)})
    return pages


def extract_docx(raw: bytes):
    from docx import Document
    try:
        d = Document(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise AppError("file_unreadable", "This Word file cannot be opened.", status=400) from e
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for tb in d.tables:
        lines += [" | ".join(c.text for c in r.cells) for r in tb.rows]
    return [{"text": _clean("\n".join(lines)), "image": None}]


def extract(filename: str, raw: bytes):
    low = filename.lower()
    if low.endswith(".pdf") or raw[:4] == b"%PDF":
        return extract_pdf(raw)
    if low.endswith(".pptx"):
        return extract_pptx(raw)
    if low.endswith(".docx"):
        return extract_docx(raw)
    if low.endswith((".txt", ".md")):
        return [{"text": _clean(raw.decode("utf-8", "replace")), "image": None}]
    raise AppError("file_type", "Use a PDF, PowerPoint, Word or text file.", status=400)


class SourceMixin:
    def _src_path(self):
        return self._need_store().root / "sources.json"

    def _src_dir(self, sid: str):
        if not re.fullmatch(r"[0-9a-f]{10}", sid):
            raise AppError("bad_value", "Unknown source.", status=400)
        return paths.app_support_dir() / "source_pages" / sid

    def _srcs(self) -> list:
        data = self._need_store().read_json(self._src_path(), [], check=lambda d: isinstance(d, list) or (_ for _ in ()).throw(ValueError()))
        return data if isinstance(data, list) else []

    def _src(self, sid: str) -> dict:
        for s in self._srcs():
            if s["id"] == sid:
                return s
        raise AppError("source_missing", "That source was not found.", status=404)

    def _src_save(self, src: dict) -> None:
        items = [s for s in self._srcs() if s["id"] != src["id"]]
        items.append(src)
        self._need_store().write_json(self._src_path(), items)

    @staticmethod
    def _src_brief(s: dict) -> dict:
        pages = s["pages"]
        pending = sum(1 for p in pages if p.get("vision") and not p.get("done"))
        d = s.get("digest") or {}
        return {"id": s["id"], "name": s["name"], "added": s["added"], "pages": len(pages), "pending": pending,
                "chars": sum(len(p["text"]) for p in pages), "topic": d.get("topic", ""), "has_digest": bool(d), "read_model": s.get("read_model", "")}

    def list_sources(self) -> dict:
        return {"sources": sorted((self._src_brief(s) for s in self._srcs()), key=lambda x: x["added"], reverse=True)}

    def get_source(self, sid: str) -> dict:
        s = self._src(sid)
        return {**self._src_brief(s), "digest": s.get("digest") or {}, "text": self._src_text(s, 60000)}

    def import_source(self, b: dict) -> dict:
        name = str(b.get("filename") or "slides").strip()[:120]
        try:
            raw = base64.b64decode(b.get("data_b64") or "")
        except ValueError as e:
            raise AppError("file_unreadable") from e
        if not raw:
            raise AppError("file_unreadable", "The file is empty.", status=400)
        pages = extract(name, raw)
        if not any(p["text"] or p.get("image") for p in pages):
            raise AppError("source_empty", "Nothing readable was found in this file.", status=400)
        sid = uuid.uuid4().hex[:10]
        folder = self._src_dir(sid)
        out = []
        for i, p in enumerate(pages, 1):
            vision = bool(p.get("image"))
            if vision:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"p{i}.jpg").write_bytes(p["image"])
            out.append({"n": i, "text": p["text"], "notes": p.get("notes", ""), "vision": vision, "done": not vision})
        src = {"id": sid, "name": re.sub(r"\.(pdf|pptx|docx|txt|md)$", "", name, flags=re.I), "added": date.today().isoformat(), "pages": out}
        self._src_save(src)
        return self._src_brief(src)

    def delete_source(self, sid: str) -> dict:
        self._src(sid)
        self._need_store().write_json(self._src_path(), [s for s in self._srcs() if s["id"] != sid])
        shutil.rmtree(self._src_dir(sid), ignore_errors=True)
        return {"ok": True}

    # ------------------------------------------------------------ reading pictures
    def _vision_models(self, cfg: dict) -> list[str]:
        prov = next((p for p in registry() if p["id"] == cfg["provider"]), {})
        out = [cfg["model"]] if cfg.get("model") else []
        out += prov.get("vision_models", [])
        if prov.get("vision_any") and not cfg.get("model"):
            try:
                out += self._models_for(cfg)[:4]
            except AppError as e:
                if e.code in ("ai_bad_key", "ai_offline", "ai_timeout", "ai_rate_limit"):
                    raise
        if not out and cfg["provider"] == "custom":  # we cannot know which of their models sees pictures: try the best ones
            try:
                out = self._models_for(cfg)[:3]
            except AppError:
                out = []
        return list(dict.fromkeys(out))

    def _vision_chat(self, system: str, user: str, images: list[bytes]) -> tuple[str, str]:
        from ..core import ai_client
        cfg = self._ai_config()
        cands = self._vision_models(cfg)
        if not cands:
            raise AppError("ai_no_vision", "This AI service cannot read pictures. Use Gemini (free) in Settings.", status=409)
        last = None
        for m in cands[:4]:
            try:
                return ai_client.chat({**cfg, "model": m}, system, user, max_tokens=3500, temperature=0.1, images=images), m
            except AppError as e:
                last = e
                if e.code not in ("ai_bad_model", "ai_bad_request", "ai_empty", "ai_server", "ai_rate_limit"):
                    raise
        raise last or AppError("ai_no_vision", "No model could read the pictures.", status=502)

    def read_source(self, sid: str) -> dict:
        src = self._src(sid)
        todo = [p for p in src["pages"] if p.get("vision") and not p.get("done")][:BATCH]
        if todo:
            folder = self._src_dir(sid)
            imgs, nums = [], []
            for p in todo:
                f = folder / f"p{p['n']}.jpg"
                if f.is_file():
                    imgs.append(f.read_bytes()); nums.append(p["n"])
                else:
                    p["done"] = True  # the picture is gone (another computer): nothing more to read
            if imgs:
                system = ("You read school slides that are pictures. For each picture, copy ALL the text exactly as written (any language), "
                          "then add a short description of diagrams or drawings that carry meaning. Answer with ONE JSON object only.")
                user = (f"There are {len(imgs)} slide pictures, in this order, with these slide numbers: {nums}.\n"
                        'Return: {"pages": [{"n": <slide number>, "text": "<all text>", "diagram": "<short description or empty>"}]}')
                raw, used = self._vision_chat(system, user, imgs)
                src["read_model"] = used
                try:
                    items = _json_from(raw).get("pages") or []
                except Exception:  # noqa: BLE001
                    items = []
                got = {}
                for it in items:
                    if isinstance(it, dict) and isinstance(it.get("n"), int):
                        got[it["n"]] = _clean((str(it.get("text") or "") + ("\n[Picture: " + str(it.get("diagram")) + "]" if it.get("diagram") else "")))
                if not got:  # not JSON: keep what the AI wrote as the text of the first page
                    got[nums[0]] = _clean(re.sub(r"^```[a-z]*\s*|\s*```$", "", raw))
                for p in todo:
                    if p["n"] in got:
                        p["text"], p["done"] = got[p["n"]], True
                    elif p["n"] in nums and len(nums) == 1:
                        p["done"] = True
                if not any(p["done"] for p in todo if p["n"] in nums):
                    raise AppError("ai_bad_output", "The AI did not read the pictures. Try again.", status=502)
            self._src_save(src)
        return self._src_brief(src)

    # ------------------------------------------------------------ digest + use
    def _src_text(self, src: dict, limit: int = MAX_CLIP) -> str:
        parts = []
        for p in src["pages"]:
            body = "\n".join(x for x in (p["text"], ("Teacher notes: " + p["notes"]) if p.get("notes") else "") if x)
            if body:
                parts.append(f"[Slide {p['n']}]\n{body}" if len(src["pages"]) > 1 else body)
        return "\n\n".join(parts)[:limit]

    def digest_source(self, sid: str) -> dict:
        src = self._src(sid)
        text = self._src_text(src, 14000)
        if not text.strip():
            raise AppError("source_empty", "This source has no text yet. Let the app read the pictures first.", status=409)
        system = self._system_for("revision", "Answer with ONE JSON object only, no other text. Use ONLY what the source says.")
        user = ("Source (a teacher's slides):\n" + text + "\n\nExtract what a teacher needs for school files. "
                'Return: {"topic": "short lesson title", "objectives": ["..."], "words": [{"term": "...", "meaning": "..."}], '
                '"points": ["..."], "activities": ["..."], "questions": [{"q": "...", "a": "..."}]}. '
                "objectives: 2-4, start with an action verb. words: up to 8. points: up to 8. activities: up to 4 (only if the source suggests some). questions: 4-8 short Q&A.")
        data = _json_from(self._ask(system, user, max_tokens=3000))
        if not isinstance(data, dict):
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)

        def lst(k, n):
            return [" ".join(str(x).split())[:300] for x in (data.get(k) or []) if str(x).strip()][:n]
        digest = {"topic": " ".join(str(data.get("topic") or "").split())[:120], "objectives": lst("objectives", 4), "points": lst("points", 8), "activities": lst("activities", 4),
                  "words": [{"term": " ".join(str(x.get("term")).split())[:60], "meaning": " ".join(str(x.get("meaning") or "").split())[:200]}
                            for x in (data.get("words") or []) if isinstance(x, dict) and x.get("term")][:8],
                  "questions": [{"q": " ".join(str(x.get("q")).split())[:220], "a": " ".join(str(x.get("a") or "").split())[:200]}
                                for x in (data.get("questions") or []) if isinstance(x, dict) and x.get("q")][:8]}
        src["digest"] = digest
        self._src_save(src)
        return {**self._src_brief(src), "digest": digest}

    def source_block(self, sid: str) -> str:
        """Text added to the prompt of the writing helpers."""
        sid = str(sid or "")
        if not sid:
            return ""
        try:
            text = self._src_text(self._src(sid))
        except AppError:
            return ""
        return ("\nSource material from the teacher's own slides (base your answer on it, do not contradict it):\n" + text) if text.strip() else ""
