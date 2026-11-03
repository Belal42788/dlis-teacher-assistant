"""Arabic student names -> English spelling, offline (names never leave the computer).

A list of common names gives the usual English spelling; anything else is spelled letter by letter.
It is a helper: the teacher can always correct the English name by hand.
"""
from __future__ import annotations

import re

_AR = re.compile(r"[؀-ۿ]")
_DIAC = re.compile(r"[ً-ٰٟـ]")

WORDS = {
    # boys
    "محمد": "Mohamed", "احمد": "Ahmed", "محمود": "Mahmoud", "مصطفى": "Mostafa", "مصطفي": "Mostafa", "علي": "Ali", "على": "Ali", "عمر": "Omar",
    "يوسف": "Youssef", "ابراهيم": "Ibrahim", "اسماعيل": "Ismail", "اسلام": "Islam", "خالد": "Khaled", "حسن": "Hassan", "حسين": "Hussein",
    "عمرو": "Amr", "كريم": "Karim", "طارق": "Tarek", "زياد": "Ziad", "ياسين": "Yassin", "يس": "Yassin", "يحيى": "Yahya", "يحيي": "Yahya",
    "ادم": "Adam", "آدم": "Adam", "سليم": "Salim", "سليمان": "Soliman", "عثمان": "Othman", "عادل": "Adel", "فؤاد": "Fouad", "امام": "Emam",
    "وليد": "Walid", "صبري": "Sabry", "مبارك": "Mubarak", "رضا": "Reda", "عباس": "Abbas", "قاسم": "Kassem", "زكريا": "Zakaria", "لطفي": "Lotfy",
    "لطفى": "Lotfy", "تيم": "Taym", "منصور": "Mansour", "ممدوح": "Mamdouh", "عطا": "Atta", "شعبان": "Shaaban", "فتح": "Fathallah", "الله": "Allah",
    "صالح": "Saleh", "سعيد": "Said", "سيد": "Sayed", "السيد": "El Sayed", "جمال": "Gamal", "كمال": "Kamal", "هشام": "Hisham", "هاني": "Hany",
    "ايمن": "Ayman", "أيمن": "Ayman", "باسم": "Bassem", "بلال": "Bilal", "حمزة": "Hamza", "حمدي": "Hamdy", "رامي": "Rami", "ريان": "Rayan",
    "سامي": "Samy", "سامر": "Samer", "سيف": "Seif", "شريف": "Sherif", "صلاح": "Salah", "ضياء": "Diaa", "طه": "Taha", "عاصم": "Assem",
    "عبدالله": "Abdullah", "عبدالرحمن": "Abdelrahman", "عصام": "Essam", "عماد": "Emad", "عزت": "Ezzat", "فارس": "Fares", "فادي": "Fady",
    "فهد": "Fahd", "ماجد": "Maged", "مازن": "Mazen", "مالك": "Malek", "مروان": "Marwan", "معاذ": "Moaz", "مؤمن": "Moamen", "مهند": "Mohannad",
    "نادر": "Nader", "ناصر": "Nasser", "نبيل": "Nabil", "هيثم": "Haitham", "ياسر": "Yasser", "يامن": "Yamen", "إياد": "Eyad", "اياد": "Eyad",
    "انس": "Anas", "أنس": "Anas", "بدر": "Badr", "جاسم": "Jassim", "رائد": "Raed", "رمضان": "Ramadan", "زين": "Zein", "سعد": "Saad",
    "سلمان": "Salman", "شادي": "Shady", "صبحي": "Sobhy", "عاطف": "Atef", "عبد": "Abd", "عزيز": "Aziz", "علاء": "Alaa", "غانم": "Ghanem",
    "فيصل": "Faisal", "لؤي": "Louay", "محسن": "Mohsen", "مجدي": "Magdy", "ممدوح ": "Mamdouh", "نور": "Nour", "هادي": "Hadi", "وائل": "Wael",
    # girls
    "مريم": "Mariam", "فاطمة": "Fatma", "عائشة": "Aisha", "عايشة": "Aisha", "سارة": "Sara", "ساره": "Sara", "نور": "Nour", "نورا": "Nora",
    "هبة": "Heba", "منى": "Mona", "منة": "Menna", "ياسمين": "Yasmin", "جنى": "Jana", "جني": "Jana", "لينا": "Lina", "ليلى": "Layla",
    "ليلي": "Layla", "رنا": "Rana", "رهف": "Rahaf", "ريم": "Reem", "سلمى": "Salma", "سلمي": "Salma", "شهد": "Shahd", "ملك": "Malak",
    "هنا": "Hana", "هنى": "Hana", "دعاء": "Doaa", "آية": "Aya", "اية": "Aya", "ايه": "Aya", "اسراء": "Esraa", "إسراء": "Esraa", "الاء": "Alaa",
    "امينة": "Amina", "أمينة": "Amina", "بسمة": "Basma", "تقى": "Toqa", "تقي": "Toqa", "جميلة": "Gamila", "حبيبة": "Habiba", "حنان": "Hanan",
    "خديجة": "Khadija", "دينا": "Dina", "رحمة": "Rahma", "رقية": "Ruqayya", "رودينا": "Rodina", "زينب": "Zeinab", "سعاد": "Souad",
    "سما": "Sama", "سمية": "Sumaya", "سهى": "Soha", "شيماء": "Shaimaa", "صفية": "Safia", "عالية": "Alia", "غزل": "Ghazal", "فرح": "Farah",
    "كارما": "Karma", "لمى": "Lama", "لمياء": "Lamia", "ليان": "Lian", "مها": "Maha", "ميار": "Mayar", "ميرنا": "Mirna", "ندى": "Nada",
    "نسمة": "Nesma", "نهى": "Noha", "هالة": "Hala", "هدى": "Hoda", "هند": "Hind", "وفاء": "Wafaa", "ياسمينا": "Yasmina", "يمنى": "Yomna",
    "جودي": "Judy", "جودى": "Judy", "جميل": "Gamil", "كنزي": "Kenzy", "ريتاج": "Ritaj", "روان": "Rawan", "روفيدا": "Rofayda",
    # common family words
    "فتح الله": "Fathallah", "عبد الرحمن": "Abdelrahman", "عبد الله": "Abdullah", "عبد العزيز": "Abdelaziz", "عبد الحميد": "Abdelhamid",
    "عبد الحافظ": "Abdel Hafez", "عبد الفتاح": "Abdelfattah", "عبد الناصر": "Abdelnasser", "عبد المنعم": "Abdelmoneim", "انور": "Anwar", "أنور": "Anwar",
    "نادين": "Nadine", "ادهم": "Adham", "ان": "An", "ابو": "Abu", "ام": "Om", "بن": "Bin", "ابن": "Ibn",
}

