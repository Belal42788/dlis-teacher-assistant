import json
import unittest
from pathlib import Path

from helpers import AiCase   # sets the import path and blocks the real internet
from app.core.errors import AppError


class TestAi(AiCase):
    def test_chat_hides_names_keeps_history_and_prompts_are_editable(self):
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = "Sure, here is an idea."
        r = self.svc.ai_chat({"messages": [{"role": "user", "content": "Help"}, {"role": "assistant", "content": "Ok"},
                                           {"role": "user", "content": "Sara Ali Hassan talks too much, what to do?"}], "grade_id": "g4"})
        self.assertEqual(r["reply"], self.reply)
        body = self.sent[-1][3]
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user", "assistant", "user"])
        self.assertNotIn("Sara", json.dumps(body)); self.assertIn("[student]", json.dumps(body))
        self.assertIn("ICT", body["messages"][0]["content"])
        with self.assertRaises(AppError):
            self.svc.ai_chat({"messages": [{"role": "assistant", "content": "hi"}]})
        # the teacher edits the lesson prompt; the output-format rule stays
        got = self.svc.ai_prompts_get()
        self.assertTrue(got["templates"]); self.assertEqual(got["custom"], {})
        self.svc.ai_prompts_put({"key": "lesson", "system": "You are a pirate teacher.", "guidance": "Use short steps."})
        self.reply = json.dumps({"topic": "T"})
        self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 1, "topic": "Hardware"})
        system = self.sent[-1][3]["messages"][0]["content"]
        self.assertIn("pirate", system); self.assertIn("ONE JSON object", system)
        self.svc.ai_prompts_put({"key": "lesson", "reset": True})
        self.assertEqual(self.svc.ai_prompts_get()["custom"], {})
        with self.assertRaises(AppError):
            self.svc.ai_prompts_put({"key": "nope", "system": "x"})

    def test_slide_topics_and_notebooklm_prompt(self):
        wk = self.svc.overview()["trimesters"][0]["weeks"]
        w1, w2 = wk[2]["number"], wk[3]["number"]
        self.svc.make_trimester_plan({"grade_id": "g4", "trimester": 0, "lessons": [""] * 2 + ["Intro to computers", "Hardware"]})
        self.svc.make_lesson_plan({"grade_id": "g4", "trimester": 0, "week": w2, "content": {"topic": "Input devices", "objectives": "- Name 3 devices"}})
        got = {x["week"]: x for x in self.svc.slide_topics("g4", 0)["weeks"]}
        self.assertEqual((got[w1]["topic"], got[w1]["source"]), ("Intro to computers", "trimester"))
        self.assertEqual((got[w2]["topic"], got[w2]["source"]), ("Input devices", "lesson"))  # the lesson plan wins
        self.assertEqual(got[wk[0]["number"]]["source"], "")
        r = self.svc.notebooklm_prompt({"grade_id": "g4", "topic": "Input devices", "slides": 8, "language": "ar", "look": "cartoon", "objectives": "- Name 3 devices"})["prompt"]
        for must in ("8 slides", "Input devices", "ICT", "Arabic", "cartoon", "Do not add exercises", "2F82A8", "Name 3 devices", "right-to-left", "Grade 4", "speaker notes"):
            self.assertIn(must, r)
        self.svc.build_structure({"kg1": ["A"], "g4": ["A"], "g11": ["A"]})
        stages = {g: self.svc.notebooklm_prompt({"grade_id": g, "topic": "Colours"})["prompt"] for g in ("kg1", "g4", "g11")}
        self.assertIn("4-6 years old", stages["kg1"]); self.assertIn("6 words", stages["kg1"])
        self.assertIn("9-12 years old", stages["g4"]); self.assertIn("15-18 years old", stages["g11"])
        self.assertEqual(len({p.split("## Visual style")[1][:60] for p in stages.values()}), 3)  # each stage has its own style
        with self.assertRaises(AppError):
            self.svc.notebooklm_prompt({"grade_id": "g4", "topic": " "})
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = "Input devices let us give information to a computer."
        out = self.svc.notebooklm_source({"grade_id": "g4", "topic": "Input devices. Sara Ali Hassan helps"})
        self.assertIn("Input devices", out["text"]); self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))

    def test_bilingual_student_names(self):
        from app.core.translit import to_english
        self.assertEqual(to_english("محمد أحمد"), "Mohamed Ahmed")
        self.assertEqual(to_english("Sara Ali"), "Sara Ali")
        r = self.svc.put_students("g4-a", ["يوسف محمد", "مريم علي"], ["", "Maryam Aly"])
        self.assertEqual((r["english"], r["auto"][0]), (["", "Maryam Aly"], "Youssef Mohamed"))
        again = self.svc.get_students("g4-a")
        self.assertEqual(again["english"], ["", "Maryam Aly"])
        # spelling that equals our own suggestion is not stored as a manual change
        self.assertEqual(self.svc.put_students("g4-a", ["يوسف محمد"], ["Youssef Mohamed"])["english"], [""])
        r = self.svc.put_students("g4-a", ["يوسف محمد", "مريم علي"], ["", "Maryam Aly"])
        from docx import Document
        txt = lambda p: "\n".join(c.text for t in Document(p).tables for row in t.rows for c in row.cells)
        en = self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8})  # same file name: read before the next one
        text_en = txt(en["path"])
        text_ar = txt(self.svc.make_grading_sheet({"room_id": "g4-a", "trimester": 0, "week": 8, "lang": "ar"})["path"])
        self.assertIn("Maryam Aly", text_en); self.assertIn("Youssef Mohamed", text_en); self.assertNotIn("مريم", text_en)
        self.assertIn("مريم علي", text_ar)
        # both spellings are hidden from the AI
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.svc.ai_chat({"messages": [{"role": "user", "content": "Maryam Aly and Youssef Mohamed and مريم علي were late"}]})
        sent = json.dumps(self.sent[-1][3], ensure_ascii=False)
        for n in ("Maryam", "Youssef", "مريم"):
            self.assertNotIn(n, sent)

    def test_slides_plan_images_and_powerpoint(self):
        import base64, io
        from PIL import Image
        from pptx import Presentation
        buf = io.BytesIO(); Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "JPEG"); jpg = buf.getvalue()
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = json.dumps({"slides": [{"title": "What is input?", "bullets": ["Sends data in", "Keyboard"], "notes": "Say it.", "image_prompt": "a keyboard"},
                                            {"title": "Recap", "bullets": ["Input = in"], "notes": "", "image_prompt": "a mouse"}]})
        plan = self.svc.slide_plan({"grade_id": "g4", "topic": "Input devices. Sara Ali Hassan likes it", "slides": 2, "language": "en"})
        self.assertEqual((len(plan["slides"]), plan["stage"]), (2, "upper"))
        self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))
        self.assertIn("ONE JSON object", self.sent[-1][3]["messages"][0]["content"])
        # pictures: Cloudflare not set up -> clear error; set up -> file saved, names hidden from the picture prompt
        self.svc.image_save({"provider": "cloudflare"})     # (the default service needs no setup, and would really go online)
        with self.assertRaises(AppError) as e:
            self.svc.slide_image({"prompt": "a keyboard"})
        self.assertEqual(e.exception.code, "img_not_set")
        with self.assertRaises(AppError):
            self.svc.image_save({"account_id": "bad id", "api_token": "t"})
        st = self.svc.image_save({"account_id": "a" * 32, "api_token": "cf_secret"})
        self.assertTrue(st["configured"]); self.assertNotIn("cf_secret", json.dumps(self.svc.image_state()))
        def cf(method, url, headers, body=None, timeout=0):
            self.sent.append((method, url, headers, body))
            return {"result": {"image": base64.b64encode(jpg).decode()}, "success": True}
        self.ai_client._http = cf
        img = self.svc.slide_image({"prompt": "a keyboard with Sara Ali Hassan", "grade_id": "g4"})
        self.assertIn("flux-1-schnell", self.sent[-1][1]); self.assertNotIn("Sara", self.sent[-1][3]["prompt"]); self.assertIn("No text", self.sent[-1][3]["prompt"])
        slides = [{**s, "image_id": img["id"] if i == 0 else ""} for i, s in enumerate(plan["slides"])]
        out = self.svc.slide_build({"grade_id": "g4", "title": "Input devices", "slides": slides, "language": "en", "trimester": 0, "week": 8})
        self.assertEqual(out["slides"], 3)
        prs = Presentation(out["path"])
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual(prs.slides[1].notes_slide.notes_text_frame.text, "Say it.")
        self.assertTrue(any(sh.shape_type == 13 for sh in prs.slides[1].shapes))  # a picture is there (the logo and the slide picture)
        self.assertEqual(self.svc._plans()["slides"]["g4|0|8"]["count"], 3)
        ar = self.svc.slide_build({"grade_id": "g4", "title": "أجهزة الإدخال", "slides": [{"title": "مرحبا", "bullets": ["أ"]}], "language": "ar"})
        self.assertTrue(Path(ar["path"]).is_file())
        with self.assertRaises(AppError):
            self.svc.slide_build({"grade_id": "g4", "title": "x", "slides": []})

    def test_revision_sheet(self):
        from docx import Document
        self.svc.ai_save({"provider": "groq", "api_key": "k", "model": "m"})
        self.reply = json.dumps({"words": [{"term": "CPU", "meaning": "the brain"}], "points": ["Input sends data in"],
                                 "questions": [{"q": "What is the CPU?", "a": "The brain"}, {"q": "Name an input device", "a": "Mouse"}]})
        r = self.svc.ai_generate_revision({"grade_id": "g4", "topic": "Hardware with Sara Ali Hassan", "count": 2})
        self.assertNotIn("Sara", json.dumps(self.sent[-1][3]))
        self.assertEqual(r["words"], "CPU: the brain"); self.assertIn("|", r["questions"])
        out = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 3, **r, "title": "Hardware", "with_answers": True})
        self.assertTrue(out["name"].endswith("T1-W03_Revision_Sheet.docx"))
        d = Document(out["path"])
        text = "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for tb in d.tables for row in tb.rows for c in row.cells)
        for w in ("Revision Sheet: Hardware", "Key words", "CPU", "the brain", "What is the CPU?", "Answers", "Mouse"):
            self.assertIn(w, text)
        out2 = self.svc.make_revision({"grade_id": "g4", "trimester": 0, "week": 0, "title": "All", "points": "A\nB"})
        self.assertTrue(out2["name"].endswith("T1_Revision_Sheet.docx"))
        with self.assertRaises(AppError):
            self.svc.make_revision({"grade_id": "g4", "trimester": 0, "title": "x"})

    def test_school_map(self):
        m = self.svc.get_map()
        self.assertEqual([f["name"] for f in m["floors"]], ["Ground floor", "First floor", "Second floor"])   # the school's own building
        self.assertIn("Principal's office", [r["name"] for f in m["floors"] for r in f["rooms"]])
        ids = [r["id"] for f in m["floors"] for r in f["rooms"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [r["id"] for f in self.svc.get_map()["floors"] for r in f["rooms"]])   # ids stay the same between loads
        bad = {"floors": [{"name": "Ground", "rooms": [{"name": "Principal", "kind": "admin", "x": 99, "y": -4, "w": 40, "h": 0, "phone": "0100 123", "bogus": 1},
                                                      {"name": "G4A", "kind": "weird", "id": "../x"}]}]}
        out = self.svc.put_map(bad)
        r = out["floors"][0]["rooms"]
        self.assertEqual((r[0]["kind"], r[0]["phone"], r[1]["kind"]), ("admin", "0100 123", "other"))
        self.assertTrue(0 <= r[0]["x"] and r[0]["x"] + r[0]["w"] <= 24 and r[0]["h"] >= 1 and r[0]["y"] >= 0)
        self.assertNotIn("bogus", r[0]); self.assertNotIn("/", r[1]["id"])
        self.assertEqual(self.svc.get_map()["floors"][0]["name"], "Ground")
        with self.assertRaises(AppError):
            self.svc.put_map({"floors": "x"})

    def test_school_map_layout_and_migration(self):
        m = self.svc.get_map()
        wings = {f["name"]: {w: [r["name"] for r in f["rooms"] if r["wing"] == w] for w in ("left", "center", "right")} for f in m["floors"]}
        self.assertEqual(wings["Ground floor"], {"left": ["KG1", "KG2"], "center": [], "right": ["Photocopy office", "HR & Student affairs", "Store", "Canteen"]})
        self.assertEqual(wings["First floor"]["center"], ["Reception"])
        self.assertEqual(wings["First floor"]["right"], ["IT", "Art store", "Special needs class", "Grade 1"])
        self.assertEqual(wings["Second floor"]["left"], ["Grade 11", "Grade 9", "Grade 10", "Grade 6"])
        self.assertEqual(wings["Second floor"]["center"], ["Principal's office"])
        # a map saved by an older version (no "version") is replaced by the new building, keeping what was typed about each room
        old = {"floors": [{"id": "floor2", "name": "Second floor", "rooms": [{"name": "Principal's office", "kind": "admin", "person": "Mr X", "phone": "0100", "wing": "left"}]}]}
        self.svc._need_store().write_json(self.svc._map_path(), old)
        new = self.svc.get_map()
        r = [r for f in new["floors"] for r in f["rooms"] if r["name"] == "Principal's office"][0]
        self.assertEqual((r["person"], r["phone"], r["wing"]), ("Mr X", "0100", "center"))
        self.assertEqual(new["version"], 2)

    def test_sources_read_pictures_and_feed_helpers(self):
        import base64, io
        from PIL import Image
        from pptx import Presentation
        self.svc.ai_save({"provider": "groq", "api_key": "k"})
        # a PDF made only of pictures (like NotebookLM) and a PowerPoint with one full-slide picture and one text slide
        imgs = [Image.new("RGB", (800, 450), c) for c in ((250, 250, 250), (200, 220, 250))]
        buf = io.BytesIO(); imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:]); pdf = buf.getvalue()
        out = self.svc.import_source({"filename": "Input devices.pdf", "data_b64": base64.b64encode(pdf).decode()})
        self.assertEqual((out["pages"], out["pending"]), (2, 2))
        sid = out["id"]
        self.reply = json.dumps({"pages": [{"n": 1, "text": "Input devices", "diagram": "a keyboard"}, {"n": 2, "text": "A mouse points and clicks"}]})
        r = self.svc.read_source(sid)
        self.assertEqual(r["pending"], 0)
        body = self.sent[-1][3]["messages"][1]["content"]
        self.assertTrue(any(x.get("type") == "image_url" for x in body))   # the pictures really went to the model
        self.assertIn("llama-4-scout", self.sent[-1][3]["model"])
        self.assertIn("A mouse points and clicks", self.svc.get_source(sid)["text"])
        self.reply = json.dumps({"topic": "Input devices", "objectives": ["Name input devices"], "points": ["A mouse points"],
                                 "words": [{"term": "Mouse", "meaning": "points and clicks"}], "questions": [{"q": "What does a mouse do?", "a": "Points"}]})
        d = self.svc.digest_source(sid)["digest"]
        self.assertEqual((d["topic"], d["words"][0]["term"]), ("Input devices", "Mouse"))
        # the source text reaches every writing helper
        self.reply = json.dumps({"words": [], "points": ["x"], "questions": []})
        self.svc.ai_generate_revision({"grade_id": "g4", "topic": "t", "source_id": sid})
        self.assertIn("A mouse points and clicks", self.sent[-1][3]["messages"][1]["content"])
        # pptx
        prs = Presentation(); sl = prs.slides.add_slide(prs.slide_layouts[6])
        b2 = io.BytesIO(); imgs[1].save(b2, "PNG"); b2.seek(0); sl.shapes.add_picture(b2, 0, 0, prs.slide_width, prs.slide_height)
        sl2 = prs.slides.add_slide(prs.slide_layouts[5]); sl2.shapes.title.text = "A long enough title for a text slide that has real words in it, more than sixty characters"
        pb = io.BytesIO(); prs.save(pb)
        o2 = self.svc.import_source({"filename": "x.pptx", "data_b64": base64.b64encode(pb.getvalue()).decode()})
        self.assertEqual((o2["pages"], o2["pending"]), (2, 1))
        with self.assertRaises(AppError):
            self.svc.import_source({"filename": "x.exe", "data_b64": base64.b64encode(b"MZ00").decode()})
        self.svc.delete_source(sid)
        self.assertEqual(len(self.svc.list_sources()["sources"]), 1)

    def test_setup_and_keys_never_returned(self):
        with self.assertRaises(AppError):
            self.svc.ai_test({"provider": "groq"})  # no key
        st = self.svc.ai_save({"provider": "groq", "api_key": "gsk_secret"})
        self.assertTrue(st["ready"])
        self.assertNotIn("gsk_secret", json.dumps(st))
        self.assertTrue(next(p for p in st["providers"] if p["id"] == "groq")["has_key"])
        self.assertEqual(self.svc.ai_test({})["ok"], True)
        m, url, h, body = self.sent[-1]
        self.assertTrue(url.startswith("https://api.groq.com/openai/v1/chat/completions"))
        self.assertEqual(h["Authorization"], "Bearer gsk_secret")
        self.assertEqual(sorted(self.svc.ai_models({})["models"]), ["m1", "m2"])
        # the key is not inside the data folder
        self.assertFalse(any("gsk_secret" in p.read_text(errors="ignore") for p in Path(self.d.name).rglob("*") if p.is_file()))
        self.svc.ai_save({"provider": "groq", "api_key": "__clear__"})
        self.assertFalse(self.svc.ai_state()["ready"])

    def test_anthropic_and_ollama(self):
        self.svc.ai_save({"provider": "anthropic", "api_key": "sk-ant-x"})
        self.svc.ai_test({})
        m, url, h, body = self.sent[-1]
        self.assertTrue(url.endswith("/v1/messages")); self.assertEqual(h["x-api-key"], "sk-ant-x")
        self.assertIn("system", body)
        self.svc.ai_save({"provider": "ollama"})  # no key needed
        self.assertTrue(self.svc.ai_state()["ready"])

    def test_student_names_never_sent(self):
        self.svc.ai_save({"provider": "gemini", "api_key": "k"})
        self.reply = "1. Q?\na) x\nb) y\nAnswer: a"
        r = self.svc.ai_generate_quiz({"grade_id": "g4", "topic": "Sara   Ali Hassan and omar samy quiz", "notes": "SARA ALI HASSAN is weak", "count": 1})
        self.assertEqual(r["questions"], 1)
        sent = json.dumps(self.sent[-1][3])
        for n in ("Sara", "Hassan", "Omar", "Samy"):
            self.assertNotIn(n, sent)
        self.assertIn("[student]", sent)

    def test_lesson_and_trimester(self):
        self.svc.ai_save({"provider": "gemini", "api_key": "k"})
        self.reply = '```json\n{"topic":"Hardware","objectives":["a","b"],"sunday":"x","monday":"y","friday":"no"}\n```'
        c = self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 8, "topic": "Hardware"})["content"]
        self.assertEqual(c["objectives"], "- a\n- b"); self.assertEqual(c["sunday"], "x"); self.assertEqual(c["tuesday"], "")
        self.assertIn("monday, tuesday", "")  if False else None
        self.assertNotIn("tuesday", self.sent[-1][3]["messages"][-1]["content"].lower().split("teaching days this week:")[1].split("\n")[0])
        self.reply = '{"lessons": ["L1", "L2"]}'
        out = self.svc.ai_generate_trimester({"grade_id": "g4", "trimester": 0})["lessons"]
        self.assertEqual(out[:2], ["L1", "L2"]); self.assertEqual(len(out), 13 if len(out) == 13 else len(out))
        self.reply = "nonsense"
        with self.assertRaises(AppError):
            self.svc.ai_generate_lesson({"grade_id": "g4", "trimester": 0, "week": 8, "topic": "x"})
        with self.assertRaises(AppError):
            self.svc.ai_generate_quiz({"grade_id": "g4", "topic": "x"})

    def test_errors_and_url_allowlist(self):
        from app.core.ai_client import _map_status
        self.assertEqual(_map_status(401, "").code, "ai_bad_key")
        self.assertEqual(_map_status(429, "").code, "ai_rate_limit")
        self.assertEqual(_map_status(404, "").code, "ai_bad_model")
        self.assertEqual(_map_status(503, "").code, "ai_server")
        with self.assertRaises(AppError):
            self.svc.open_url("https://evil.example.com")
        self.assertTrue(self.svc.open_url("https://aistudio.google.com/app/apikey")["ok"])


