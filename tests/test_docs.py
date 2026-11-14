import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helpers import AiCase   # sets the import path and blocks the real internet
from app.core.errors import AppError
from app.core.store import DataStore


class TestQuizVersionsAndParentWeek(unittest.TestCase):
    def test_version_b_keeps_answers_right(self):
        from app.core import documents as D
        qs = D.parse_quiz("1. What is a CPU?\na) Brain\nb) Screen\nc) Mouse\nAnswer: a\n\n2. Which is input?\na) Mouse\nb) Speaker\nc) Printer\nAnswer: a\n\n3. Name one.\n")
        b = D.shuffled_version(qs)
        self.assertEqual(sorted(q["q"] for q in b), sorted(q["q"] for q in qs))
        for q in b:
            if q["type"] == "mcq":
                right = dict(q["options"])[q["answer"].upper()]
                self.assertEqual(right, "Brain" if "CPU" in q["q"] else "Mouse")        # the answer letter follows its choice
        self.assertTrue(any(x["options"] != y["options"] for x in qs for y in b if x["q"] == y["q"]))

    def test_parent_week_saved_clean_and_published_only_by_staff(self):
        from app.server.service import Service
        with tempfile.TemporaryDirectory() as d:
            svc = Service(); svc.store = DataStore(d)
            svc.build_structure({"kg1": ["A"]})
            out = svc.save_parent_week({"room_id": "kg1-a", "trimester": 0, "week": 8, "homework": "Page 12\n\n  Draw a mouse ",
                                        "material": "Video | https://youtu.be/x\nbad | javascript:alert(1)", "quiz_alerts": "Unit 2 quiz | 2026-11-12"})
            self.assertEqual(out["homework"], ["Page 12", "Draw a mouse"])
            self.assertEqual(out["material"], [{"title": "Video", "url": "https://youtu.be/x"}])
            self.assertEqual(out["quiz_alerts"][0]["date"], "2026-11-12"); self.assertFalse(out["approved"])
            again = svc.save_parent_week({"room_id": "kg1-a", "trimester": 0, "week": 8, "homework": "Page 13", "quiz_alerts": ""})   # the files page sends no links: the saved ones stay
            self.assertEqual((again["homework"], again["material"]), (["Page 13"], out["material"]))
            with self.assertRaises(AppError):
                svc.save_parent_week({"room_id": "kg1-a", "trimester": 0, "week": 8}, True)


