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
MAX_EXAM = 100
NO_TOPIC = "__none__"   # the topic filter that means "questions saved without a topic"


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

    def _bank_filter(self, data: dict, grade_id="", topic="", level="", search="", quiz="") -> list[dict]:
        topic, search = topic.strip().lower(), search.strip().lower()
        out = []
        for e in data["questions"]:
            if grade_id and e["grade_id"] != grade_id:
                continue
            if topic == NO_TOPIC:
                if e.get("topic"):
                    continue
            elif topic and topic != str(e.get("topic", "")).lower():
                continue
            if level and e.get("level") != level:
                continue
            if search and search not in e["text"].lower():
                continue
            if quiz and not any(u.get("quiz") == quiz for u in e.get("used") or []):
                continue
            out.append(e)
        return out

    def bank_list(self, q: dict) -> dict:
        data = self._bank_data()
        grade = str(q.get("grade_id", ""))
        rows = self._bank_filter(data, grade, str(q.get("topic", "")), str(q.get("level", "")), str(q.get("search", "")), str(q.get("quiz", "")))
        rows.sort(key=lambda e: (e.get("added", ""), e["id"]), reverse=True)
        topics = sorted({e.get("topic", "") for e in data["questions"] if e.get("topic") and (not grade or e["grade_id"] == grade)})
        return {"items": [self._bank_view(e) for e in rows[:500]], "found": len(rows), "total": len(data["questions"]), "topics": topics}

    def bank_topics(self, q: dict) -> dict:
        """One card per topic for the bank page: how many questions, how they split by level, and how many were ever used in a quiz.
        Also the quizzes that used these questions, so a new exam can mix questions that came from several quizzes."""
        data = self._bank_data()
        grade = str(q.get("grade_id", ""))
        rows = [e for e in data["questions"] if not grade or e["grade_id"] == grade]
        cards: dict[str, dict] = {}
        quizzes: dict[str, int] = {}
        for e in rows:
            c = cards.setdefault(e.get("topic", ""), {"topic": e.get("topic", ""), "total": 0, "used": 0, "levels": dict.fromkeys(LEVELS, 0)})
            c["total"] += 1
            c["levels"][e.get("level") if e.get("level") in LEVELS else "medium"] += 1
            if e.get("used"):
                c["used"] += 1
            for label in {u.get("quiz", "") for u in e.get("used") or []} - {""}:
                quizzes[label] = quizzes.get(label, 0) + 1
        ordered = sorted(cards.values(), key=lambda c: (c["topic"] == "", c["topic"].lower()))
        return {"cards": ordered, "total": len(rows), "used": sum(c["used"] for c in ordered),
                "quizzes": [{"quiz": k, "count": v} for k, v in sorted(quizzes.items(), reverse=True)]}

    # ---- the exam basket: questions the teacher ticked, kept until the exam is made (survives closing the program)
    def _basket_path(self):
        return self._need_store().root / "exam_basket.json"

    def _basket_raw(self) -> dict:
        def check(d):
            if not isinstance(d, dict) or not isinstance(d.get("ids", []), list):
                raise ValueError("exam_basket.json has the wrong shape")
        return self._need_store().read_json(self._basket_path(), {}, check=check) or {}

    def bank_basket(self) -> dict:
        raw = self._basket_raw()
        by_id = {e["id"]: e for e in self._bank_data()["questions"]}
        ids = [i for i in raw.get("ids", []) if i in by_id]   # a question deleted from the bank leaves the basket too
        items = [self._bank_view(by_id[i]) for i in ids]
        return {"grade_id": by_id[ids[0]]["grade_id"] if ids else "", "ids": ids, "items": items}

    def bank_basket_set(self, b: dict) -> dict:
        ids = []
        for i in b.get("ids") or []:
            if isinstance(i, str) and i not in ids:
                ids.append(i)
        if len(ids) > MAX_EXAM:
            raise AppError("exam_too_big", f"An exam holds {MAX_EXAM} questions at most.", status=409)
        by_id = {e["id"]: e for e in self._bank_data()["questions"]}
        ids = [i for i in ids if i in by_id]
        if len({by_id[i]["grade_id"] for i in ids}) > 1:
            raise AppError("exam_one_grade", "One exam is for one grade.", status=409)
        self._need_store().write_json(self._basket_path(), {"ids": ids})
        return self.bank_basket()

    def bank_exam(self, b: dict) -> dict:
        """Make the quiz file from the basket (or from `ids`), in the order the teacher arranged, then empty the basket."""
        basket = self.bank_basket()
        ids = [str(i) for i in (b.get("ids") or basket["ids"])]
        if not ids:
            raise AppError("bank_empty", "The exam basket is empty. Tick some questions first.", status=404)
        picked = self.bank_pick({"ids": ids})
        grade = next((e["grade_id"] for e in self._bank_data()["questions"] if e["id"] == picked["ids"][0]), "")
        res = self.make_quiz({**b, "grade_id": grade, "text": picked["text"], "bank_ids": picked["ids"]})
        if b.get("clear", True):
            self._need_store().write_json(self._basket_path(), {"ids": []})
        return res

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