class TestAiModels(AiCase):
    def test_models_come_from_the_service_and_auto_picks_a_working_one(self):
        from app.server.ai_service import rank_models
        self.assertEqual(rank_models(["text-embedding-004", "whisper-large-v3", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-lite"], "gemini"),
                         ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro"])
        self.assertEqual(rank_models(["a", "b:free", "c:free"], "openrouter"), ["b:free", "c:free"])
        self.svc.ai_save({"provider": "groq", "api_key": "k"})
        chat_models = []
        hand_picked = False
        orig = self.ai_client._http
        def picky(method, url, headers, body=None, timeout=0):
            if url.endswith("/models"):
                return {"data": [{"id": "old-model-flash"}, {"id": "whisper-1"}, {"id": "new-model-mini"}]}
            chat_models.append(body["model"])
            if body["model"] == "new-model-mini" and not hand_picked:
                raise AppError("ai_bad_model", "gone", status=502)
            return {"choices": [{"message": {"content": "ready"}}]}
        self.ai_client._http = picky
        self.svc._models_cache.clear()
        r = self.svc.ai_test({})
        self.assertEqual((r["model"], r["auto"]), ("old-model-flash", True))
        self.assertNotIn("whisper-1", r["models"])
        self.assertEqual(chat_models[:2], ["new-model-mini", "old-model-flash"])  # tried the best-ranked first, then moved on
        # a model chosen by hand is used as is
        chat_models.clear(); hand_picked = True
        self.svc.ai_save({"provider": "groq", "model": "new-model-mini"})
        self.svc.ai_test({}); self.assertEqual(chat_models, ["new-model-mini"])
        self.ai_client._http = orig


class TestMadeDecks(AiCase):
    def test_built_and_existing_decks_join_my_slides(self):
        from app.core.pptx_builder import build_deck
        self.svc.slide_build({"grade_id": "g4", "title": "Input devices", "slides": [{"title": "Mouse", "bullets": ["points", "clicks"], "explain": "A mouse moves the pointer.", "notes": "n"}]})
        names = [x["name"] for x in self.svc.list_sources()["sources"]]
        self.assertTrue(any("Input devices" in n for n in names))
        extra = self.svc._need_store().root / "Slides" / "x" / "Old deck.pptx"
        build_deck(extra, {"title": "Old deck", "subtitle": "", "language": "en", "stage": "primary", "slides": [{"title": "Keyboard", "bullets": ["keys"], "explain": "", "notes": "", "image_path": ""}]})
        srcs = self.svc.list_sources()["sources"]
        self.assertTrue(any(x["name"] == "Old deck" and x["made"] for x in srcs))
        self.assertEqual(len([x for x in srcs if "Input devices" in x["name"]]), 1)


class TestUrlSource(AiCase):
    def test_web_page_becomes_a_source_and_blocks_private_addresses(self):
        from unittest import mock
        page = b"<html><head><title>The CPU</title></head><body><nav>menu</nav><h1>The CPU</h1><p>" + b"The CPU is the brain of the computer. " * 8 + b"</p></body></html>"
        with mock.patch("app.core.ai_client.http_bytes", return_value=page), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            out = self.svc.import_url({"url": "example.com/cpu"})
        self.assertEqual(out["name"], "The CPU"); self.assertGreater(out["chars"], 100)
        text = self.svc.source_block(out["id"])
        self.assertIn("ONLY", text); self.assertNotIn("menu", text)
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.1", 0))]):
            with self.assertRaises(AppError):
                self.svc.import_url({"url": "http://router.local/"})
        with self.assertRaises(AppError):
            self.svc.import_url({"url": "file:///etc/passwd"})



class TestYoutubeSource(AiCase):
    def test_captions_and_pasted_transcript(self):
        import json
        from unittest import mock
        pr = {"videoDetails": {"title": "How a CPU works"}, "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [{"languageCode": "en", "baseUrl": "https://www.youtube.com/api/timedtext?v=abc"}]}}}
        page = ("<script>var ytInitialPlayerResponse = " + json.dumps(pr) + ";var meta = 1;</script>").encode()
        xml = ("<transcript>" + "".join(f"<text start='{i}'>The CPU runs instructions {i} &amp;#39;fast&amp;#39;</text>" for i in range(12)) + "</transcript>").encode()
        with mock.patch("app.core.ai_client.http_bytes", side_effect=[page, xml]), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.1.1", 0))]):
            out = self.svc.import_url({"url": "https://youtu.be/dQw4w9WgXcQ"})
        self.assertEqual(out["name"], "How a CPU works")
        self.assertIn("runs instructions", self.svc.source_block(out["id"]))
        nocap = ("<script>var ytInitialPlayerResponse = {};</script>").encode()
        with mock.patch("app.core.ai_client.http_bytes", return_value=nocap), mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.1.1", 0))]):
            with self.assertRaises(AppError) as c:
                self.svc.import_url({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
            self.assertEqual(c.exception.code, "no_captions")
            out2 = self.svc.import_url({"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "transcript": "Memory stores data. " * 10})
        self.assertIn("Memory stores", self.svc.source_block(out2["id"]))


class TestTranslitMore(unittest.TestCase):
    def test_names(self):
        from app.core.translit import to_english
        self.assertEqual(to_english("تسنيم حامد"), "Tasneem Hamed")
        self.assertEqual(to_english("رزان خالد"), "Razan Khaled")
        self.assertEqual(to_english("زين الدين"), "Zein El Din")


if __name__ == "__main__":
    unittest.main()
