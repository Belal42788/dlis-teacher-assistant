"""Builds resources/school_calendar.json from the DLIS American Calendar 2026-2027 PDF (typed in by hand)."""
import json
from datetime import date, timedelta
from pathlib import Path

Y = 2026
def d(m, day, y=None):
    return date(y or (2026 if m >= 8 else 2027), m, day)

holidays = [  # (start, end, "English / Arabic")
    (d(8, 27), None, "El Mouled El Nabawy Off / المولد النبوي"),
    (d(10, 6), None, "6th of October Celebration Day Off / عيد القوات المسلحة"),
    (d(11, 25), d(11, 26), "Long Weekend / إجازة طويلة"),
    (d(12, 27), d(12, 31), "Winter Break / إجازة الشتاء"),
    (d(1, 7), None, "Coptic Christmas Day / عيد الميلاد المجيد"),
    (d(1, 25), None, "National Police Day / عيد الشرطة"),
    (d(1, 31), d(2, 8), "Mid-Year Vacation / إجازة نصف العام"),
    (d(3, 7), d(3, 11), "Eid Al-Fitr Vacation / إجازة عيد الفطر"),
    (d(4, 11), d(4, 15), "Spring Break / إجازة الربيع"),
    (d(4, 25), None, "Sinai Liberation Day / عيد تحرير سيناء"),
    (d(5, 3), None, "Sham El Nessim / شم النسيم"),
    (d(5, 16), d(5, 20), "Eid Al-Adha Vacation / إجازة عيد الأضحى"),
    (d(6, 6), None, "Islamic New Year / رأس السنة الهجرية"),
    (d(6, 27), d(8, 31), "Summer Vacation / الإجازة الصيفية"),
]
events = [  # (start, end, name)
    (d(8, 16), None, "Staff Return"), (d(8, 30), None, "New Staff Return"), (d(8, 30), d(9, 2), "Training For Staff"),
    (d(9, 3), None, "Meet & Greet"),
    (d(9, 6), None, "First Day Of Foundation Stage To G3 + Welcome Party"),
    (d(9, 7), None, "First Day Of G4 To G7 + Welcome Party"),
    (d(9, 8), None, "First Day Of G8 To G11 + Welcome Party"),
    (d(9, 10), None, "Breaking Ice"), (d(9, 24), None, "Sports Day For All School"),
    (d(10, 1), None, "Character Day Event (KG1 – G5)"),
    (d(10, 5), None, "6th of October Celebration (Morning Line + First Session)"),
    (d(10, 7), None, "Trip (KG – G5)"),
    (d(10, 12), None, "Spelling Bee Round 1 (G1 – G6)"), (d(10, 14), None, "Spelling Bee Round 1 (G7 – G11)"),
    (d(10, 15), None, "Trip (G6 – G11)"),
    (d(10, 19), None, "Book Week KG & Elementary School (KG – G5)"),
    (d(10, 21), None, "Book Week Middle School (G6 – G8)"), (d(10, 22), None, "Book Week High School (G9 – G11)"),
    (d(11, 2), None, "(G9 – G10) Cultural Diversity / (G11) Business Conference"),
    (d(11, 5), None, "(G1 – G8) Cultural Diversity / International Day"),
    (d(11, 8), d(11, 12), "Map Test"),
    (d(11, 15), d(11, 17), "Revision Days"), (d(11, 18), d(11, 24), "Exams Days"),
    (d(11, 29), None, "First Day Of Trimester Two / Recap Day"),
    (d(11, 30), None, "Camera Show Event (KG – G5)"),
    (d(12, 3), None, "Parents Meeting / Day Off For Students"),
    (d(12, 7), None, "Math Is Fun (KG – G5)"), (d(12, 9), None, "Math Is Fun (G6 – G8)"), (d(12, 10), None, "Math Is Fun (G9 – G11)"),
    (d(12, 14), None, "Spelling Bee Round 2 (G1 – G6)"), (d(12, 16), None, "Spelling Bee Round 2 (G7 – G11)"),
    (d(12, 17), None, "اليوم العالمي للغة العربية"),
    (d(12, 24), None, "Go Green + Healthy Day Event (KG – G5)"),
    (d(1, 4), None, "Winter Festival & Pyjama Day (KG – G5) / Trip (G6 – G11)"),
    (d(1, 14), None, "DLIS Garage Sale"), (d(1, 18), None, "La Journee Francoise"), (d(1, 21), None, "Detacher Carnival"),
    (d(1, 27), None, "Trip (KG – G5)"),
    (d(2, 8), None, "First day of Ramadan"),
    (d(2, 9), None, "Back To School"),
    (d(2, 21), d(2, 23), "Revision Days"), (d(2, 24), d(3, 2), "Exam Days"),
    (d(3, 3), d(3, 4), "Recap Days"),
    (d(3, 14), None, "First Day Of Trimester Three"),
    (d(3, 18), None, "Parents Meeting / Day Off For Students"),
    (d(3, 22), None, "Math Week (G6 – G8)"), (d(3, 24), None, "Math Week (KG – G5)"), (d(3, 25), None, "Math Week (G9 – G11)"),
    (d(3, 29), None, "Spelling Bee Round Three (G7 – G11)"), (d(3, 30), None, "Spelling Bee Round Three (G1 – G6)"),
    (d(3, 31), None, "Holy Quraan Competition (G6 – G11)"),
    (d(4, 1), None, "Holy Quraan Competition (G1 – G5)"),
    (d(4, 5), None, "Science Fair (G1 – G5)"), (d(4, 6), None, "Science Fair (G6 – G11)"), (d(4, 8), None, "Spring Festival All School"),
    (d(4, 19), None, "ELA Learning Journey Project (G6 – G11)"), (d(4, 20), None, "ELA Learning Journey Project (KG – G5)"),
    (d(4, 22), None, "Trip For All School"),
    (d(5, 9), d(5, 13), "Map Test"), (d(5, 31), None, "Art Gallery"),
    (d(6, 7), d(6, 10), "Revision Days"), (d(6, 13), d(6, 17), "Exam Days"), (d(6, 20), d(6, 24), "Recap Days"),
]
def days(a, b):
    b = b or a
    while a <= b:
        yield a
        a += timedelta(days=1)

cal = {
    "academic_year": "2026-2027",
    "trimesters": [
        {"name": "T1", "start": "2026-09-06", "end": "2026-11-26", "week1_start": "2026-09-06"},
        {"name": "T2", "start": "2026-11-29", "end": "2027-03-04", "week1_start": "2026-11-29"},
        {"name": "T3", "start": "2027-03-14", "end": "2027-06-24", "week1_start": "2027-03-14"},
    ],
    "holidays": [{"start": a.isoformat(), "end": b.isoformat() if b else "", "name": n} for a, b, n in holidays],
    "events": sorted(({"date": x.isoformat(), "name": n} for a, b, n in events for x in days(a, b)), key=lambda e: e["date"]),
}
out = Path(__file__).resolve().parent.parent / "resources" / "school_calendar.json"
out.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(cal["holidays"]), "holidays", len(cal["events"]), "events")