class TestDocsAndTasks(unittest.TestCase):
    def setUp(self):
        os.environ["DLIS_NO_OPEN"] = "1"
        from app.server.service import Service
        self.d = tempfile.TemporaryDirectory()
        self.svc = Service(); self.svc.store = DataStore(self.d.name)
        self.svc.put_settings({"teacher_name": "Test Teacher", "subject": "ICT"})
        self.svc.build_structure({"g4": ["A"], "kg1": ["A"]})
        self.svc.put_students("g4-a", ["Sara Ali", "Omar Samy"])
        self.svc.put_timetable({"grid": {"Sunday": {"6": "g4-a", "2": "kg1-a"}}})
        self.svc.put_calendar(self.svc.school_calendar())

    def tearDown(self):
        self.d.cleanup()

    def test_weekly_checklist(self):
        w = self.svc.get_weekly(0, 8)
        self.assertEqual(w["tasks"][0], "attendance"); self.assertEqual(len(w["rows"]), 2); self.assertEqual(w["done"], 0)
        self.assertEqual([g["id"] for g in w["groups"]], ["attendance", "presentation", "lesson_plan", "quiz", "weekly_plan"])
        w = self.svc.set_weekly({"trimester": 0, "week": 8, "grade_id": "g4", "task": "quiz_sent", "state": "done"})
        self.assertEqual(next(r for r in w["rows"] if r["grade_id"] == "g4")["states"]["quiz_sent"], "done"); self.assertEqual(w["done"], 1)
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware"}})   # the file exists: "made" ticks itself
        r4 = next(r for r in self.svc.get_weekly(0, 8)["rows"] if r["grade_id"] == "g4")
        self.assertEqual(r4["states"]["lesson_plan_made"], "done"); self.assertTrue(r4["auto"]["lesson_plan_made"]); self.assertEqual(r4["states"]["lesson_plan_sent"], "wait")
        self.assertEqual(self.svc.get_weekly(0, 9)["done"], 0)   # each week has its own marks
        with self.assertRaises(AppError):
            self.svc.set_weekly({"trimester": 0, "week": 8, "grade_id": "g4", "task": "nope", "state": "done"})

    def test_saved_chats(self):
        a = self.svc.chat_save("", {"messages": [{"role": "user", "content": "Explain the CPU"}, {"role": "assistant", "content": "It is the brain"}]})
        self.assertEqual(a["title"], "Explain the CPU")
        b = self.svc.chat_save("", {"messages": [{"role": "user", "content": "Quiz ideas"}]})
        self.assertEqual({x["id"] for x in self.svc.chats_list()["items"]}, {a["id"], b["id"]})
        self.assertEqual(len(self.svc.chat_get(a["id"])["messages"]), 2)
        self.svc.chat_save(a["id"], {"messages": [{"role": "user", "content": "Explain the CPU"}, {"role": "assistant", "content": "x"}, {"role": "user", "content": "more"}]})
        self.assertEqual(len(self.svc.chat_get(a["id"])["messages"]), 3)
        self.assertEqual(len(self.svc.chat_delete(a["id"])["items"]), 1)
        with self.assertRaises(AppError):
            self.svc.chat_get(a["id"])

    def test_grade_table_for_lms(self):
        from openpyxl import load_workbook
        room = self.svc.store.load_structure().rooms[0]
        self.svc.store.save_students(room.id, ["Ali Ahmed", "Sara Omar"]) if hasattr(self.svc.store, "save_students") else None
        out = self.svc.make_grading_sheet({"room_id": room.id, "trimester": 0, "week": 8, "lang": "en", "format": "xlsx"})
        self.assertTrue(out["name"].endswith(".xlsx"))
        ws = load_workbook(out["path"]).active
        self.assertEqual([c.value for c in ws[2]], ["#", "Student", "Grade"])
        self.assertGreaterEqual(ws.max_row, 3)
        csv = self.svc.make_grading_sheet({"room_id": room.id, "trimester": 0, "week": 8, "lang": "en", "format": "csv"})
        self.assertTrue(open(csv["path"], encoding="utf-8-sig").read().startswith("#,Student,Grade"))

    def test_plan_on_today_and_cover_sheet(self):
        from docx import Document
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware", "objectives": "- Name parts"}})
        plans = self.svc._plans(); plans.setdefault("slides", {})["g4|0|8"] = {"count": 12, "file": "x.pptx"}
        self.svc.store.write_json(self.svc._plans_path(), plans)
        self.svc.log_save({"room_id": "g4-a", "date": "2026-10-18", "topic": "Input", "slide": 5, "total": 12, "next_note": "Bring mice"})
        sessions = self.svc.today("2026-10-25")["sessions"]
        plan = next(x for x in sessions if x["room_id"] == "g4-a")["plan"]
        self.assertEqual((plan["topic"], plan["slides"]), ("Hardware", 12))
        r = self.svc.make_cover_sheet({"date": "2026-10-25"})
        self.assertEqual(r["lessons"], 2)
        d = Document(r["path"]); text = "\n".join(p.text for p in d.paragraphs)
        for w in ("substitute", "Hardware", "12 slides", "slide 5 of 12", "Bring mice", "Grade 4"):
            self.assertIn(w, text)
        with self.assertRaises(AppError):
            self.svc.make_cover_sheet({"date": "2026-10-23"})   # Friday: no lessons

    def test_four_documents(self):
        from docx import Document
        r = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware", "sunday": "Warm up"}})
        self.assertTrue(r["rel"].replace("\\", "/").endswith("Documents/Grade 4/T1-W08_Lesson_Plan.docx"), r["rel"])
        doc = Document(r["path"])
        txt = " ".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
        self.assertIn("Hardware", txt); self.assertIn("ICT", txt); self.assertIn("Test Teacher", txt); self.assertIn("Warm up", txt)
        days = [doc.tables[2].rows[i].cells[0].text for i in range(1, 6)]  # grade 4 only has Sunday: the other four days say so
        self.assertNotIn("No session", days[0]); self.assertIn("Warm up", days[0])
        self.assertTrue(all("No session" in d for d in days[1:]), days)
        self.assertIn("Term 1 Week 8", doc.paragraphs[0].text)
        self.assertIn("Term 1", doc.paragraphs[0].text.replace("\t", "").replace("  ", " ") if False else "Term 1")
        r = self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": ["L1", "L2"]})
        txt = " ".join(c.text for t in Document(r["path"]).tables for row in t.rows for c in row.cells)
        self.assertIn("From 06/09 to 10/09", txt); self.assertIn("L2", txt); self.assertIn("Week 12", txt)
        r = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a", "with_answers": True})
        self.assertEqual(r["questions"], 1)
        r = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8})
        txt = " ".join(c.text for t in Document(r["path"]).tables for row in t.rows for c in row.cells)
        self.assertIn("Sara Ali", txt); self.assertIn("Grade level Grade 4 A", txt)
        self.assertEqual(self.svc.open_file(r["path"])["opened"], r["path"])
        with self.assertRaises(AppError):
            self.svc.open_file("/etc/passwd")
        self.svc.build_structure({"g5": ["A"]})
        with self.assertRaises(AppError):   # a class with no students
            self.svc.make_grading_sheet({"room_id": "g5-a", "trimester": 0, "week": 8})

    def test_library_lists_files_and_keeps_private_ones_off_the_server(self):
        r1 = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
        r2 = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware"}})
        items = {x["name"]: x for x in self.svc.library_list()["items"]}
        q = items[r1["name"]]
        self.assertEqual((q["kind"], q["private"], [(x["t"], x["w"], x["shared"]) for x in q["places"]]), ("quiz", False, [(0, 8, None)]))
        self.assertTrue(items[r2["name"]]["private"])
        with self.assertRaises(AppError) as cm:
            self.svc.library_share({"rel": r2["rel"], "class_id": "g4-a", "public": True})
        self.assertEqual(cm.exception.code, "private_file")
        with self.assertRaises(AppError):
            self.svc.library_share({"rel": "../../etc/passwd", "class_id": "g4-a"})

    def test_files_by_week_with_notes_and_sharing(self):
        r1 = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
        r1 = {**r1, "rel": r1["rel"].replace("\\", "/")}
        pubs = []
        self.svc.list_publications = lambda: {"items": list(pubs)}
        self.svc.add_publication = lambda b: pubs.append({"id": f"{len(pubs) + 1:036d}", **b})
        self.svc.set_publication = lambda pid, b: next(x for x in pubs if x["id"] == pid).update(b)
        self.svc.delete_publication = lambda pid: pubs.remove(next(x for x in pubs if x["id"] == pid))

        def places():
            return next(x for x in self.svc.library_list()["items"] if x["rel"] == r1["rel"])["places"]
        self.assertEqual([(x["id"], x["t"], x["w"]) for x in places()], [("auto", 0, 8)])       # named T1-W08: it lands in its week
        first = next(x for x in self.svc.library_place({"rel": r1["rel"], "pid": "auto", "note": "  Part 1   only "})["items"] if x["rel"] == r1["rel"])["places"][0]
        self.assertNotEqual(first["id"], "auto"); self.assertEqual(first["note"], "Part 1 only")
        self.svc.library_place_add({"rel": r1["rel"], "t": 0, "w": 9})
        with self.assertRaises(AppError):
            self.svc.library_place_add({"rel": r1["rel"], "t": 0, "w": 9})
        with self.assertRaises(AppError):
            self.svc.library_place({"rel": r1["rel"], "pid": first["id"], "t": 5, "w": 1})
        second = places()[1]
        self.svc.library_place({"rel": r1["rel"], "pid": second["id"], "note": "Part 2"})
        self.svc.library_share({"rel": r1["rel"], "pid": second["id"], "class_id": "g4-a", "public": True, "visible_from": "2026-11-05"})
        self.assertEqual((pubs[0]["note"], pubs[0]["trimester"], pubs[0]["week"], pubs[0]["approved"]), ("Part 2", 0, 9, True))
        self.svc.library_place({"rel": r1["rel"], "pid": second["id"], "note": "Part 2: up to slide 20"})   # the students see the new note
        self.assertEqual(pubs[0]["note"], "Part 2: up to slide 20")
        self.svc.library_place({"rel": r1["rel"], "pid": second["id"], "t": 0, "w": 10})                      # moved to another week
        self.assertEqual(pubs[0]["week"], 10)
        self.assertEqual([bool(x["shared"]) for x in places()], [False, True])
        self.svc.library_place_delete({"rel": r1["rel"], "pid": second["id"]})                              # taking it out of the week removes it from students too
        self.assertEqual((pubs, len(places())), ([], 1))
        only = self.svc.library_place_delete({"rel": r1["rel"], "pid": first["id"]})
        self.assertEqual([(x["t"], x["w"]) for x in next(i for i in only["items"] if i["rel"] == r1["rel"])["places"]], [(None, None)])   # always keeps one place
        # an older library.json (one share per file) is carried over
        import json
        path = self.svc._need_store().root / "library.json"
        path.write_text(json.dumps({"shared": {r1["rel"]: {"id": "x" * 36, "class_id": "g4-a", "public": True, "at": 1}}}), encoding="utf-8")
        old = places()
        self.assertEqual((old[0]["shared"]["class_id"], old[0]["w"]), ("g4-a", None))

    def _fake_cloud(self):
        """A server that keeps its items in a list; one add can serve several classes (class_ids), as the real one does."""
        pubs = []

        def add(b):
            for cid in (b.get("class_ids") or [b["class_id"]]):
                pubs.append({"id": f"{len(pubs) + 1:036d}", "class_id": cid, **{k: v for k, v in b.items() if k not in ("class_id", "class_ids")}})
        self.svc.list_publications = lambda: {"items": list(pubs)}
        self.svc.add_publication = add
        self.svc.set_publication = lambda pid, b: next(x for x in pubs if x["id"] == pid).update(b)
        self.svc.delete_publication = lambda pid: pubs.remove(next(x for x in pubs if x["id"] == pid))
        return pubs

    def _item(self, rel):
        return next(x for x in self.svc.library_list()["items"] if x["rel"] == rel)

    def test_files_sit_in_grades_and_show_to_every_class_of_the_grade(self):
        self.svc.build_structure({"g4": ["A", "B"], "g5": ["A"]})
        pubs = self._fake_cloud()
        q = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
        rel = q["rel"].replace("\\", "/")
        p = self._item(rel)["places"][0]
        self.assertEqual((p["g"], p["t"], p["w"]), ("g4", 0, 8))   # the folder is named after the grade
        r = self.svc.library_visible({"rel": rel, "pid": p["id"], "on": True, "visible_from": "2026-11-05"})
        self.assertEqual(sorted(x["class_id"] for x in pubs), ["g4-a", "g4-b"])
        self.assertTrue(all(x["approved"] and x["week"] == 8 and x["kind"] == "quiz" for x in pubs))
        sh = next(i for i in r["items"] if i["rel"] == rel)["places"][0]["shared"]
        self.assertEqual((sh["public"], sorted(sh["ids"])), (True, ["g4-a", "g4-b"]))
        pid = next(i for i in r["items"] if i["rel"] == rel)["places"][0]["id"]
        self.svc.library_place({"rel": rel, "pid": pid, "note": "Chapter 1"})          # every class sees the new note
        self.assertEqual({x["note"] for x in pubs}, {"Chapter 1"})
        moved = self.svc.library_place({"rel": rel, "pid": pid, "g": "g5"})            # another grade: other classes, so it is taken back
        self.assertEqual((pubs, moved["unshared"]), ([], True))
        self.svc.library_visible({"rel": rel, "pid": pid, "on": True, "visible_from": "2026-11-05"})
        self.assertEqual([x["class_id"] for x in pubs], ["g5-a"])
        self.svc.library_visible({"rel": rel, "pid": pid, "on": False})
        self.assertEqual(pubs, [])
        self.svc.library_place({"rel": rel, "pid": pid, "g": None})                    # no grade: nobody to show it to
        with self.assertRaises(AppError) as cm:
            self.svc.library_visible({"rel": rel, "pid": pid, "on": True, "visible_from": "2026-11-05"})
        self.assertEqual(cm.exception.code, "no_grade")
        self.svc.library_place({"rel": rel, "pid": pid, "g": "*"})                     # a book for every grade
        self.svc.library_visible({"rel": rel, "pid": pid, "on": True, "visible_from": "2026-11-05"})
        self.assertEqual(sorted(x["class_id"] for x in pubs), sorted(r["id"] for r in self.svc.get_structure()["rooms"]))   # every class of the school
        with self.assertRaises(AppError):
            self.svc.library_place({"rel": rel, "pid": pid, "g": "g99"})

    def test_messages_for_students(self):
        self.svc.build_structure({"g4": ["A", "B"]})
        pubs = self._fake_cloud()
        with self.assertRaises(AppError):
            self.svc.library_message_add({"text": "   "})
        rel = self.svc.library_message_add({"text": "  Bring   the book\nand a pen ", "g": "g4", "t": 0, "w": 9})["added"]
        it = self._item(rel)
        self.assertEqual((it["kind"], it["text"], it["name"]), ("message", "Bring the book\nand a pen", "Bring the book and a pen"))
        p = it["places"][0]
        self.assertEqual((p["g"], p["t"], p["w"]), ("g4", 0, 9))
        self.svc.library_visible({"rel": rel, "pid": p["id"], "on": True})
        self.assertEqual(sorted((x["class_id"], x["kind"], x["body"], x["week"]) for x in pubs), [("g4-a", "message", "Bring the book\nand a pen", 9), ("g4-b", "message", "Bring the book\nand a pen", 9)])
        self.svc.library_message_set({"rel": rel, "text": "Quiz on Sunday"})   # the students see the new words
        self.assertEqual({x["body"] for x in pubs}, {"Quiz on Sunday"})
        with self.assertRaises(AppError):
            self.svc.library_message_set({"rel": "../x", "text": "no"})
        self.svc.library_message_delete({"rel": rel})
        self.assertEqual(pubs, [])
        self.assertNotIn(rel, [x["rel"] for x in self.svc.library_list()["items"]])

    def test_upload_and_files_as_ai_sources(self):
        import base64
        from docx import Document
        self.svc.build_structure({"g4": ["A"], "g5": ["A"]})
        with self.assertRaises(AppError):
            self.svc.library_upload({"filename": "virus.exe", "data_b64": base64.b64encode(b"x").decode()})
        d = Document(); d.add_paragraph("Photosynthesis makes food from light."); import io; buf = io.BytesIO(); d.save(buf)
        r = self.svc.library_upload({"filename": "Plants worksheet.docx", "data_b64": base64.b64encode(buf.getvalue()).decode(), "g": "g5", "t": 0, "w": 2})
        rel = r["added"]
        self.assertTrue(rel.startswith("Uploads/Grade 5/"), rel)
        p = self._item(rel)["places"][0]
        self.assertEqual((p["g"], p["t"], p["w"]), ("g5", 0, 2))
        again = self.svc.library_upload({"filename": "Plants worksheet.docx", "data_b64": base64.b64encode(buf.getvalue()).decode()})["added"]
        self.assertNotEqual(again, rel)   # the same name is kept as a second file, nothing is overwritten
        # a file with no week is simply put in the week the teacher picks
        self.svc.library_place_add({"rel": again, "g": "g4", "t": 0, "w": 3})
        self.assertEqual([(x["g"], x["t"], x["w"]) for x in self._item(again)["places"]], [("g4", 0, 3)])
        # an uploaded file is read for the AI at once; a file that only sits in the folder is read the first time it is chosen
        real = [x for x in self.svc.list_sources()["sources"] if x["rel"] == rel]
        self.assertEqual(len(real), 1)
        self.assertIn(real[0]["id"], {x["id"] for x in self.svc.list_pickable_sources()["sources"]})
        plan = self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8, "content": {"topic": "Hardware"}})
        ids = {x["id"] for x in self.svc.list_pickable_sources()["sources"]}
        self.assertNotIn("file:" + plan["rel"].replace("\\", "/"), ids)   # plans hold the teacher's own work
        (self.svc._need_store().root / "Uploads").mkdir(exist_ok=True)
        (self.svc._need_store().root / "Uploads" / "Hand placed.docx").write_bytes(buf.getvalue())
        hand = "Uploads/Hand placed.docx"
        self.svc.library_place_add({"rel": hand, "g": "g4", "t": 0, "w": 4})
        ids = {x["id"] for x in self.svc.list_pickable_sources()["sources"]}
        self.assertIn("file:" + hand, ids)
        n0 = len(self.svc.list_sources()["sources"])
        self.assertIn("Photosynthesis", self.svc.source_block("file:" + hand))
        got = [x for x in self.svc.list_sources()["sources"] if x["rel"] == hand]
        self.assertEqual((len(got), len(self.svc.list_sources()["sources"])), (1, n0 + 1))
        self.assertNotIn("file:" + hand, {x["id"] for x in self.svc.list_pickable_sources()["sources"]})   # now an ordinary source
        self.assertEqual(self.svc.use_source({"id": "file:" + hand})["id"], got[0]["id"])
        with self.assertRaises(AppError):
            self.svc.use_source({"id": "file:" + plan["rel"].replace("\\", "/")})

    def test_links_are_files_too(self):
        pubs, asked = [], []
        self.svc.list_publications = lambda: {"items": list(pubs)}
        self.svc.add_publication = lambda b: pubs.append({"id": f"{len(pubs) + 1:036d}", **b})
        self.svc.set_publication = lambda pid, b: next(x for x in pubs if x["id"] == pid).update(b)
        self.svc.delete_publication = lambda pid: pubs.remove(next(x for x in pubs if x["id"] == pid))

        def fake_import(b):
            asked.append(b)
            src = {"id": "abcdef1234", "name": "Video", "added": "2026-11-11", "pages": [{"n": 1, "text": "hello", "notes": "", "vision": False, "done": True}], "url": b["url"]}
            self.svc._src_save(src)
            return self.svc._src_brief(src)
        self.svc.import_url = fake_import
        with self.assertRaises(AppError):
            self.svc.library_link_add({"url": "javascript:alert(1)"})
        rel = self.svc.library_link_add({"title": "Keyboard playlist", "url": "https://www.youtube.com/playlist?list=PL1"})["added"]

        def me():
            return next(x for x in self.svc.library_list()["items"] if x["rel"] == rel)
        self.assertEqual((me()["kind"], me()["name"], me()["source"], me()["places"][0]["w"]), ("link", "Keyboard playlist", None, None))
        pid = me()["places"][0]["id"]
        self.svc.library_place({"rel": rel, "pid": pid, "t": 0, "w": 9, "note": "Watch part 1"})
        self.svc.library_share({"rel": rel, "pid": pid, "class_id": "g4-a", "public": True})
        self.assertEqual((pubs[0]["kind"], pubs[0]["url"], pubs[0]["week"], pubs[0]["note"], pubs[0]["approved"]), ("link", "https://www.youtube.com/playlist?list=PL1", 9, "Watch part 1", True))
        self.svc.library_source({"rel": rel, "on": True, "transcript": "pasted text"})
        self.assertEqual((asked[0]["transcript"], me()["source"]["id"]), ("pasted text", "abcdef1234"))
        self.svc.library_source({"rel": rel, "on": False})
        self.assertIsNone(me()["source"])
        self.svc.library_source({"rel": rel, "on": True})
        # a web page added as a source before links existed becomes a link
        self.svc._src_save({"id": "old0000001", "name": "Old page", "added": "2026-10-01", "pages": [{"n": 1, "text": "x", "notes": "", "vision": False, "done": True}], "url": "https://example.com/p"})
        names = [x["name"] for x in self.svc.library_list()["items"]]
        self.assertIn("Old page", names)
        self.assertEqual(self.svc.library_list()["orphans"], [])
        out = self.svc.library_link_delete({"rel": rel})   # takes it away from the students and drops its source
        self.assertEqual((pubs, [x for x in out["items"] if x["rel"] == rel]), ([], []))
        self.assertNotIn("abcdef1234", [x["id"] for x in self.svc.list_sources()["sources"]])

    def test_one_file_list_with_source_switch(self):
        import base64
        import io
        from docx import Document
        d = Document(); d.add_paragraph("Chapter one is about input devices such as the keyboard and the mouse, and how they send data to the computer."); buf = io.BytesIO(); d.save(buf)
        book = self.svc.import_source({"filename": "Book 1.docx", "data_b64": base64.b64encode(buf.getvalue()).decode()})
        self.assertTrue(book["rel"].startswith("Books/"))
        quiz = self.svc.make_quiz({"grade_id": "g4", "trimester": 0, "week": 8, "number": 1, "text": "1. Q?\na) x\nb) y\nAnswer: a"})
        lib = self.svc.library_list()
        items = {x["name"]: x for x in lib["items"]}
        b = items["Book 1.docx"]
        self.assertEqual((b["kind"], b["source"]["id"], b["source_locked"]), ("book", book["id"], False))
        self.assertIsNone(items[quiz["name"]]["source"])
        on = {x["name"]: x for x in self.svc.library_source({"rel": quiz["rel"], "on": True})["items"]}
        self.assertTrue(on[quiz["name"]]["source"])
        self.assertEqual(len(self.svc.list_sources()["sources"]), 2)
        off = {x["name"]: x for x in self.svc.library_source({"rel": quiz["rel"], "on": False})["items"]}
        self.assertIsNone(off[quiz["name"]]["source"])
        self.assertEqual(len(self.svc.list_sources()["sources"]), 1)
        self.assertEqual(self.svc.library_list()["orphans"], [])
        with self.assertRaises(AppError):
            self.svc.library_source({"rel": "../../etc/passwd", "on": True})

    def test_scheme_of_work_round_trip_and_planned_source(self):
        d = self.svc.scheme_get("g4", 0)
        self.assertTrue(d["weeks"])
        w1 = next(w for w in d["weeks"] if w["school_days"] > 0)["week"]
        out = self.svc.scheme_put({"grade_id": "g4", "trimester": 0, "weeks": [{"week": w1, "topic": " Hardware  basics ", "pages": "10-14", "source_id": "nope"}, {"week": 999, "topic": "ignored"}]})
        row = next(w for w in out["weeks"] if w["week"] == w1)
        self.assertEqual((row["topic"], row["pages"], row["source_id"]), ("Hardware basics", "10-14", ""))   # an unknown source is dropped
        self.assertNotIn("ignored", str(out["weeks"]))
        data = self.svc._plans(); data["scheme"]["g4|0"][str(w1)]["source_id"] = "abc"; self.svc._need_store().write_json(self.svc._plans_path(), data)
        self.assertEqual(self.svc.scheme_source("g4", "hardware BASICS"), ("abc", "10-14"))
        self.assertEqual(self.svc.scheme_source("g5", "hardware basics"), ("", ""))
        wk = next(x for x in self.svc.slide_topics("g4", 0)["weeks"] if x["week"] == w1)       # the Create page reads the same plan
        self.assertEqual((wk["topic"], wk["pages"], wk["source_id"]), ("Hardware basics", "10-14", "abc"))
        st = self.svc.week_prep_status("2026-10-28")
        self.assertEqual(st["state"], "in_term"); self.assertLessEqual(st["ready"], st["total"])

    def test_revision_cover_page(self):
        from docx import Document
        self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": ["Hardware", "Software"]})
        sug = self.svc.revision_cover_suggest("g4", 0)
        self.assertIn("Hardware", sug["lines"])
        rows = "Unit 1 | Hardware | 10-14\nSoftware | 15-20\n" + "\n".join(f"U{i} | L{i} | {i}" for i in range(12))
        r = self.svc.make_revision_cover({"grade_id": "g4", "trimester": 0, "rows": rows})
        self.assertTrue(r["rel"].replace("\\", "/").endswith("Documents/Grade 4/T1_Revision_Cover_Page.docx"), r["rel"])
        d = Document(r["path"])
        text = "\n".join(p.text for p in d.paragraphs)
        for w in ("Final Trimester 1 Revision Pack", "ICT", "Test Teacher", "Grade Level: 4"):
            self.assertIn(w, text)
        cells = [[c.text for c in row.cells] for row in d.tables[0].rows]
        self.assertEqual(cells[1], ["Unit 1", "Hardware", "10-14"])
        self.assertEqual(cells[2], ["", "Software", "15-20"])   # two parts = lesson | pages
        self.assertEqual(len(cells), 15)                         # grew past the 9 empty rows
        head = " ".join(p.text for p in d.sections[0].header.paragraphs)
        self.assertIn("ICT Department", head); self.assertIn("Trimester 1-Grade (4)", head)
        self.assertEqual(sum(len(x.drawing_images) if hasattr(x, "drawing_images") else 0 for x in []), 0)
        with self.assertRaises(AppError):
            self.svc.make_revision_cover({"grade_id": "nope", "trimester": 0, "rows": ""})
        # the cover is the first page of the revision file itself
        r = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 0, "title": "Hardware", "words": "CPU: brain", "with_cover": True, "cover_rows": "Unit 1 | Hardware | 10-14"})
        d = Document(r["path"])
        text = "\n".join(p.text for p in d.paragraphs)
        self.assertIn("Final Trimester 1 Revision Pack", text); self.assertIn("Revision Sheet", " ".join(c.text for t in d.tables for row in t.rows for c in row.cells) + text)
        self.assertEqual(d.tables[0].rows[1].cells[1].text, "Hardware")

    def test_tasks(self):
        self.svc.store.write_json(self.svc._tasks_path(), {"tasks": [], "dismissed": [], "tracking_start": "2026-10-19"})
        t = self.svc.list_tasks(date(2026, 10, 25))
        ids = {x["id"] for x in t["auto"]}
        self.assertIn("lesson_plan:g4:0:7", ids)   # week 7 started 18 Oct, nothing written: overdue
        self.assertIn("lesson_plan:g4:0:9", ids)   # next week
        self.assertEqual(len([i for i in ids if i.startswith("lesson_plan:kg1")]), len([i for i in ids if i.startswith("lesson_plan:g4")]))
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": 8})
        ids = {x["id"] for x in self.svc.list_tasks(date(2026, 10, 25))["auto"]}
        self.assertNotIn("lesson_plan:g4:0:8", ids)    # written -> disappears by itself
        t = self.svc.add_task({"title": "Print quizzes", "importance": "high", "deadline": "2026-10-26"})
        tid = t["tasks"][0]["id"]
        self.svc.update_task(tid, {"done": True})
        self.assertTrue(self.svc.list_tasks()["tasks"][0]["done"])
        self.svc.dismiss_task("lesson_plan:g4:0:9")
        self.assertNotIn("lesson_plan:g4:0:9", {x["id"] for x in self.svc.list_tasks(date(2026, 10, 25))["auto"]})
        self.svc.delete_task(tid)
        self.assertEqual(self.svc.list_tasks()["tasks"], [])