_LETTERS = {
    "ا": "a", "أ": "a", "إ": "e", "آ": "a", "ء": "", "ؤ": "o", "ئ": "e", "ب": "b", "ت": "t", "ث": "th", "ج": "g", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh",
    "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "a", "و": "w", "ي": "y", "ى": "a", "ئ ": "e",
}


def _norm(word: str) -> str:
    return _DIAC.sub("", word).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه").strip()


from .translit_names import pairs as _more

_KEYS = {_norm(k): v for k, v in _more().items()}
_KEYS.update({_norm(k): v for k, v in WORDS.items()})       # the first list wins when both have a name


_VOWELS = ("a", "e", "o", "i", "u", "ou")


def _spell(word: str) -> str:
    """Letter by letter, for names that are not in the lists. Arabic does not write short vowels, so an 'a' is put in when
    three consonants would meet, and a letter waw / yaa inside the word becomes 'ou' / 'i' as in Nour and Nabil."""
    w = _DIAC.sub("", word)
    parts = []
    tail = ""
    if len(w) > 3 and w[-1] in "هة":
        w, tail = w[:-1], "a"
    for i, ch in enumerate(w):
        if ch == "و" and 0 < i < len(w) - 1:
            parts.append("ou")
        elif ch == "ي" and 0 < i < len(w) - 1:
            parts.append("i")
        elif ch in "اأآ" and 0 < i:
            parts.append("a")
        else:
            parts.append(_LETTERS.get(ch, ch))
    out, run = [], 0
    if len(parts) > 2 and parts[0] and parts[1] and parts[0][0] not in "aeiou" and parts[1][0] not in "aeiou":
        parts.insert(1, "a")
    for p in parts:
        if not p:
            continue
        if p[0].lower() in "aeiou":
            run = 0
        else:
            run += 1
            if run == 3:
                out.append("a"); run = 1
        out.append(p)
    s = "".join(out) + tail
    return s[:1].upper() + s[1:]


