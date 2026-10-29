"""Ready-made stages and grades so nobody has to type them."""
from __future__ import annotations

from .models import AgeBand

STAGE_PRESETS = [
    {"id": "kg", "name": "KG", "name_ar": "رياض الأطفال", "order": 0},
    {"id": "primary", "name": "Primary", "name_ar": "الابتدائي", "order": 1},
    {"id": "preparatory", "name": "Preparatory", "name_ar": "الإعدادي", "order": 2},
    {"id": "high_school", "name": "High School", "name_ar": "الثانوي", "order": 3},
]

_AR_NUM = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس", 6: "السادس",
           7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر", 11: "الحادي عشر", 12: "الثاني عشر"}


def _grade_presets() -> list[dict]:
    out: list[dict] = []
    for i in (1, 2):
        out.append({"id": f"kg{i}", "name": f"KG{i}", "name_ar": f"كي جي {i}",
                    "stage_id": "kg", "order": i - 1, "age_band": AgeBand.KG.value})
    for n in range(1, 13):
        if n <= 5:
            stage = "primary"
        elif n <= 8:
            stage = "preparatory"
        else:
            stage = "high_school"
        if n <= 2:
            band = AgeBand.LOWER_PRIMARY
        elif n <= 5:
            band = AgeBand.UPPER_PRIMARY
        elif n <= 8:
            band = AgeBand.PREPARATORY
        else:
            band = AgeBand.SECONDARY
        out.append({"id": f"g{n}", "name": f"Grade {n}", "name_ar": f"الصف {_AR_NUM[n]}",
                    "stage_id": stage, "order": n + 1, "age_band": band.value})
    return out


GRADE_PRESETS = _grade_presets()
GRADE_PRESET_BY_ID = {g["id"]: g for g in GRADE_PRESETS}
STAGE_PRESET_BY_ID = {s["id"]: s for s in STAGE_PRESETS}

ROOM_LETTERS = "ABCDEFGH"

COMMON_SUBJECTS = [
    ("ICT", "تكنولوجيا المعلومات"), ("Math", "الرياضيات"), ("Science", "العلوم"),
    ("English", "اللغة الإنجليزية"), ("Arabic", "اللغة العربية"), ("Social Studies", "الدراسات الاجتماعية"),
    ("Islamic Studies", "التربية الإسلامية"), ("French", "اللغة الفرنسية"), ("German", "اللغة الألمانية"),
    ("Art", "التربية الفنية"), ("Music", "الموسيقى"), ("PE", "التربية البدنية"),
]
