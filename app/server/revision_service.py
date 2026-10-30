"""Revision sheet (ملف مراجعة): key words, key points and short questions, in the DLIS Word look."""
from __future__ import annotations

from datetime import date

from ..core import documents as D
from ..core.errors import AppError
from .docs_service import _safe
from .slides_service import STAGES, stage_of


def _clip(x, n: int) -> str:
    return " ".join(str(x or "").split())[:n]


class RevisionMixin:
    def ai_generate_revision(self, b: dict) -> dict:
        from .ai_service import _json_from
        c = self._ai_context(b)
        topic = str(b.get("topic", "")).strip()
        if not topic:
            raise AppError("ai_need_topic", "Write the revision topic first.")
        stage = STAGES[stage_of(c["grade"].id)]
        n = max(3, min(15, int(b.get("count", 6) or 6)))
        system = self._system_for("revision", "Answer with ONE JSON object only, no other text.")
        user = (f"Subject: {c['subject']}\nGrade: {c['label']} ({stage['age']})\nRevision topic(s): {topic}\n"
                + (f"Teacher notes: {c['notes']}\n" if c["notes"] else "")
                + f"\nWrite a one-page revision sheet in simple English. {stage['words']}.\n"
                  f"- words: 4 to 8 key words, each with a short child-friendly meaning.\n- points: 3 to 6 short facts to remember.\n"
                  f"- questions: exactly {n} short questions with a short answer each (not multiple choice).\n"
                  + ("Use the teacher's material word for word: take key words, points, questions and answers from its exact wording, and add no facts that are not in it.\n" if b.get("verbatim") else "")
                  + 'Return: {"words": [{"term": "...", "meaning": "..."}], "points": ["..."], "questions": [{"q": "...", "a": "..."}]}')
        data = _json_from(self._ask(system, user, max_tokens=3000))
        if not isinstance(data, dict):
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
        words = [f"{_clip(x.get('term'), 60)}: {_clip(x.get('meaning'), 200)}" for x in (data.get("words") or []) if isinstance(x, dict) and x.get("term")]
        points = [_clip(x, 220) for x in (data.get("points") or []) if str(x).strip()]
        qs = [f"{_clip(x.get('q'), 220)} | {_clip(x.get('a'), 200)}" for x in (data.get("questions") or []) if isinstance(x, dict) and x.get("q")]
        if not (words or points or qs):
            raise AppError("ai_bad_output", "The AI answer was not in the expected shape. Try again.", status=502)
        return {"words": "\n".join(words), "points": "\n".join(points), "questions": "\n".join(qs[:n])}

    def make_revision(self, b: dict) -> dict:
        grade = self._grade(str(b.get("grade_id", "")))
        tri, week = int(b.get("trimester", 0)), int(b.get("week", 0) or 0)
        title = str(b.get("title", "")).strip()
        words, points = D.parse_revision_text(b.get("words"), "words"), D.parse_revision_text(b.get("points"), "points")
        qs = D.parse_revision_text(b.get("questions"), "questions")
        if not (words or points or qs):
            raise AppError("no_questions", "Write or generate the revision content first.")
        base = self._need_store().root / "Documents" / _safe(grade.name)
        stem = f"T{tri + 1}-W{week:02d}" if week else f"T{tri + 1}"
        out = base / f"{stem}_Revision_Sheet.docx"
        D.fill_revision(D.template_path("revision"), out, {
            "grade_label": self._grade_label(grade), "trimester": tri + 1, "week": week, "title": title,
            "words": words, "points": points, "questions": qs, "with_answers": bool(b.get("with_answers"))})
        return self._result(out)
