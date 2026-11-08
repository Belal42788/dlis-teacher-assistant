"""Question bank: every question the teacher saved, per grade and topic, so a new quiz is a few clicks.
A question is stored as the same plain text the quiz box reads, so nothing is converted twice. Stays on this computer."""
from __future__ import annotations

import random
import re
import uuid
from datetime import date

from ..core import documents as D
from ..core.errors import AppError

LEVELS = ("easy", "medium", "hard")
MAX_BANK = 5000
MAX_PER_ADD = 200


def _check(d) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("questions", []), list):
        raise ValueError("question_bank.json has the wrong shape")


def _same(text: str) -> str:
    """The question's words only, so "What is CPU?" and "what is  the cpu" are not saved twice."""
    t = re.sub(r"[^\w\s]", " ", str(text).lower())
    return " ".join(w for w in t.split() if w not in ("the", "a", "an", "ال"))


class BankMixin:
    def _bank_path(self):
        return self._need_store().root / "question_bank.json"

    def _bank_data(self) -> dict:
        data = self._need_store().read_json(self._bank_path(), {}, check=_check) or {}
        data.setdefault("questions", [])
        return data

    @staticmethod
    def _bank_view(e: dict) -> dict:
        q = (D.parse_quiz(e.get("text", "")) or [{"q": "", "type": "essay", "options": [], "pairs": [], "answer": ""}])[0]
        used = e.get("used") or []
        return {"id": e["id"], "grade_id": e["grade_id"], "topic": e.get("topic", ""), "level": e.get("level", "medium"), "text": e["text"],
                "type": q["type"], "q": q["q"], "options": q["options"], "pairs": q["pairs"], "answer": q["answer"],
                "used": len(used), "last_used": used[-1]["date"] if used else "", "added": e.get("added", "")}

    def _bank_filter(self, data: dict, grade_id="", topic="", level="", search="") -> list[dict]:
        topic, search = topic.strip().lower(), search.strip().lower()
        out = []
        for e in data["questions"]:
            if grade_id and e["grade_id"] != grade_id:
                continue
            if topic and topic != str(e.get("topic", "")).lower():
                continue
            if level and e.get("level") != level:
                continue
            if search and search not in e["text"].lower():
                continue
            out.append(e)
        return out

    def bank_list(self, q: dict) -> dict:
        data = self._bank_data()
        grade = str(q.get("grade_id", ""))
        rows = self._bank_filter(data, grade, str(q.get("topic", "")), str(q.get("level", "")), str(q.get("search", "")))
        rows.sort(key=lambda e: (e.get("added", ""), e["id"]), reverse=True)
        topics = sorted({e.get("topic", "") for e in data["questions"] if e.get("topic") and (not grade or e["grade_id"] == grade)})
        return {"items": [self._bank_view(e) for e in rows[:500]], "found": len(rows), "total": len(data["questions"]), "topics": topics}

    def _bank_fields(self, b: dict) -> tuple[str, str, str]:
        grade = self._grade(str(b.get("grade_id", ""))).id
        topic = " ".join(str(b.get("topic", "")).split())[:80]
        level = str(b.get("level") or "medium")
        if level not in LEVELS:
            raise AppError("invalid_data", "bad level")
        return grade, topic, level

    def bank_add(self, b: dict) -> dict:
        grade, topic, level = self._bank_fields(b)
        questions = D.parse_quiz(b.get("text", ""))
        if not questions:
            raise AppError("no_questions", "Paste at least one question first.")
        data = self._bank_data()
        seen = {_same(D.parse_quiz(e["text"])[0]["q"]) for e in data["questions"] if e["grade_id"] == grade and D.parse_quiz(e["text"])}
        added = skipped = 0
        for q in questions[:MAX_PER_ADD]:
            key = _same(q["q"])
            if key in seen:
                skipped += 1
                continue
            if len(data["questions"]) >= MAX_BANK:
                raise AppError("bank_full", f"The bank holds {MAX_BANK} questions at most.", status=409)
            seen.add(key)
            data["questions"].append({"id": uuid.uuid4().hex[:10], "grade_id": grade, "topic": topic, "level": level,
                                      "text": D.question_to_text(q, 1), "used": [], "added": date.today().isoformat()})
            added += 1
        if added:
            self._need_store().write_json(self._bank_path(), data)
        return {"added": added, "skipped": skipped, "total": len(data["questions"])}

    def bank_update(self, qid: str, b: dict) -> dict:
        data = self._bank_data()
        e = next((x for x in data["questions"] if x["id"] == qid), None)
        if not e:
            raise AppError("question_not_found", status=404)
        if "text" in b:
            parsed = D.parse_quiz(b.get("text", ""))
            if len(parsed) != 1:
                raise AppError("one_question", "Edit one question at a time.")
            e["text"] = D.question_to_text(parsed[0], 1)
        if "topic" in b or "level" in b:
            _, topic, level = self._bank_fields({"grade_id": e["grade_id"], "topic": b.get("topic", e.get("topic", "")), "level": b.get("level", e.get("level", "medium"))})
            e["topic"], e["level"] = topic, level
        self._need_store().write_json(self._bank_path(), data)
        return {"item": self._bank_view(e)}

    def bank_delete(self, qid: str) -> dict:
        data = self._bank_data()
        keep = [x for x in data["questions"] if x["id"] != qid]
        if len(keep) == len(data["questions"]):
            raise AppError("question_not_found", status=404)
        data["questions"] = keep
        self._need_store().write_json(self._bank_path(), data)
        return {"total": len(keep)}

    def bank_pick(self, b: dict) -> dict:
        """Questions for a new quiz, as quiz text. `ids` = the ones the teacher ticked; otherwise `count` random ones,
        preferring the questions used the fewest times so the same quiz does not come back."""
        data = self._bank_data()
        start = max(0, int(b.get("start", 0) or 0))
        if b.get("ids"):
            by_id = {e["id"]: e for e in data["questions"]}
            chosen = [by_id[i] for i in b["ids"] if i in by_id]
        else:
            pool = self._bank_filter(data, str(b.get("grade_id", "")), str(b.get("topic", "")), str(b.get("level", "")))
            count = max(1, min(int(b.get("count", 5) or 5), 50))
            rnd = random.Random()
            rnd.shuffle(pool)
            chosen = sorted(pool, key=lambda e: len(e.get("used") or []))[:count]
        if not chosen:
            raise AppError("bank_empty", "No saved questions match. Save some first.", status=404)
        text = "\n\n".join(D.question_to_text(D.parse_quiz(e["text"])[0], start + i + 1) for i, e in enumerate(chosen))
        return {"text": text, "ids": [e["id"] for e in chosen], "count": len(chosen)}

    def _bank_mark_used(self, ids, label: str) -> None:
        """Remember in which quiz a saved question was used (called when the quiz file is made)."""
        ids = {str(i) for i in (ids or [])}
        if not ids:
            return
        data = self._bank_data()
        hit = False
        for e in data["questions"]:
            if e["id"] in ids:
                e.setdefault("used", []).append({"date": date.today().isoformat(), "quiz": str(label)[:60]})
                hit = True
        if hit:
            self._need_store().write_json(self._bank_path(), data)
