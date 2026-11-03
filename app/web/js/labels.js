// Names shown on screen: grades, classes, days, dates - in the user's language.
import { t, getLang } from "./i18n.js";

export const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export const dayName = (d) => t(`day_${d}`);

export function gradeName(g) {
  return getLang() === "ar" && g.name_ar ? g.name_ar : g.name;
}
export function stageName(s) {
  return getLang() === "ar" && s.name_ar ? s.name_ar : s.name;
}

// "Grade 4 A" -> "الصف الرابع A" in Arabic
export function roomLabel(room, structure) {
  const g = structure.grades.find((x) => x.id === room.grade_id);
  if (!g) return room.name;
  if (room.name.startsWith(g.name)) {
    const rest = room.name.slice(g.name.length).trim();
    return rest ? `${gradeName(g)} ${rest}` : gradeName(g);
  }
  return room.name;
}

const locale = () => (getLang() === "ar" ? "ar-EG-u-nu-latn" : "en-GB");

export function fmtDate(iso, opts = { weekday: "long", day: "numeric", month: "long" }) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale(), { ...opts, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}
export const fmtDay = (iso) => fmtDate(iso, { weekday: "long", day: "numeric", month: "short" });
export const fmtShort = (iso) => fmtDate(iso, { day: "numeric", month: "short" });

export const todayIso = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

export function addDays(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

export const triName = (name) => {
  const m = /^T(\d+)$/.exec(name || "");
  return m ? t("trimester_n", { n: m[1] }) : name;
};

export function subjectLabel(en, subjects) {
  const s = (subjects || []).find((x) => x.en === en);
  return s ? (getLang() === "ar" ? s.ar : s.en) : en;
}

// Holiday names from the school calendar are stored as "English / عربي". Show the one for the current language.
export function localName(name) {
  const parts = String(name || "").split(" / ");
  if (parts.length < 2) return name || "";
  const ar = parts.find((x) => /[\u0600-\u06FF]/.test(x));
  const en = parts.find((x) => !/[\u0600-\u06FF]/.test(x));
  return (getLang() === "ar" ? ar || en : en || ar) || name;
}

// Consecutive days with the same name become one entry: "Winter Break 27 Dec → 31 Dec".
export function groupHolidays(list) {
  const out = [];
  for (const x of list) {
    const last = out[out.length - 1];
    if (last && last.name === x.name) last.to = x.date; else out.push({ name: x.name, from: x.date, to: x.date });
  }
  return out;
}

// "Grade 4 A" -> "G4 A", "KG 1 A" -> "KG1 A" (used where space is tight, like the timetable table)
export function shortRoomLabel(room, structure) {
  const g = structure.grades.find((x) => x.id === room.grade_id);
  const m = g && /^(kg)(\d+)$|^g(\d+)$/.exec(g.id);
  if (!m) return roomLabel(room, structure);
  const code = m[1] ? `KG${m[2]}` : `G${m[3]}`;
  const rest = room.name.startsWith(g.name) ? room.name.slice(g.name.length).trim() : room.name;
  return rest ? `${code} ${rest}` : code;
}

// 24-hour "13:40" -> "1:40 PM" (Arabic: "1:40 م")
export function fmt12(hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ""));
  if (!m) return hhmm || "";
  const h = +m[1], pm = h >= 12;
  const h12 = h % 12 || 12;
  return `${h12}:${m[2]} ${getLang() === "ar" ? (pm ? "م" : "ص") : (pm ? "PM" : "AM")}`;
}

// A colour for each school stage, taken from the logo, so a glance at the day shows which age group each lesson is.
export function stageTone(gradeId) {
  const id = String(gradeId || "");
  if (id.startsWith("kg")) return "#8fb83f";
  const n = parseInt(id.replace(/\D/g, ""), 10);
  if (!n) return "#2f82a8";
  return n <= 3 ? "#4aa3cf" : n <= 6 ? "#2f82a8" : n <= 9 ? "#2d6b86" : "#2a2a72";
}

// Names on the school map (floors and rooms). Shown in Arabic in the Arabic UI; anything the teacher typed herself is left as typed.
const MAP_AR = {
  "ground floor": "الدور الأرضي", "first floor": "الدور الأول", "second floor": "الدور الثاني", "third floor": "الدور الثالث",
  "photocopy office": "مكتب التصوير", "hr & student affairs": "شئون العاملين وشئون الطلاب", "store": "المخزن", "canteen": "الكانتين",
  "admission room": "غرفة القبول", "administrative manager": "المدير الإداري", "financial expert": "الخبير المالي", "art room": "غرفة الفنون",
  "reception": "الاستقبال", "it lab": "معمل الكمبيوتر (IT)", "art store": "مخزن الفن", "special needs class": "فصل ذوي الاحتياجات الخاصة",
  "principal's office": "مكتب المدير", "french class": "فصل الفرنساوي", "isolation room": "غرفة العزل", "kg1": "كي جي 1", "kg2": "كي جي 2",
};
const ORD = ["", "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر", "الحادي عشر", "الثاني عشر"];
export function mapName(name) {
  const n = localName(name);
  if (getLang() !== "ar" || /[؀-ۿ]/.test(n)) return n;
  const k = String(n).trim().toLowerCase();
  if (MAP_AR[k]) return MAP_AR[k];
  const g = /^grade (\d+)$/.exec(k);
  if (g && ORD[+g[1]]) return `الصف ${ORD[+g[1]]}`;
  return n;
}
