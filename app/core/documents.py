"""Fill the four DLIS Word templates (lesson plan, trimester plan, quiz, grading sheet).

The templates have no placeholders, so each filler knows where things live (which table, which cell) and keeps the
template's own fonts and layout: it only adds text next to labels or into empty cells.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Optional

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

from . import paths
from .errors import AppError

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]


# ------------------------------------------------------------------ small Word helpers
def _first_run(par: Paragraph):
    return par.runs[0] if par.runs else par.add_run("")


def set_par(par: Paragraph, text: str) -> None:
    """Replace a paragraph's text but keep the formatting of its first run."""
    runs = par.runs
    if not runs:
        par.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def add_after_label(par: Paragraph, value: str) -> None:
    """'Subject/Course: ' -> 'Subject/Course: ICT' (the value is not bold)."""
    base = par.runs[-1] if par.runs else None
    run = par.add_run(value)
    if base is not None:
        run.font.name = base.font.name
        run.font.size = base.font.size
    run.bold = False


def fill_cell(cell, text: str, keep_labels: int = 0) -> None:
    """Write (possibly multi-line) text into a cell, using its last paragraph so labels above stay untouched."""
    text = (text or "").rstrip()
    if not text:
        return
    pars = cell.paragraphs
    target = pars[-1] if len(pars) > keep_labels else pars[0]
    lines = text.split("\n")
    set_par(target, lines[0])
    for r in target.runs:
        r.bold = False
    prev = target
    for line in lines[1:]:
        new = copy.deepcopy(target._p)
        prev._p.addnext(new)
        prev = Paragraph(new, target._parent)
        set_par(prev, line)


def _cell(table, r: int, c: int):
    return table.rows[r].cells[c]


_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def _scrub(obj):
    """Text pasted from the web or written by an AI may hold characters Word files cannot store. Remove them, and
    make every value a string (or a list of strings) so a strange value can never crash the file."""
    if isinstance(obj, str):
        return _BAD_XML.sub("", obj)
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub(v) for v in obj]
    return obj


def _clean(text) -> str:
    if isinstance(text, (list, tuple)):
        text = "\n".join(str(x) for x in text)
    return _BAD_XML.sub("", str(text if text is not None else "")).strip()


# ------------------------------------------------------------------ lesson plan
def add_block(cell, text: str) -> None:
    """Add text as new paragraphs UNDER the label paragraph of a cell (e.g. under 'Sunday'), not bold."""
    text = (text or "").strip()
    if not text:
        return
    label = cell.paragraphs[0]
    base = next((r for r in label.runs if r.text.strip()), None)
    prev = label
    for line in text.split("\n"):
        new_p = copy.deepcopy(label._p)
        for r in list(new_p.findall(qn("w:r"))):
            new_p.remove(r)
        ppr = new_p.find(qn("w:pPr"))
        if ppr is not None and ppr.find(qn("w:ind")) is not None:  # the label's side indent would squeeze the text
            ppr.remove(ppr.find(qn("w:ind")))
        prev._p.addnext(new_p)
        par = Paragraph(new_p, label._parent)
        run = par.add_run(line)
        if base is not None:
            run.font.name, run.font.size = base.font.name, base.font.size
        run.bold = False
        prev = par


def _template_font(cell, name: str = "Segoe UI", size: float = 8.5) -> None:
    """The template's empty cells have no font of their own (they would print in 11pt Calibri); use the labels' font."""
    for par in cell.paragraphs:
        for r in par.runs:
            if r.font.name is None:
                r.font.name = name
                rpr = r._r.get_or_add_rPr()
                fonts = rpr.find(qn("w:rFonts"))
                for attr in ("w:eastAsia", "w:cs"):
                    fonts.set(qn(attr), name)
            if r.font.size is None:
                r.font.size = Pt(size)