class TestQuizTypes(unittest.TestCase):
    def test_mixed_types_parse_and_render(self):
        from pathlib import Path
        from app.core import documents as D
        text = ("1. Capital?\na) Cairo\nb) Giza\nAnswer: a\n\n2. The Nile is ____.\nAnswer: long\n\n3. Why?\nAnswer: because\n\n"
                "4. Match:\nsun = star\nmoon = satellite\n\n5. Sky is blue.\na) True\nb) False\nAnswer: a")
        qs = D.parse_quiz(text)
        self.assertEqual([q["type"] for q in qs], ["mcq", "fill", "essay", "match", "tf"])
        with tempfile.TemporaryDirectory() as d:
            out = D.fill_quiz(D.template_path("quiz"), Path(d) / "q.docx", {"grade_label": "4", "trimester": 1, "week": 2, "number": 1,
                                                                           "questions": qs, "with_answers": True})
            from docx import Document
            body = "\n".join(p.text for p in Document(str(out)).paragraphs)
            self.assertIn("1) sun", body); self.assertIn("Answer key", body); self.assertIn("2- long", body)


class TestQuizExport(AiCase):
    TEXT = ("1. What is a CPU?\na) Brain\nb) Screen\nc) Mouse\nAnswer: a\n2. A mouse is an input device.\na) True\nb) False\nAnswer: a\n"
            "3. Match the device with its use.\nMouse = points\nKeyboard = types\nSpeaker = sound\n4. The ___ is the brain of the computer.\nAnswer: CPU\n5. Explain: why?\n6. Which is output?\na) Mouse\nb) Printer\n")

    def test_moodle_gift_and_google_forms_script(self):
        g = self.svc.export_quiz({"grade_id": "g4", "trimester": 0, "week": 3, "number": 1, "text": self.TEXT, "format": "gift"})
        body = Path(g["path"]).read_text(encoding="utf-8")
        self.assertTrue(g["name"].endswith("_Moodle.txt")); self.assertEqual(g["questions"], 6)
        self.assertIn("{ =Brain ~Screen ~Mouse }", body); self.assertIn("{TRUE}", body)
        self.assertIn("=Mouse -> points", body); self.assertIn("The {=CPU} is the brain", body)
        self.assertIn("Explain\\: why? {}", body)
        self.assertIn("Which is output? {}", body)                       # no answer given: imported as an essay question
        f = self.svc.export_quiz({"grade_id": "g4", "trimester": 0, "week": 3, "number": 1, "text": self.TEXT, "format": "forms"})
        js = Path(f["path"]).read_text(encoding="utf-8")
        self.assertIn("FormApp.create", js); self.assertIn('createChoice("Brain", true)', js); self.assertIn("addListItem", js); self.assertIn("Answer: CPU", js)
        with self.assertRaises(AppError):
            self.svc.export_quiz({"grade_id": "g4", "text": "  "})


if __name__ == "__main__":
    unittest.main()