def to_english(name: str) -> str:
    """'محمد احمد' -> 'Mohamed Ahmed'. Text without Arabic letters is returned unchanged."""
    name = " ".join(str(name or "").split())
    if not _AR.search(name):
        return name
    words = name.split(" ")
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        n = _norm(w)
        pair = _norm(" ".join(words[i:i + 2]))
        if pair in _KEYS and i + 1 < len(words):
            out.append(_KEYS[pair]); i += 2; continue
        if n == "عبد" and i + 1 < len(words):  # Abdel + name (عبد الله is one name)
            nxt = _norm(words[i + 1])
            if nxt == "الله":
                out.append("Abdullah")
            elif nxt.startswith("ال"):
                out.append("Abdel " + (_KEYS.get(nxt) or _spell(nxt[2:]) ))
            else:
                out.append("Abdel " + (_KEYS.get(nxt) or _spell(words[i + 1])))
            i += 2; continue
        if n.startswith("عبد") and len(n) > 3 and n not in _KEYS:  # عبدالرحمن written as one word
            rest = n[3:]
            out.append("Abdel " + (_KEYS.get(rest) or _spell(rest[2:] if rest.startswith("ال") else rest)))
            i += 1; continue
        if n in _KEYS:
            out.append(_KEYS[n])
        elif n.startswith("ال") and len(n) > 3:
            out.append("El " + (_KEYS.get(n[2:]) or _spell(w[2:] if w.startswith("ال") else n[2:])))
        else:
            out.append(_spell(w))
        i += 1
    return " ".join(out)


_EN2AR = {}
for _k, _v in WORDS.items():
    _EN2AR.setdefault(_v.lower().replace(" ", ""), _k)
_EN2AR.update({"abdel": "عبد", "abd": "عبد", "el": "ال", "al": "ال", "mohamed": "محمد", "mohammed": "محمد", "muhammad": "محمد",
               "ahmed": "أحمد", "ahmad": "أحمد", "mahmoud": "محمود", "ali": "علي", "omar": "عمر", "youssef": "يوسف", "yousef": "يوسف"})
_DIGRAPHS = [("sh", "ش"), ("kh", "خ"), ("gh", "غ"), ("th", "ث"), ("ee", "ي"), ("oo", "و"), ("ou", "و"), ("aa", "ا"), ("ei", "ي"), ("ai", "ي")]
_SINGLE = {"a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف", "g": "ج", "h": "ه", "i": "ي", "j": "ج", "k": "ك", "l": "ل",
           "m": "م", "n": "ن", "o": "و", "p": "ب", "q": "ق", "r": "ر", "s": "س", "t": "ت", "u": "و", "v": "ف", "w": "و", "x": "كس",
           "y": "ي", "z": "ز"}


def _en_word(w: str) -> str:
    lw = w.lower()
    if lw in _EN2AR:
        return _EN2AR[lw]
    out, i = [], 0
    while i < len(lw):
        for d, a in _DIGRAPHS:
            if lw.startswith(d, i):
                out.append(a); i += 2; break
        else:
            ch = lw[i]
            if ch in "aeiou" and 0 < i:  # inner short vowels are normally not written
                if ch in "ou" or i == len(lw) - 1 and ch in "ai":
                    out.append(_SINGLE[ch])
            else:
                out.append(_SINGLE.get(ch, ch))
            i += 1
    return "".join(out)


def to_arabic(name: str) -> str:
    """'Mohamed Ahmed' -> 'محمد أحمد' (best effort; the teacher can edit). Text that already has Arabic is returned unchanged."""
    name = " ".join(str(name or "").split())
    if not name or _AR.search(name):
        return name
    ws = name.split(" ")
    out, i = [], 0
    while i < len(ws):
        if ws[i].lower() in ("abdel", "abd") and i + 1 < len(ws):
            nxt = ws[i + 1]
            out.append("عبد" + (_en_word(nxt) if nxt.lower() not in ("allah", "ullah") else "الله")); i += 2; continue
        if ws[i].lower() in ("el", "al") and i + 1 < len(ws):
            out.append("ال" + _en_word(ws[i + 1])); i += 2; continue
        out.append(_en_word(ws[i])); i += 1
    return " ".join(out)
