"""Writes portal/calendar.json, the school calendar the parents' portal shows (terms, holidays, events for the child's grade).
It is made from resources/school_calendar.json, the same file the teacher app uses, so there is one calendar, not two.
Staff-only days are left out. `--check` only says whether portal/calendar.json is up to date (a test runs it).
Run it again whenever resources/school_calendar.json changes (e.g. the new school year)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "resources/school_calendar.json", ROOT / "portal/calendar.json"
GRADES = ["kg1", "kg2"] + [f"g{i}" for i in range(1, 13)]
STAFF = re.compile(r"\bstaff\b", re.I)

# Arabic names for the school's events (the full English name is the key). A name that is not here is shown in English.
AR = {
    "Back To School": "العودة للمدرسة", "Breaking Ice": "كسر الجليد", "Meet & Greet": "لقاء وتعارف",
    "Exam Days": "أيام الامتحانات", "Exams Days": "أيام الامتحانات", "Revision Days": "أيام المراجعة", "Recap Days": "أيام المراجعة السريعة", "Map Test": "اختبار MAP",
    "Parents Meeting / Day Off For Students": "اجتماع أولياء الأمور / إجازة للطلاب", "Art Gallery": "معرض الفنون",
    "Book Week High School (G9 – G11)": "أسبوع الكتاب للمرحلة الثانوية (G9 – G11)", "Book Week KG & Elementary School (KG – G5)": "أسبوع الكتاب لرياض الأطفال والابتدائي (KG – G5)", "Book Week Middle School (G6 – G8)": "أسبوع الكتاب للمرحلة الإعدادية (G6 – G8)",
    "Camera Show Event (KG – G5)": "عرض الكاميرا (KG – G5)", "Character Day Event (KG1 – G5)": "يوم الشخصيات (KG1 – G5)", "DLIS Garage Sale": "بازار DLIS",
    "ELA Learning Journey Project (G6 – G11)": "مشروع رحلة التعلم ELA (G6 – G11)", "ELA Learning Journey Project (KG – G5)": "مشروع رحلة التعلم ELA (KG – G5)",
    "First Day Of Foundation Stage To G3 + Welcome Party": "أول يوم من المرحلة التأسيسية حتى G3 + حفل ترحيب", "First Day Of G4 To G7 + Welcome Party": "أول يوم من G4 حتى G7 + حفل ترحيب", "First Day Of G8 To G11 + Welcome Party": "أول يوم من G8 حتى G11 + حفل ترحيب",
    "First Day Of Trimester Three": "أول يوم في الفصل الدراسي الثالث", "First Day Of Trimester Two / Recap Day": "أول يوم في الفصل الدراسي الثاني / يوم مراجعة", "First day of Ramadan": "أول أيام رمضان",
    "Go Green + Healthy Day Event (KG – G5)": "يوم الأخضر والصحة (KG – G5)", "Holy Quraan Competition (G1 – G5)": "مسابقة القرآن الكريم (G1 – G5)", "Holy Quraan Competition (G6 – G11)": "مسابقة القرآن الكريم (G6 – G11)",
    "La Journee Francoise": "اليوم الفرنسي", "Math Is Fun (G6 – G8)": "الرياضيات ممتعة (G6 – G8)", "Math Is Fun (G9 – G11)": "الرياضيات ممتعة (G9 – G11)", "Math Is Fun (KG – G5)": "الرياضيات ممتعة (KG – G5)",
    "Math Week (G6 – G8)": "أسبوع الرياضيات (G6 – G8)", "Math Week (G9 – G11)": "أسبوع الرياضيات (G9 – G11)", "Math Week (KG – G5)": "أسبوع الرياضيات (KG – G5)",
    "Science Fair (G1 – G5)": "معرض العلوم (G1 – G5)", "Science Fair (G6 – G11)": "معرض العلوم (G6 – G11)",
    "Spelling Bee Round 1 (G1 – G6)": "مسابقة التهجئة، الجولة 1 (G1 – G6)", "Spelling Bee Round 1 (G7 – G11)": "مسابقة التهجئة، الجولة 1 (G7 – G11)",
    "Spelling Bee Round 2 (G1 – G6)": "مسابقة التهجئة، الجولة 2 (G1 – G6)", "Spelling Bee Round 2 (G7 – G11)": "مسابقة التهجئة، الجولة 2 (G7 – G11)",
    "Spelling Bee Round Three (G1 – G6)": "مسابقة التهجئة، الجولة 3 (G1 – G6)", "Spelling Bee Round Three (G7 – G11)": "مسابقة التهجئة، الجولة 3 (G7 – G11)",
    "Sports Day For All School": "اليوم الرياضي لكل المدرسة", "Spring Festival All School": "مهرجان الربيع لكل المدرسة",
    "Trip (G6 – G11)": "رحلة (G6 – G11)", "Trip (KG – G5)": "رحلة (KG – G5)", "Trip For All School": "رحلة لكل المدرسة",
    "6th of October Celebration (Morning Line + First Session)": "احتفال 6 أكتوبر (الطابور والحصة الأولى)",
    "(G9 – G10) Cultural Diversity / (G11) Business Conference": "التنوع الثقافي (G9 – G10) / مؤتمر الأعمال (G11)", "Detacher Carnival": "كرنفال Detacher",
    "(G1 – G8) Cultural Diversity / International Day": "اليوم الدولي والتنوع الثقافي (G1 – G8)", "Winter Festival & Pyjama Day (KG – G5) / Trip (G6 – G11)": "مهرجان الشتاء ويوم البيجامة (KG – G5) / رحلة (G6 – G11)",
}


def _grade_range(a: str, b: str) -> list[str]:
    lo = {"KG": "kg1"}.get(a.upper(), a.lower()); hi = {"KG": "kg2"}.get(b.upper(), b.lower())
    if lo not in GRADES or hi not in GRADES:
        return []
    return GRADES[GRADES.index(lo): GRADES.index(hi) + 1]


def grades_of(name: str):
    """Which grades an event is for, read from the words in its name: '(KG – G5)', '(G11)', 'Foundation Stage To G3'. None = everybody."""
    out: list[str] = []
    for a, b in re.findall(r"\b(KG1?|G\d+)\s*[–-]\s*(KG2?|G\d+)\b", name):
        out += _grade_range(a, b)
    for a, b in re.findall(r"\b(Foundation Stage|G\d+) To (G\d+)\b", name):
        out += _grade_range("KG" if a.startswith("Found") else a, b)
    for g in re.findall(r"\((G\d+)\)", name):
        out += _grade_range(g, g)
    return sorted(set(out), key=GRADES.index) or None


def build() -> dict:
    cal = json.loads(SRC.read_text(encoding="utf-8"))
    holidays = []
    for h in cal["holidays"]:
        en, _, ar = (h["name"].partition(" / "))
        holidays.append({"start": h["start"], "end": h["end"] or h["start"], "en": en.strip(), "ar": ar.strip() or en.strip()})
    events = []
    for e in sorted(cal["events"], key=lambda e: (e["date"], e["name"])):
        if STAFF.search(e["name"]):
            continue
        row = {"date": e["date"], "en": e["name"], "ar": AR.get(e["name"], e["name"])}
        g = grades_of(e["name"])
        if g:
            row["grades"] = g
        events.append(row)
    terms = [{"start": t["start"], "end": t["end"], "week1": t.get("week1_start") or t["start"]} for t in cal["trimesters"]]
    return {"year": cal["academic_year"], "terms": terms, "holidays": holidays, "events": events}


def text() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text()
        print("portal/calendar.json is up to date" if ok else "portal/calendar.json is out of date: run python3 scripts/make_portal_calendar.py")
        sys.exit(0 if ok else 1)
    OUT.write_text(text(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
