"use strict";
import { state } from "./core.js";

const ar = {
  app: "بوابة الأسرة", school: "دار لقمان الحكيم الدولية",
  // sign in
  login: "تسجيل الدخول", signup: "إنشاء حساب", email: "البريد الإلكتروني", pass: "كلمة السر", code: "كود التفعيل من المدرسة", codeHint: "كود ولي الأمر أو كود الطالب، حسب اللي المدرسة سلّمته لك.",
  haveAcc: "عندي حساب", noAcc: "أول مرة؟ أنشئ حساب", forgot: "نسيت كلمة السر", sent: "لو الحساب موجود هيوصلك رابط على البريد.", pw8: "كلمة السر لازم تكون 8 حروف على الأقل.",
  welcomeTitle: "أهلًا بك في بوابة الأسرة", welcomeText: "درجات وملفات وخطة الأسبوع والرسائل مع المدرسين، في مكان واحد.",
  unconfirmed: "البريد ده لسه متأكدش. اطلب من المدرسة تأكيده.", rate: "السيرفر بعت رسائل كتير. استنى ساعة وجرّب تاني.", badLogin: "البريد أو كلمة السر مش صح.",
  locked: "جرّبت كذا كود غلط، فالحساب اتقفل لحمايتك. كلّم المدرسة عشان تفتحه لك.", badCode: "الكود مش صح أو اتستخدم قبل كده. اطلب كود جديد من المدرسة.", net: "مش قادر أوصل للسيرفر. اتأكد من النت.", notSet: "البوابة لسه ما اتظبطتش (عنوان السيرفر ناقص).",
  newPassTitle: "اكتب كلمة سر جديدة", newPassLead: "اختار كلمة سر جديدة لحسابك (8 حروف على الأقل).", newPass: "كلمة السر الجديدة", newPass2: "اكتبها تاني", savePass: "حفظ كلمة السر", passSaved: "اتغيّرت كلمة السر.", passDiff: "الكلمتين مش زي بعض.", linkOld: "رابط الاستعادة انتهى أو اتستخدم قبل كده. اطلب رابط جديد من «نسيت كلمة السر».",
  staffAccount: "ده حساب مدرس أو إدارة. استخدم برنامج المدرس على الكمبيوتر.", loading: "جارٍ التحميل…", retry: "إعادة المحاولة",
  // roles and account
  parent: "ولي الأمر", student: "الطالب", teacher: "المدرس", admin: "الإدارة", parentAcc: "حساب ولي الأمر", studentAcc: "حساب الطالب",
  account: "حسابي", signedAs: "داخل بحساب", out: "تسجيل الخروج", lang: "English", children: "الأبناء", myself: "بياناتي",
  addKid: "ربط ابن أو ابنة بكود", addKidText: "لو عندك ابن تاني في المدرسة، اكتب كوده هنا.", add: "إضافة", noKids: "لسه ما فيش طالب مربوط بحسابك. اكتب الكود اللي المدرسة سلّمته لك.",
  // navigation
  home: "الرئيسية", study: "الدراسة", talk: "التواصل", week: "هذا الأسبوع", files: "الملفات", grades: "الدرجات", messages: "الرسائل", news: "الإعلانات",
  // dates
  term: "الفصل الدراسي", wk: "الأسبوع", latest: "الأحدث", general: "ملفات عامة", allKinds: "الكل", files_n: "ملف", news_n: "إعلان",
  // home
  hello: "أهلًا", following: "بتتابع", classWord: "الفصل", seeAll: "عرض الكل", open: "فتح",
  homeWeek: "الأسبوع الحالي", homeFiles: "آخر الملفات", homeNews: "آخر الإعلانات", homeTalk: "الرسائل", unread: "غير مقروءة", noUnread: "مفيش رسائل جديدة.", startTalk: "ابدأ محادثة مع مدرس",
  // study
  homework: "الواجبات", material: "مواد إضافية", quizzes: "تنبيهات الكويزات", noWeek: "خطة الأسبوع لسه ما اتنشرتش.", weekFiles: "ملفات الأسبوع", pickWeek: "اختر الأسبوع",
  noFiles: "مفيش ملفات متاحة دلوقتي.", noFilesWeek: "مفيش ملفات في الأسبوع ده.", noGrades: "مفيش درجات متسجلة لسه.", noNews: "مفيش إعلانات حاليًا.",
  kind: { presentation: "عرض تقديمي", quiz: "كويز", revision: "مراجعة", link: "رابط", other: "ملف", message: "رسالة من المدرس" },
  items: { Behavior: "السلوك", Attendance: "الحضور", Classwork: "شغل الفصل", Homework: "الواجب", Quiz: "الكويز", "Quiz Score": "درجة الكويز", Total: "المجموع" }, total: "المجموع", itemCol: "البند",
  // messages
  newMsg: "رسالة جديدة", chooseTeacher: "اختر المدرس", noTeachers: "لسه مفيش مدرسين متسجلين لفصل الطالب.", noThreads: "لسه ما فيش محادثات.", noThreadsText: "اضغط «رسالة جديدة» عشان تكلم أحد المدرسين.",
  talkParent: "محادثة ولي الأمر", talkStudent: "محادثة الطالب", talkParentNote: "ولي الأمر (الأب والأم معًا) مع المدرس", talkStudentNote: "الطالب مع المدرس",
  readOnly: "دي محادثة {who}. تقدر تقراها بس.", writeHere: "اكتب رسالتك…", sendBtn: "إرسال", noMsgs: "لسه ما فيش رسائل. ابدأ بالسلام.", back: "رجوع",
  report: "إبلاغ", reportWhy: "سبب البلاغ (اختياري)", reportSend: "إرسال البلاغ", reportDone: "وصل البلاغ للإدارة.", reportAgain: "أنت بلّغت عن الرسالة دي قبل كده.", cancel: "إلغاء",
  watched: "إدارة المدرسة تقدر تراجع المحادثات للحماية. الرسائل نص فقط، وما بتتعدلش بعد الإرسال.", you: "أنت", sendFail: "الرسالة ما اتبعتتش. جرّب تاني.",
  // calendar and new
  calendar: "التقويم", comingUp: "قريبًا في المدرسة", today: "النهارده", tomorrow: "بكرة", inDays: "بعد {n} يوم", noTerm: "إحنا دلوقتي بين فصلين دراسيين أو في الإجازة.", calKind: { holiday: "إجازة", exam: "امتحانات ومراجعة", event: "فعالية" },
  calNote: "ده تقويم المدرسة. المواعيد ممكن تتغير، والمدرسة بتعلن أي تغيير في الإعلانات.", newWord: "جديد",
  forWho: "لـ", textOnly: "نص فقط", chars: "حرف",
};
const en = {
  app: "Family portal", school: "Dar Luqman Al-Hakim International School",
  login: "Sign in", signup: "Create account", email: "Email", pass: "Password", code: "Activation code from the school", codeHint: "The parent code or the student code, whichever the school gave you.",
  haveAcc: "I have an account", noAcc: "First time? Create an account", forgot: "Forgot password", sent: "If the account exists, a link was sent to your email.", pw8: "The password must be at least 8 characters.",
  welcomeTitle: "Welcome to the family portal", welcomeText: "Grades, files, the week plan and messages with teachers, in one place.",
  unconfirmed: "This email is not confirmed yet. Ask the school to confirm it.", rate: "The server sent too many emails. Wait an hour and try again.", badLogin: "The email or password is not right.",
  locked: "Too many wrong codes, so this account is locked to protect it. Ask the school to unlock it.", badCode: "The code is wrong or already used. Ask the school for a new one.", net: "Could not reach the server. Check the internet.", notSet: "The portal is not set up yet (server address missing).",
  newPassTitle: "Choose a new password", newPassLead: "Choose a new password for your account (at least 8 characters).", newPass: "New password", newPass2: "Type it again", savePass: "Save password", passSaved: "Your password was changed.", passDiff: "The two passwords are not the same.", linkOld: "The reset link has expired or was already used. Ask for a new one with “Forgot password”.",
  staffAccount: "This is a teacher or office account. Use the teacher app on the computer.", loading: "Loading…", retry: "Try again",
  parent: "Parent", student: "Student", teacher: "Teacher", admin: "School office", parentAcc: "Parent account", studentAcc: "Student account",
  account: "My account", signedAs: "Signed in as", out: "Sign out", lang: "العربية", children: "Children", myself: "My details",
  addKid: "Link a child with a code", addKidText: "If you have another child at the school, type their code here.", add: "Add", noKids: "No student is linked to your account yet. Type the code the school gave you.",
  home: "Home", study: "Study", talk: "Talk", week: "This week", files: "Files", grades: "Grades", messages: "Messages", news: "Announcements",
  term: "Term", wk: "Week", latest: "Latest", general: "General files", allKinds: "All", files_n: "files", news_n: "items",
  hello: "Hello", following: "Following", classWord: "Class", seeAll: "See all", open: "Open",
  homeWeek: "Current week", homeFiles: "Latest files", homeNews: "Latest announcements", homeTalk: "Messages", unread: "unread", noUnread: "No new messages.", startTalk: "Start a conversation with a teacher",
  homework: "Homework", material: "Extra material", quizzes: "Quiz alerts", noWeek: "The week plan is not published yet.", weekFiles: "This week's files", pickWeek: "Pick the week",
  noFiles: "Nothing shared right now.", noFilesWeek: "No files in this week.", noGrades: "No grades yet.", noNews: "No announcements right now.",
  kind: { presentation: "Presentation", quiz: "Quiz", revision: "Revision", link: "Link", other: "File", message: "Message from the teacher" },
  items: { Behavior: "Behavior", Attendance: "Attendance", Classwork: "Classwork", Homework: "Homework", Quiz: "Quiz", "Quiz Score": "Quiz score", Total: "Total" }, total: "Total", itemCol: "Item",
  newMsg: "New message", chooseTeacher: "Choose the teacher", noTeachers: "No teachers are registered for the student's class yet.", noThreads: "No conversations yet.", noThreadsText: "Press “New message” to talk to a teacher.",
  talkParent: "Parent conversation", talkStudent: "Student conversation", talkParentNote: "The parents (father and mother together) with the teacher", talkStudentNote: "The student with the teacher",
  readOnly: "This is the {who} conversation. You can read it only.", writeHere: "Write your message…", sendBtn: "Send", noMsgs: "No messages yet. Start by saying hello.", back: "Back",
  report: "Report", reportWhy: "Reason (optional)", reportSend: "Send report", reportDone: "The report reached the school office.", reportAgain: "You already reported this message.", cancel: "Cancel",
  watched: "The school office can review conversations for safety. Messages are text only and cannot be edited after sending.", you: "You", sendFail: "The message was not sent. Try again.",
  calendar: "Calendar", comingUp: "Coming up at school", today: "Today", tomorrow: "Tomorrow", inDays: "in {n} days", noTerm: "We are between terms or on holiday right now.", calKind: { holiday: "Holiday", exam: "Exams and revision", event: "Event" },
  calNote: "This is the school calendar. Dates can change, and the school announces any change in Announcements.", newWord: "New",
  forWho: "To", textOnly: "Text only", chars: "chars",
};
state.dict.ar = ar; state.dict.en = en;