def fill_lesson_plan(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: term, week, subject, teacher, grade_label, date_range, length, content{...}, day_dates{Sunday:'06/09'},
    day_notes{Sunday:'Holiday: ...'}, teach_days[...] (days this grade has a lesson; the others say 'No session')."""
    ctx = _scrub(ctx)
    doc = Document(str(template))
    raw = ctx.get("content")
    c = {k: _clean(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    for r in doc.paragraphs[0].runs:
        if "Lesson Plan" in r.text:
            r.text = re.sub(r"\(Term.*?\)", f"(Term {ctx.get('term', '')} Week {ctx.get('week', '')})", r.text)

    t0 = doc.tables[0]
    add_after_label(_cell(t0, 1, 0).paragraphs[0], _clean(ctx.get("subject")))
    add_after_label(_cell(t0, 1, 1).paragraphs[0], _clean(ctx.get("teacher")))
    add_after_label(_cell(t0, 2, 0).paragraphs[0], _clean(ctx.get("grade_label")))
    add_after_label(_cell(t0, 2, 1).paragraphs[0], _clean(ctx.get("date_range")))
    add_after_label(_cell(t0, 3, 0).paragraphs[0], _clean(c.get("topic")))
    add_after_label(_cell(t0, 3, 1).paragraphs[0], _clean(ctx.get("length")))

    fill_cell(_cell(doc.tables[1], 1, 0), c.get("objectives", ""))

    # table 2: row 1..5 = Sunday..Thursday (one cell each), row 6 = practice book pages
    structure = doc.tables[2]
    dates = ctx.get("day_dates") or {}
    notes = ctx.get("day_notes") or {}
    teach = ctx.get("teach_days")
    for i, day in enumerate(DAYS):
        cell = _cell(structure, 1 + i, 0)
        if dates.get(day):
            label_text = cell.paragraphs[0].text
            r = cell.paragraphs[0].add_run(f"{'' if label_text.endswith(' ') else ' '}({dates[day]})")
            r.bold = False
            r.font.name = "Segoe UI"
            r.font.size = Pt(8.5)
            r.underline = False
        text = _clean(c.get(day.lower()))
        if not text:
            if notes.get(day):
                text = f"{notes[day]}"
            elif teach is not None and day not in teach:
                text = "No session"
        add_block(cell, text)
    pages = _clean(c.get("practice_pages"))
    if pages:
        add_after_label(_cell(structure, 6, 0).paragraphs[0], pages)

    fill_cell(_cell(doc.tables[3], 1, 0), c.get("activities", ""))
    fill_cell(_cell(doc.tables[4], 1, 0), c.get("resources", ""))
    fill_cell(_cell(doc.tables[5], 1, 0), c.get("differentiation", ""))
    fill_cell(_cell(doc.tables[6], 1, 0), c.get("assessment", ""))
    fill_cell(_cell(doc.tables[7], 1, 0), c.get("reflection", ""))
    for t_i in (1, 3, 4, 5, 6, 7):
        _template_font(_cell(doc.tables[t_i], 1, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


# ------------------------------------------------------------------ trimester plan
def fill_trimester_plan(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: trimester(number), subject, grade_label, academic_year, textbooks, weeks=[{number,from,to,note,lesson}]"""
    ctx = _scrub(ctx)
    doc = Document(str(template))
    for p in doc.paragraphs:
        t = p.text.strip()
        if t.startswith("Trimester"):
            set_par(p, f"Trimester {ctx.get('trimester', '')} Plan")
        elif t.startswith("Department"):
            set_par(p, f"Department: {_clean(ctx.get('subject'))}")
        elif t.startswith("Grade"):
            set_par(p, f"Grade ( {_clean(ctx.get('grade_label'))} )")
        elif t.startswith("Academic Year"):
            set_par(p, f"Academic Year: {_clean(ctx.get('academic_year'))}")
        elif set(t) == {"_"} and ctx.get("textbooks"):
            set_par(p, ctx["textbooks"])
    table = doc.tables[0]
    weeks = ctx.get("weeks") or []
    body_rows = table.rows[1:]
    while len(body_rows) < len(weeks):  # more weeks than the template has rows: copy the last row
        table._tbl.append(copy.deepcopy(body_rows[-1]._tr))
        body_rows = table.rows[1:]
    for i, row in enumerate(body_rows):
        if i >= len(weeks):
            table._tbl.remove(row._tr)
            continue
        w = weeks[i]
        left = row.cells[0].paragraphs
        set_par(left[0], f"Week {w['number']}")
        if len(left) > 1:
            set_par(left[1], f"From {w['from']} to {w['to']}")
        lesson = "\n".join(x for x in (_clean(w.get("lesson")), f"[{w['note']}]" if w.get("note") else "") if x)
        fill_cell(row.cells[1], lesson)
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


# ------------------------------------------------------------------ quiz
_OPT = re.compile(r"^\s*\(?([A-Ha-h])[\)\.\-:]\s+(.*\S)\s*$")
_ANS = re.compile(r"^\s*(?:answer|ans|الإجابة|الاجابة)\s*[:：\-]\s*(.*\S)\s*$", re.I)
_QNUM = re.compile(r"^\s*(?:Q\s*)?\d+\s*[\.\)\-:]\s*", re.I)
_PAIR = re.compile(r"^\s*(.+?)\s*(?:=|->|→|=>|\|)\s*(.+?)\s*$")
_TYPE_TAG = re.compile(r"^\s*\[(mcq|tf|true.?false|match(?:ing)?|essay|fill(?:.?blank)?|short)\]\s*", re.I)
QUESTION_TYPES = ("mcq", "tf", "match", "essay", "fill")


def _kind(q: dict) -> str:
    if q["pairs"]:
        return "match"
    if q["options"]:
        vals = [o[1].strip().lower().rstrip(".") for o in q["options"]]
        return "tf" if len(vals) == 2 and set(vals) <= {"true", "false", "صح", "خطأ", "خطا"} else "mcq"
    return "fill" if "___" in q["q"] else "essay"


def parse_quiz(text: str) -> list[dict]:
    """Questions as plain text. '1. Question?' then 'a) ...' lines (multiple choice / true-false), or 'term = match' lines (matching),
    or nothing (essay / fill the blank). Optional 'Answer: ...' line. Every numbered line starts a new question."""
    questions: list[dict] = []
    cur: Optional[dict] = None
    for raw in str(text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m_ans, m_opt = _ANS.match(line), _OPT.match(line)
        if m_ans and cur:
            cur["answer"] = m_ans.group(1).strip().strip("()")
        elif m_opt and cur and not _QNUM.match(line):
            cur["options"].append((m_opt.group(1).upper(), m_opt.group(2)))
        elif cur and (cur["type"].startswith("match") or cur["pairs"] or "match" in cur["q"].lower() or "وصل" in cur["q"]) and not _QNUM.match(line) and _PAIR.match(line) and not line.endswith("?"):
            m = _PAIR.match(line)
            cur["pairs"].append((m.group(1), m.group(2)))
        else:
            numbered = bool(_QNUM.match(line))
            if cur is None or numbered or cur["options"] or cur["answer"] or cur["pairs"]:
                cur = {"q": "", "options": [], "answer": "", "pairs": [], "type": ""}
                questions.append(cur)
            body = _QNUM.sub("", line)
            tag = _TYPE_TAG.match(body)
            if tag:
                cur["type"] = tag.group(1).lower()
                body = body[tag.end():]
            cur["q"] = (cur["q"] + " " + body).strip()
    out = []
    for q in questions:
        if not q["q"]:
            continue
        if q["type"].startswith("match") and not q["pairs"]:
            q["pairs"] = []
        q["type"] = _kind(q)
        out.append(q)
    return out


def _right_option(q: dict) -> str:
    """The text of the correct choice of a multiple-choice or true/false question ('' when no answer is given)."""
    ans = str(q.get("answer", "")).strip().strip("()").upper()
    for letter, text in q.get("options") or []:
        if ans and (ans == str(letter).upper() or ans == text.strip().upper()):
            return text
    return ""


def quiz_to_gift(questions: list[dict], title: str = "Quiz") -> str:
    """Moodle's GIFT text format (Question bank > Import > GIFT). Questions without a usable answer become essay questions."""
    def esc(x):
        return re.sub(r"([~=#{}:\\])", r"\\\1", str(x))
    lines = [f"// {title}", f"$CATEGORY: {esc(title)}", ""]
    for i, q in enumerate(questions, 1):
        kind = q.get("type") or _kind(q)
        head = f"::Q{i}:: "
        text = esc(q["q"])
        if kind == "match" and len(q.get("pairs") or []) >= 3:
            body = " ".join(f"={esc(a)} -> {esc(b)}" for a, b in q["pairs"])
            lines.append(f"{head}{text} {{ {body} }}")
        elif kind in ("mcq", "tf") and q.get("options") and _right_option(q):
            right = _right_option(q)
            if kind == "tf":
                lines.append(f"{head}{text} {{{'TRUE' if right.strip().lower().rstrip('.') in ('true', 'صح') else 'FALSE'}}}")
            else:
                body = " ".join(("=" if text_ == right else "~") + esc(text_) for _l, text_ in q["options"])
                lines.append(f"{head}{text} {{ {body} }}")
        elif kind == "fill" and str(q.get("answer", "")).strip() and "___" in q["q"]:
            lines.append(head + re.sub(r"_{3,}", "{=" + esc(str(q["answer"]).strip()) + "}", esc(q["q"]), count=1).replace("\\{", "{").replace("\\}", "}").replace("\\=", "="))
        else:
            lines.append(f"{head}{text} {{}}")
        lines.append("")
    return "\n".join(lines)


def quiz_to_forms_script(questions: list[dict], title: str = "Quiz") -> str:
    """A Google Apps Script that builds the quiz as a Google Form (script.google.com > New project > paste > Run createQuiz)."""
    import json
    j = lambda x: json.dumps(str(x), ensure_ascii=False)
    out = ["function createQuiz() {", f"  var form = FormApp.create({j(title)});", "  form.setIsQuiz(true);", "  var it;"]
    for q in questions:
        kind = q.get("type") or _kind(q)
        if kind in ("mcq", "tf") and q.get("options"):
            right = _right_option(q)
            out.append(f"  it = form.addMultipleChoiceItem().setTitle({j(q['q'])}).setPoints(1).setRequired(false);")
            out.append("  it.setChoices([" + ", ".join(f"it.createChoice({j(t_)}, {'true' if t_ == right and right else 'false'})" for _l, t_ in q["options"]) + "]);")
        elif kind == "match" and q.get("pairs"):
            rights = [b for _a, b in q["pairs"]]
            for a, b in q["pairs"]:
                out.append(f"  it = form.addListItem().setTitle({j(q['q'] + ' — ' + a)}).setPoints(1).setRequired(false);")
                out.append("  it.setChoices([" + ", ".join(f"it.createChoice({j(r_)}, {'true' if r_ == b else 'false'})" for r_ in rights) + "]);")
        else:
            long = kind == "essay"
            out.append(f"  it = form.{'addParagraphTextItem' if long else 'addTextItem'}().setTitle({j(q['q'])}).setPoints(1).setRequired(false);")
            if str(q.get("answer", "")).strip():
                out.append(f"  it.setGeneralFeedback(FormApp.createFeedback().setText({j('Answer: ' + str(q['answer']).strip())}).build());")
    out += ["  Logger.log('Edit: ' + form.getEditUrl());", "  Logger.log('Students: ' + form.getPublishedUrl());", "}", ""]
    return "\n".join(out)


def shuffled_version(questions: list[dict], seed: int = 7) -> list[dict]:
    """Version B of a quiz: the questions in another order, and the choices of every multiple-choice question in another order
    (the answer letter follows its choice). True/false and matching keep their order, so nothing becomes confusing."""
    import random
    rnd = random.Random(seed)
    out = []
    for q in questions:
        q = {**q, "options": list(q.get("options") or []), "pairs": list(q.get("pairs") or [])}
        if q.get("type") == "mcq" and len(q["options"]) > 1:
            letters = [o[0] for o in q["options"]]
            texts = [o[1] for o in q["options"]]
            order = list(range(len(texts)))
            rnd.shuffle(order)
            if order == list(range(len(texts))):
                order = order[1:] + order[:1]
            ans = str(q.get("answer", "")).strip().strip("()").upper()[:1]
            if ans in letters:
                q["answer"] = letters[order.index(letters.index(ans))]
            q["options"] = [(letters[i], texts[order[i]]) for i in range(len(texts))]
        out.append(q)
    rnd.shuffle(out)
    return out


def fill_quiz(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: grade_label ('4' or 'KG 1'), trimester, week, number, questions(list), with_answers"""
    ctx = _scrub(ctx)
    doc = Document(str(template))
    pars = doc.paragraphs
    label = _clean(ctx.get("grade_label"))
    grade_text = label if label.upper().startswith("KG") else f"Grade {label}"
    head = doc.tables[0].rows[0].cells[1].paragraphs
    set_par(head[0], f"{_clean(ctx.get('subject'))} Department")
    set_par(head[1], f"{grade_text} - Trimester {ctx.get('trimester', '')}")
    set_par(head[2], f"Quiz {ctx.get('number', 1)}: Week {ctx.get('week', '')}")
    total = len(ctx.get("questions") or [])
    score = doc.tables[1].rows[1].cells[2].paragraphs[0]
    set_par(score, f"Score:  ____ / {total}")

    anchor = pars[2]            # the empty line under the student table: the questions go here, "Good luck!" stays last
    base = pars[2]
    font = _first_run(pars[4]).font.name if len(pars) > 4 else None

    def add_par(after: Paragraph, text: str, bold: bool = False, indent: float = 0, space_after: float = 4) -> Paragraph:
        new = copy.deepcopy(pars[3]._p)
        after._p.addnext(new)
        p = Paragraph(new, after._parent)
        for rr in list(p.runs):
            rr._r.getparent().remove(rr._r)
        run = p.add_run(text)
        run.bold = bold
        run.underline = False
        run.font.size = Pt(12)
        if font:
            run.font.name = font
        p.paragraph_format.left_indent = Pt(indent)
        p.paragraph_format.space_after = Pt(space_after)
        p.alignment = 0   # left: the template's empty lines are centred
        return p

    questions = ctx.get("questions") or []
    last = anchor
    keys = []
    for i, q in enumerate(questions, 1):
        kind = q.get("type") or _kind({"q": q["q"], "options": q.get("options") or [], "pairs": q.get("pairs") or []})
        last = add_par(last, f"{i}. {q['q']}", bold=True, space_after=2)
        if kind == "match" and q.get("pairs"):
            pairs = q["pairs"]
            order = [(j + 1) % len(pairs) for j in range(len(pairs))]  # right column in a shifted order so it is not already matched
            for j, (left, _r) in enumerate(pairs, 1):
                last = add_par(last, f"{j}) {left}", indent=22, space_after=1)
            last = add_par(last, "", space_after=1)
            for k, j in enumerate(order):
                last = add_par(last, f"{chr(97 + k)}) {pairs[j][1]}", indent=22, space_after=1)
            keys.append(f"{i}- " + " ".join(f"{n + 1}-{chr(97 + order.index(n))}" for n in range(len(pairs))))
        elif kind in ("mcq", "tf"):
            for letter, opt in q["options"]:
                last = add_par(last, f"{letter.lower()}) {opt}", indent=22, space_after=1)
            if q.get("answer"):
                keys.append(f"{i}-{q['answer'].upper()}")
        elif kind == "essay":
            for _ in range(2):
                last = add_par(last, "_" * 70, indent=22, space_after=2)
            if q.get("answer"):
                keys.append(f"{i}- {q['answer']}")
        else:
            if q.get("answer"):
                keys.append(f"{i}- {q['answer']}")
        last = add_par(last, "", space_after=4)
    if ctx.get("with_answers") and keys:
        last = add_par(last, "Answer key", bold=True)
        for k in keys:
            last = add_par(last, k, space_after=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


# ------------------------------------------------------------------ grading sheet
# The school's sheet: five daily boxes for each part. The full mark of a part is shared equally between its five boxes.
GRADE_PARTS = {"behavior": (2, 2), "attendance": (7, 2), "classwork": (12, 3), "homework": (17, 3), "quiz": (22, 20)}   # part -> (first column, mark per box)
GRADE_TOTALS = {"behavior": 10, "attendance": 10, "classwork": 15, "homework": 15, "quiz": 20}


def fill_grading_sheet(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: term, week, date, subject, grade_label, students(list of names),
    optional full(list of parts to fill with the full mark: behavior, attendance, classwork, homework, quiz) and absent(list of student indexes left empty)"""
    ctx = _scrub(ctx)
    doc = Document(str(template))
    for cell in doc.tables[0].rows[0].cells:
        if "Term" in cell.text and "Week" in cell.text:
            text = (cell.text.replace("Term ____", f"Term {ctx.get('term', '')}")
                    .replace("Week _____", f"Week {ctx.get('week', '')}")
                    .replace("Date ________", f"Date {ctx.get('date', '')}")
                    .replace("Subject ______________", f"Subject {_clean(ctx.get('subject'))}")
                    .replace("Grade level ____", f"Grade level {_clean(ctx.get('grade_label'))}"))
            set_par(cell.paragraphs[0], text)
            break
    table = doc.tables[1]
    students = ctx.get("students") or []
    while len(table.rows) - 1 < len(students):
        table._tbl.append(copy.deepcopy(table.rows[-1]._tr))
    for i, row in enumerate(table.rows[1:]):
        if i >= len(students):
            break
        set_par(row.cells[0].paragraphs[0], str(i + 1))
        set_par(row.cells[1].paragraphs[0], students[i])
        if i in set(ctx.get("absent") or []):
            continue                                             # the absent student's marks stay empty for the teacher
        for part in ctx.get("full") or []:
            first, each = GRADE_PARTS[part]
            boxes = 1 if part == "quiz" else 5
            for c in range(first, first + boxes):
                set_par(row.cells[c].paragraphs[0], str(each))
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


def write_grade_table(out: Path, names: list, subject: str = "", label: str = "", term: int = 0, week: int = 0, full_mark=None, absent=()) -> Path:
    """A plain on-screen table (Excel or CSV) with the class list and an empty grade column, to copy into the LMS."""
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [[i + 1, _scrub({"n": n})["n"], ("" if (full_mark is None or i in set(absent)) else full_mark)] for i, n in enumerate(names)]
    if out.suffix.lower() == ".csv":
        import csv
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["#", "Student", "Grade"]); w.writerows(rows)
        return out
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    wb = Workbook(); ws = wb.active; ws.title = "Grades"
    ws.sheet_view.rightToLeft = any("\u0600" <= c <= "\u06FF" for n in names for c in n)
    ws.append([f"{_clean(subject)} - {_clean(label)} - Term {term} Week {week}"]); ws["A1"].font = Font(bold=True, size=13)
    ws.merge_cells("A1:C1"); ws.append(["#", "Student", "Grade"])
    line = Side(style="thin", color="B8C4CE")
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="2F82A8"); c.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.border = Border(left=line, right=line, top=line, bottom=line)
    ws.column_dimensions["A"].width = 6; ws.column_dimensions["B"].width = 38; ws.column_dimensions["C"].width = 12
    ws.freeze_panes = "A3"; wb.save(out)
    return out


# ------------------------------------------------------------------ revision sheet
def parse_revision_text(text: str, kind: str) -> list:
    """kind 'words': 'word: meaning' per line; 'points': one per line; 'questions': 'question | answer' per line."""
    out = []
    for raw in str(text or "").replace("\r", "").split("\n"):
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+\s*[.)])\s*", "", raw).strip()
        if not line:
            continue
        if kind == "points":
            out.append(line)
        elif kind == "words":
            m = re.split(r"\s*[:\u2013\u2014=]\s*|\s+-\s+", line, maxsplit=1)
            out.append((m[0].strip(), m[1].strip() if len(m) > 1 else ""))
        else:
            m = re.split(r"\s*\|\s*", line, maxsplit=1)
            out.append((m[0].strip(), m[1].strip() if len(m) > 1 else ""))
    return out


