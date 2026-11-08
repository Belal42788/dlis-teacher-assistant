"""The question bank: save questions once, build quizzes from them later."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import nonet

nonet.install()

from app.core import documents as D
from app.core.errors import AppError
from app.core.store import DataStore
from app.server.service import Service

QUIZ = """1. What is the CPU?
a) The brain of the computer
b) A screen
c) A printer
Answer: a

2. Which one is an input device?
a) Mouse
b) Speaker
Answer: a

3. [match] Match the device with its job
Mouse = Pointing
Printer = Printing

4. The ___ stores files permanently.
Answer: hard disk

5. Explain what an operating system does.
"""


class TestQuestionText(unittest.TestCase):
    def test_every_kind_survives_a_round_trip(self):
        qs = D.parse_quiz(QUIZ)
        self.assertEqual([q["type"] for q in qs], ["mcq", "mcq", "match", "fill", "essay"])
        for q in qs:
            again = D.parse_quiz(D.question_to_text(q, 7))
            self.assertEqual(len(again), 1, q["q"])
            for key in ("q", "type", "options", "pairs", "answer"):
                self.assertEqual(again[0][key], q[key], (q["q"], key))


class TestBank(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service()
        self.svc.store = DataStore(Path(self.d.name) / "data")
        self.svc.put_settings({"teacher_name": "T", "subject": "ICT", "setup_done": True})
        self.svc.build_structure({"g4": ["A"], "g5": ["A"]})

    def tearDown(self):
        self.svc.wait_for_backup()
        self.d.cleanup()

    def add(self, text=QUIZ, grade="g4", topic="Hardware", level="medium"):
        return self.svc.bank_add({"grade_id": grade, "topic": topic, "level": level, "text": text})

    def test_add_saves_each_question_once(self):
        self.assertEqual(self.add(), {"added": 5, "skipped": 0, "total": 5})
        r = self.add("1. what is  THE cpu\na) x\nb) y\nAnswer: a\n\n2. A brand new question?\n")
        self.assertEqual((r["added"], r["skipped"]), (1, 1))                      # the same words, not saved again
        self.assertEqual(self.add("1. What is the CPU?\n", grade="g5")["added"], 1)   # another grade is another list
        self.assertEqual(self.svc.bank_list({})["total"], 7)

    def test_wrong_input_is_refused(self):
        for body in ({"grade_id": "nope", "text": QUIZ}, {"grade_id": "g4", "text": ""}, {"grade_id": "g4", "text": QUIZ, "level": "impossible"}):
            with self.assertRaises(AppError):
                self.svc.bank_add(body)
        self.assertEqual(self.svc.bank_list({})["total"], 0)

    def test_list_filters_and_topics(self):
        self.add(topic="Hardware", level="easy")
        self.add("1. What is a network?\n", topic="Networks", level="hard")
        self.add("1. What is an app?\n", grade="g5", topic="Software")
        self.assertEqual(self.svc.bank_list({"grade_id": "g4"})["found"], 6)
        self.assertEqual(self.svc.bank_list({"grade_id": "g4"})["topics"], ["Hardware", "Networks"])
        self.assertEqual(self.svc.bank_list({"topic": "networks"})["found"], 1)
        self.assertEqual(self.svc.bank_list({"level": "easy"})["found"], 5)
        self.assertEqual(self.svc.bank_list({"search": "mouse"})["found"], 2)      # the choice and the matching pair
        item = self.svc.bank_list({"search": "cpu"})["items"][0]
        self.assertEqual((item["type"], item["answer"], len(item["options"])), ("mcq", "a", 3))

    def test_edit_and_delete(self):
        self.add()
        first = self.svc.bank_list({"search": "cpu"})["items"][0]
        out = self.svc.bank_update(first["id"], {"text": "1. What does CPU stand for?\na) Central Processing Unit\nb) Computer Power Unit\nAnswer: a", "level": "hard", "topic": "CPU"})
        self.assertEqual((out["item"]["level"], out["item"]["topic"], out["item"]["q"]), ("hard", "CPU", "What does CPU stand for?"))
        with self.assertRaises(AppError):
            self.svc.bank_update(first["id"], {"text": QUIZ})                      # two questions in one box
        with self.assertRaises(AppError):
            self.svc.bank_update("missing", {"topic": "x"})
        self.assertEqual(self.svc.bank_delete(first["id"])["total"], 4)
        with self.assertRaises(AppError):
            self.svc.bank_delete(first["id"])

    def test_pick_prefers_questions_used_least(self):
        self.add()
        ids = [i["id"] for i in self.svc.bank_list({})["items"]]
        self.svc._bank_mark_used(ids[:3], "Old quiz")
        self.svc._bank_mark_used(ids[:3], "Older quiz")
        for _ in range(8):                                                           # random, but always the two never used
            pick = self.svc.bank_pick({"grade_id": "g4", "count": 2})
            self.assertEqual(set(pick["ids"]), set(ids[3:]))
        pick = self.svc.bank_pick({"ids": [ids[4], ids[0]], "start": 3})            # the ticked ones, in that order, numbered after 3
        self.assertEqual(pick["ids"], [ids[4], ids[0]])
        qs = D.parse_quiz(pick["text"])
        self.assertEqual(len(qs), 2)
        self.assertTrue(pick["text"].startswith("4. ") and "\n\n5. " in pick["text"])
        with self.assertRaises(AppError):
            self.svc.bank_pick({"grade_id": "g5", "count": 3})                       # nothing saved for that grade

    def test_making_a_quiz_remembers_which_saved_questions_it_used(self):
        self.add()
        pick = self.svc.bank_pick({"grade_id": "g4", "count": 3})
        r = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 1, "number": 1, "text": pick["text"], "bank_ids": pick["ids"]})
        self.assertEqual(r["questions"], 3)
        used = {i["id"]: i["used"] for i in self.svc.bank_list({})["items"]}
        self.assertEqual(sorted(used.values()), [0, 0, 1, 1, 1])
        self.assertEqual({i["last_used"] for i in self.svc.bank_list({})["items"] if i["used"]}, {date.today().isoformat()})
        self.svc.export_quiz({"grade_id": "g4", "trimester": 0, "week": 1, "number": 2, "text": pick["text"], "format": "gift", "bank_ids": pick["ids"][:1]})
        self.assertEqual(max(i["used"] for i in self.svc.bank_list({})["items"]), 2)

    def test_the_file_is_in_the_data_folder_and_survives_reopening(self):
        self.add()
        again = Service()
        again.store = DataStore(self.svc.store.root)
        self.assertEqual(again.bank_list({})["total"], 5)
        self.assertTrue((self.svc.store.root / "question_bank.json").is_file())


if __name__ == "__main__":
    unittest.main()
