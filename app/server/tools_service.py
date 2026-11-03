"""The extra AI tools (see tools_catalog.py): one form in, one ready text out, then copy it or save it as a Word file."""
from __future__ import annotations

import re

from ..core import documents as D
from ..core import paths
from ..core.errors import AppError
from .docs_service import _safe
from .tools_catalog import BY_ID, GROUPS, TOOLS

LANGS = {"en": "English", "ar": "Arabic (Modern Standard, simple and clear)", "both": "English first, then the same in Arabic"}
SYSTEM = ("You are a careful teaching assistant for teachers at an international school in Egypt. Write ready-to-use classroom material that is accurate, "
          "age-appropriate and short enough to use. Plain text only: no markdown symbols such as ** or #. Use a short heading line in capitals or with a colon, "
          "'- ' for bullet points, numbers for steps, and '|' between cells for tables. Never invent facts about the students. "
          "If the teacher gives SOURCE MATERIAL, use only it.")


class ToolsMixin:
    def tools_catalog(self) -> dict:
        return {"groups": [{"id": g, "name": {"en": en, "ar": ar}} for g, en, ar in GROUPS], "tools": TOOLS}

    def tools_run(self, b: dict) -> dict:
        tool = BY_ID.get(str(b.get("tool", "")))
        if not tool:
            raise AppError("bad_value", "Unknown tool.", status=400)
        vals = b.get("values") if isinstance(b.get("values"), dict) else {}
        lines = []
        for f in tool["fields"]:
            v = " ".join(str(vals.get(f["key"], "")).split()) if f["type"] != "textarea" else str(vals.get(f["key"], "")).strip()
            v = v[:6000]
            if not v and f["required"]:
                raise AppError("ai_need_topic", f"Fill in: {f['label']['en']}", status=400)
            if v:
                lines.append(f"{f['label']['en']}: {v}")
        s = self._need_store().load_settings()
        grade = ""
        if b.get("grade_id"):
            g = self._grade(str(b["grade_id"]))
            grade = self._grade_label(g)
        lang = LANGS.get(str(b.get("language")), LANGS["en"])
        sid, pages = b.get("source_id"), b.get("source_pages")
        user = (f"Subject: {s.subject or 'the subject'}\n" + (f"Grade: {grade}\n" if grade else "") + f"Write the answer in: {lang}\n\n"
                f"TASK: {tool['instruction']}\n\nDETAILS FROM THE TEACHER:\n" + "\n".join(lines)
                + (f"\nExtra notes: {str(b.get('notes')).strip()[:600]}" if str(b.get("notes", "")).strip() else "")
                + self.source_block(sid, pages, cite=bool(b.get("cite"))))
        text = self._ask(SYSTEM, user, max_tokens=3000).strip()
        text = re.sub(r"\*\*|^#{1,6}\s*", "", text, flags=re.M)      # a model sometimes uses markdown anyway
        return {"text": text, "model": getattr(self, "last_model", "")}

    def tools_word(self, b: dict) -> dict:
        tool = BY_ID.get(str(b.get("tool", "")))
        text = str(b.get("text", "")).strip()
        if not tool or not text:
            raise AppError("bad_value", "Nothing to save yet.", status=400)
        store = self._need_store()
        s = store.load_settings()
        grade = self._grade(str(b["grade_id"])).name if b.get("grade_id") else "Tools"
        base = store.root / "Documents" / _safe(grade)
        n = 1
        while (base / f"{_safe(tool['name']['en'])}_{n}.docx").exists():
            n += 1
        out = base / f"{_safe(tool['name']['en'])}_{n}.docx"
        D.write_plain_doc(out, tool["name"]["en"], text, {"school": s.school_name, "subject": s.subject, "teacher": s.teacher_name, "logo": paths.resources_dir() / "logo.png"})
        return self._result(out)