def _shade(cell, hex_fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hex_fill)
    tcPr.append(sh)


def _borders(table) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    pr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:space"), "0"); e.set(qn("w:color"), "A9C9DA")
        b.append(e)
    pr.append(b)


def fill_revision(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: grade_label, trimester, week (0 = whole trimester), title, words[(w, meaning)], points[str], questions[(q, a)], with_answers"""
    from docx.shared import RGBColor
    ctx = _scrub(ctx)
    doc = Document(str(template))
    pars = doc.paragraphs
    r = pars[1].runs
    label = _clean(ctx.get("grade_label"))
    if label.upper().startswith("KG"):
        r[0].text, r[2].text = "KG", label[2:].strip() or ""
    else:
        r[2].text = label
    r[6].text = str(ctx.get("trimester", ""))
    if ctx.get("week"):
        r[10].text = str(ctx["week"])
    else:
        r[8].text = ""; r[9].text = ""; r[10].text = ""
        # "Grade 4 Trimester 1" only when the sheet covers the whole trimester
    set_par(pars[2], f"Revision Sheet: {_clean(ctx.get('title'))}")
    for p in pars[3:]:
        p._p.getparent().remove(p._p)
    font = _first_run(pars[2]).font.name
    BLUE, GREEN = RGBColor(0x1F, 0x2A, 0x5C), RGBColor(0x2F, 0x82, 0xA8)

    def para(text: str, bold: bool = False, size: float = 11.5, color=None, indent: float = 0, after: float = 3, before: float = 0):
        p = doc.add_paragraph()
        run = p.add_run(text); run.bold = bold; run.font.size = Pt(size)
        if font:
            run.font.name = font
        if color is not None:
            run.font.color.rgb = color
        p.paragraph_format.left_indent = Pt(indent)
        p.paragraph_format.space_after = Pt(after); p.paragraph_format.space_before = Pt(before)
        return p

    words, points, qs = ctx.get("words") or [], ctx.get("points") or [], ctx.get("questions") or []
    if words:
        para("Key words", bold=True, size=14, color=GREEN, before=8, after=4)
        table = doc.add_table(rows=1, cols=2)
        _borders(table)
        for c, txt in zip(table.rows[0].cells, ("Word", "Meaning")):
            _shade(c, "2F82A8"); set_par(c.paragraphs[0], txt)
            for rr in c.paragraphs[0].runs:
                rr.bold = True; rr.font.size = Pt(11); rr.font.color.rgb = RGBColor(255, 255, 255)
        for i, (w, m) in enumerate(words):
            row = table.add_row().cells
            set_par(row[0].paragraphs[0], w); set_par(row[1].paragraphs[0], m)
            for c in row:
                if i % 2:
                    _shade(c, "EEF6FA")
                for rr in c.paragraphs[0].runs:
                    rr.font.size = Pt(11)
            for rr in row[0].paragraphs[0].runs:
                rr.bold = True
        for row in table.rows:
            row.cells[0].width = Pt(130); row.cells[1].width = Pt(340)
    if points:
        para("Remember", bold=True, size=14, color=GREEN, before=12, after=4)
        for p_ in points:
            para("\u2022  " + p_, indent=10, after=3)
    if qs:
        para("Check yourself", bold=True, size=14, color=GREEN, before=12, after=4)
        for i, (q, a) in enumerate(qs, 1):
            para(f"{i}. {q}", bold=True, after=2)
            para("_" * 70, size=10, indent=14, after=6, color=RGBColor(0x9B, 0xB7, 0xC6))
        if ctx.get("with_answers") and any(a for _, a in qs):
            para("Answers", bold=True, size=14, color=BLUE, before=14, after=4)
            for i, (q, a) in enumerate(qs, 1):
                if a:
                    para(f"{i}. {a}", indent=10, after=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


# ------------------------------------------------------------------ cover sheet (for a substitute teacher)
def fill_cover(template: Path, out: Path, ctx: dict) -> Path:
    """ctx: date, teacher, subject, lessons[{period,start,end,room,students,topic,objectives,activities,slides,last_topic,last_slide,last_total,remember}]"""
    from docx.shared import RGBColor
    ctx = _scrub(ctx)
    doc = Document(str(template))
    pars = doc.paragraphs
    set_par(pars[1], "Cover sheet for a substitute teacher")
    set_par(pars[2], _clean(ctx.get("date")))
    for p in pars[3:]:
        p._p.getparent().remove(p._p)
    font = _first_run(pars[2]).font.name
    BLUE, GREEN = RGBColor(0x1F, 0x2A, 0x5C), RGBColor(0x2F, 0x82, 0xA8)

    def para(text="", bold=False, size=11, color=None, after=2, before=0, indent=0):
        p = doc.add_paragraph()
        r = p.add_run(text); r.bold = bold; r.font.size = Pt(size)
        if font:
            r.font.name = font
        if color is not None:
            r.font.color.rgb = color
        p.paragraph_format.space_after = Pt(after); p.paragraph_format.space_before = Pt(before); p.paragraph_format.left_indent = Pt(indent)
        return p

    def line(label, value):
        if not value:
            return
        p = doc.add_paragraph()
        a = p.add_run(label + " "); a.bold = True; a.font.size = Pt(11)
        b = p.add_run(_clean(value)); b.font.size = Pt(11)
        if font:
            a.font.name = b.font.name = font
        p.paragraph_format.space_after = Pt(2); p.paragraph_format.left_indent = Pt(10)

    para(f"Teacher: {_clean(ctx.get('teacher'))}   Subject: {_clean(ctx.get('subject'))}", size=11, after=6)
    for L in ctx.get("lessons") or []:
        when = f"{L['start']} – {L['end']}" if L.get("start") else ""
        para(f"Period {L['period']}  ·  {when}  ·  {L['room']}  ({L['students']} students)", bold=True, size=13, color=GREEN, before=10, after=3)
        line("Topic:", L.get("topic")) if L.get("topic") else line("Topic:", "Not planned in the app. Please continue from the textbook.")
        line("Objectives:", L.get("objectives"))
        line("Activities:", L.get("activities"))
        if L.get("slides"):
            line("Slides:", f"{L['slides']} slides prepared (ask the class to open the lesson slides).")
        if L.get("last_topic") or L.get("last_slide"):
            where = _clean(L.get("last_topic"))
            if L.get("last_slide"):
                where += f" (slide {L['last_slide']}" + (f" of {L['last_total']})" if L.get("last_total") else ")")
            line("Last time the class reached:", where)
        line("Reminder:", L.get("remember"))
        para("Notes for the class teacher: ______________________________________________________", size=10, color=RGBColor(0x6B, 0x74, 0x91), before=4, after=4, indent=10)
    para("Thank you for covering the class.", color=BLUE, before=12)
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


TEMPLATES = {
    "lesson_plan": "Lesson_Plan_Temp.docx",
    "trimester_plan": "Trimester_Plan_Template.docx",
    "quiz": "Quiz_Template_v2.docx",
    "grading_sheet": "Grading_Sheet_Template.docx",
    "revision": "quiz_Template.docx",
    "revision_cover": "Revision_Cover_Template.docx",
}


def _save(doc, out: Path) -> None:
    try:
        doc.save(str(out))
    except PermissionError:  # the same file is still open in Word
        raise AppError("file_in_use", f"Close this file in Word first: {out.name}", status=409)


def fill_revision_cover(template: Path, out: Path, ctx: dict) -> Path:
    """The first page of the Trimester revision pack (school logo, Cognia logo, subject, covered material).
    ctx: academic_year, grade_label, subject, teacher, department, trimester, rows[(unit, lesson, pages)]"""
    import copy as _copy
    ctx = _scrub(ctx)
    doc = Document(str(template))
    tri = str(ctx.get("trimester", 1))
    pars = doc.paragraphs
    pars[1].runs[0].text = f"Final Trimester {tri} Revision Pack – Covered Material Report"
    for par, key in ((pars[2], "academic_year"), (pars[3], "grade_label"), (pars[4], "subject"), (pars[5], "teacher")):
        par.runs[1].text = _clean(ctx.get(key))
    hp = doc.sections[0].header.paragraphs
    dept = _clean(ctx.get("department")) or _clean(ctx.get("subject"))
    hp[0].runs[0].text = f"{dept} Department"
    hp[1].runs[0].text = f"\t\tRevision Pack-Trimester {tri}-Grade ({_clean(ctx.get('grade_label'))})"
    table = doc.tables[0]
    rows = list(ctx.get("rows") or [])
    while len(table.rows) - 1 < len(rows):
        table._tbl.append(_copy.deepcopy(table.rows[-1]._tr))
    while len(table.rows) - 1 > max(len(rows), 5):   # the template's spare lines would push the page to a second sheet
        table._tbl.remove(table.rows[-1]._tr)
    for i, row in enumerate(table.rows[1:]):
        vals = rows[i] if i < len(rows) else ("", "", "")
        for cell, v in zip(row.cells, vals):
            par = cell.paragraphs[0]
            if par.runs:
                par.runs[0].text = _clean(v)
                for extra in par.runs[1:]:
                    extra.text = ""
            else:
                par.add_run(_clean(v))
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def put_cover_first(cover: Path, doc: Path, out: Path) -> Path:
    """One file: the cover page, then a page break, then the body of `doc` (its own header is dropped: the cover's header with both logos is used for all pages)."""
    import copy as _copy
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    base, extra = Document(str(cover)), Document(str(doc))
    body = base.element.body
    sect = body.find(qn("w:sectPr"))
    br = OxmlElement("w:p"); r = OxmlElement("w:r"); b = OxmlElement("w:br"); b.set(qn("w:type"), "page"); r.append(b); br.append(r)
    sect.addprevious(br)
    for el in list(extra.element.body):
        if el.tag == qn("w:sectPr"):
            continue
        new = _copy.deepcopy(el)
        for blip in new.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            if rid and rid in extra.part.rels:
                import io as _io
                new_rid, _ = base.part.get_or_add_image(_io.BytesIO(extra.part.rels[rid].target_part.blob))
                blip.set(qn("r:embed"), new_rid)
        sect.addprevious(new)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(str(out))
    return out


def write_plain_doc(out: Path, title: str, text: str, meta: dict) -> Path:
    """A simple Word file for the extra tools: school logo, title, then the text (bullets, numbers and '|' tables are recognised)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    ctx = _scrub({"t": title, "x": text, "s": meta.get("school"), "u": meta.get("subject"), "n": meta.get("teacher")})
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Pt(54)
    logo = meta.get("logo")
    if logo and Path(logo).is_file():
        doc.add_picture(str(logo), height=Pt(46))
    head = doc.add_paragraph()
    r = head.add_run(ctx["t"]); r.bold = True; r.font.size = Pt(16)
    sub = " · ".join(x for x in (_clean(ctx["s"]), _clean(ctx["u"]), _clean(ctx["n"])) if x)
    if sub:
        doc.add_paragraph(sub)
    arabic = re.compile(r"[\u0600-\u06FF]")

    def rtl(par, line):
        if len(arabic.findall(line)) > len(line) * 0.3:
            par._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
            par.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    rows: list = []

    def flush():
        if not rows:
            return
        width = max(len(r) for r in rows)
        tbl = doc.add_table(rows=len(rows), cols=width)
        tbl.style = "Table Grid"
        for i, row in enumerate(rows):
            for j in range(width):
                cell = tbl.cell(i, j)
                cell.text = row[j] if j < len(row) else ""
                if i == 0:
                    for run in cell.paragraphs[0].runs:
                        run.bold = True
        rows.clear()
        doc.add_paragraph()

    for raw in ctx["x"].splitlines():
        line = raw.rstrip()
        if line.count("|") >= 1 and not line.lstrip().startswith("- "):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
            continue
        flush()
        if not line.strip():
            continue
        if line.lstrip().startswith(("- ", "• ")):
            p = doc.add_paragraph(line.lstrip()[2:].strip(), style="List Bullet")
        elif re.match(r"^[A-Z][A-Z0-9 ,&/()'-]{3,}:?$", line.strip()) or (line.strip().endswith(":") and len(line) < 70):
            p = doc.add_paragraph(); rr = p.add_run(line.strip()); rr.bold = True
        else:
            p = doc.add_paragraph(line.strip())
        rtl(p, line)
    flush()
    out.parent.mkdir(parents=True, exist_ok=True)
    _save(doc, out)
    return out


def template_path(kind: str) -> Path:
    name = TEMPLATES.get(kind)
    f = paths.resources_dir() / name if name else None
    if not f or not f.is_file():
        raise AppError("template_missing", f"Template not found: {kind}", status=500)
    return f
