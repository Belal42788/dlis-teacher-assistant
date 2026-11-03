"""The teacher's extra AI tools (ready-made forms, like MagicSchool's). Each tool: a form, and one instruction the AI follows.
Names and labels are written in English and Arabic; the instruction is always English; the answer language is chosen in the form."""
from __future__ import annotations

GROUPS = [("plan", "Planning", "تخطيط"), ("assess", "Assessment and assignments", "تقييم وواجبات"),
          ("text", "Working with text", "العمل مع النصوص"), ("talk", "Feedback and messages", "ملاحظات ورسائل")]


def F(key, en, ar, kind="text", ph="", options=None, rows=3, required=True, default=""):
    return {"key": key, "label": {"en": en, "ar": ar}, "type": kind, "placeholder": ph, "options": options or [], "rows": rows, "required": required, "default": default}


TOPIC = F("topic", "Topic", "الموضوع", ph="Input and output devices")
TEXT = F("text", "The text", "النص", "textarea", rows=8)


def T(id, group, en, ar, den, dar, fields, instruction, student=False):
    return {"id": id, "group": group, "name": {"en": en, "ar": ar}, "desc": {"en": den, "ar": dar}, "fields": fields, "instruction": instruction, "student": student}


TOOLS = [
    # ---- planning
    T("unit_plan", "plan", "Unit plan", "خطة وحدة", "A plan for several weeks on one unit.", "خطة لعدة أسابيع لوحدة واحدة.",
      [TOPIC, F("weeks", "Number of weeks", "عدد الأسابيع", "number", default="4")],
      "Write a unit plan on the topic for the given number of weeks. Give: unit overview, big ideas, learning objectives, a week-by-week table (week | lessons | key activities | assessment), key vocabulary, resources, differentiation, and the final assessment. Use '|' separated rows for the table."),
    T("pbl", "plan", "Project-based learning plan", "خطة مشروع", "A project students work on over several lessons.", "مشروع يشتغل عليه الطلبة على عدة حصص.",
      [TOPIC, F("duration", "How long", "المدة", ph="2 weeks", default="2 weeks"), F("product", "What students make (optional)", "إيه اللي الطلبة هيعملوه (اختياري)", required=False)],
      "Design a project-based learning plan: driving question, final product, steps by lesson, roles for group work, checkpoints, a short rubric table (criteria | excellent | good | needs work), and reflection questions."),
    T("make_relevant", "plan", "Make it relevant", "اربطه بحياتهم", "Ideas that connect the lesson to students' real life.", "أفكار تربط الدرس بحياة الطلبة.",
      [TOPIC, F("interests", "What the students like (optional)", "إيه اللي الطلبة بيحبوه (اختياري)", required=False, ph="football, games, YouTube")],
      "Give 8 ideas that connect the topic to the real life and interests of students of this age (examples, hooks, mini-activities). Each idea: one title line and 1-2 sentences."),
    T("misconceptions", "plan", "Common misconceptions", "الأخطاء الشائعة", "What students often get wrong, and how to fix it.", "اللي الطلبة بيغلطوا فيه وإزاي تصلحه.",
      [TOPIC],
      "List the 6 most common misconceptions or mistakes students of this age have about the topic. For each: what they think, why it is wrong, and a quick way to fix it in class."),
    T("explain_multi", "plan", "Explain it 4 ways", "اشرحها بـ 4 طرق", "Different ways to explain a hard idea.", "طرق مختلفة لشرح فكرة صعبة.",
      [F("topic", "The hard idea", "الفكرة الصعبة", ph="What is a variable?")],
      "Explain the idea in 4 different ways for students of this age: (1) a simple everyday analogy, (2) step by step, (3) a picture or demonstration the teacher can draw or show, (4) a short story or role play. Add one check-for-understanding question at the end."),
    T("vocab_list", "plan", "Vocabulary list", "قايمة مفردات", "Key words with simple meanings.", "كلمات مهمة بمعانيها البسيطة.",
      [TOPIC, F("count", "How many words", "عدد الكلمات", "number", default="10")],
      "Make a vocabulary list for the topic. For each word: the word, a simple meaning suitable for this age, an example sentence, and the Arabic meaning. Format each as: word | meaning | example | Arabic."),
    # ---- assessment
    T("rubric", "assess", "Rubric", "Rubric (معايير تقييم)", "A scoring table for an assignment.", "جدول تقييم لواجب أو مشروع.",
      [F("task", "The assignment", "الواجب", "textarea", ph="Make a poster about e-safety", rows=3), F("levels", "Levels", "المستويات", "select", options=["3", "4", "5"], default="4"), F("criteria", "Criteria", "عدد المعايير", "number", default="4")],
      "Write a rubric for the assignment. Output ONE table with rows separated by new lines and cells by '|': first row = Criteria | then one column per level (highest first) with points; then one row per criterion with a clear description for every level. Add a total score line under the table."),
    T("exemplar", "assess", "Strong and weak examples", "إجابة نموذجية وإجابة ضعيفة", "Examples of a strong and a weak answer, with comments.", "مثال لإجابة قوية وإجابة ضعيفة مع تعليق.",
      [F("task", "The question or task", "السؤال أو المهمة", "textarea", rows=3)],
      "Write one strong (exemplar) answer and one weak answer to the task, as a student of this age would write them. After each, add 2-3 bullet comments explaining what makes it strong or weak."),
    T("dok", "assess", "Questions by depth (DOK)", "أسئلة بمستويات العمق", "Questions from easy recall to deeper thinking.", "أسئلة من التذكر لحد التفكير العميق.",
      [TOPIC, F("count", "Questions per level", "أسئلة لكل مستوى", "number", default="3")],
      "Write questions on the topic at Depth of Knowledge levels 1 (recall), 2 (skill/concept), 3 (strategic thinking) and 4 (extended thinking). Use the given number per level for levels 1-3 and one for level 4. Label each level."),
    T("text_questions", "assess", "Questions from a text", "أسئلة من نص", "Reading questions that need the text to answer.", "أسئلة قراءة إجابتها في النص.",
      [TEXT, F("kind", "Kind", "النوع", "select", options=["Multiple choice with answer key", "Short answer with answer key", "Mixed"], default="Mixed"), F("count", "How many questions", "عدد الأسئلة", "number", default="6")],
      "Write questions that can only be answered by reading the text (no outside knowledge). Follow the kind and number requested. Add an answer key at the end that quotes the part of the text that proves each answer."),
    T("diagnostic", "assess", "Diagnostic test", "اختبار تشخيصي", "A short test of what students already know.", "اختبار قصير لمعرفة اللي الطلبة عارفينه.",
      [TOPIC, F("count", "Questions", "عدد الأسئلة", "number", default="8")],
      "Write a diagnostic (pre-assessment) of the given number of questions on the topic, from easy to hard, mixing multiple choice and short answers. Add an answer key and a short note: which results mean the class needs a re-teach."),
    T("exit_ticket", "assess", "Warm-up and exit ticket", "سؤال بداية وسؤال نهاية", "A 3-minute starter and a closing check.", "سؤال بداية الحصة وسؤال في آخرها.",
      [TOPIC],
      "Write: a 3-minute warm-up (bell ringer) that reviews the previous idea, and an exit ticket of 3 quick questions that check today's lesson on the topic. Add what a good answer looks like."),
    T("multistep", "assess", "Multi-step assignment", "واجب متعدد الخطوات", "A full worksheet: warm-up, words, questions, challenge.", "ورقة عمل كاملة بتدريجها.",
      [TOPIC, F("minutes", "Time (minutes)", "الوقت (دقيقة)", "number", default="30")],
      "Create a student-ready assignment that fits the time: a title, short directions, a warm-up, key vocabulary, 6-8 graded questions or tasks (easy to hard), and a challenge task. Then an answer key for the teacher."),
    T("scaffold", "assess", "Break an assignment into steps", "قسّم الواجب لخطوات", "Turns a big task into small supported steps.", "بيحوّل مهمة كبيرة لخطوات صغيرة.",
      [F("task", "Paste the assignment", "الصق الواجب", "textarea", rows=6)],
      "Break the assignment into small numbered steps a student can follow, with a tip or sentence starter for each step and a checklist at the end. Keep the original goals."),
    T("choice_board", "assess", "Choice board", "لوحة اختيارات", "9 activities students can choose from.", "9 أنشطة الطالب يختار منها.",
      [TOPIC],
      "Create a 3x3 choice board on the topic. Mix ways of showing learning (write, draw, build, speak, digital). Give each cell a title and one sentence. Output as three lines of three cells separated by '|'. Add a note on how to grade it fairly."),
    T("ai_resistant", "assess", "Make it harder to cheat with AI", "واجب صعب على الغش بالذكاء الاصطناعي", "Changes an assignment so AI cannot just answer it.", "تعديل الواجب علشان الذكاء الاصطناعي ما يحلوش.",
      [F("task", "Paste the assignment", "الصق الواجب", "textarea", rows=5)],
      "Suggest 6 ways to change this assignment so that students must show their own thinking and cannot just copy an AI answer (in-class steps, personal examples, process evidence, oral explanation, etc.). Then rewrite the assignment using the best two ideas."),
    # ---- text
    T("leveler", "text", "Make a text easier or harder", "عدّل مستوى النص", "The same text for a different reading level.", "نفس النص بمستوى قراءة مختلف.",
      [TEXT, F("level", "Level", "المستوى", "select", options=["Much simpler (support for weak readers / English learners)", "A bit simpler", "A bit harder (challenge)", "Much harder (advanced readers)"], default="A bit simpler")],
      "Rewrite the text at the requested reading level. Keep all key facts and the order of ideas. Do not add new facts. After it, list the 5 key words and their meanings."),
    T("summarizer", "text", "Summary", "ملخص", "A shorter version of a text.", "نسخة أقصر من النص.",
      [TEXT, F("length", "Length", "الطول", "select", options=["3 sentences", "One paragraph", "5 bullet points", "A third of the length"], default="One paragraph")],
      "Summarise the text in the requested length. Use only what is in the text."),
    T("rewriter", "text", "Rewrite for a purpose", "أعد الكتابة لغرض", "Changes the style of a text.", "بيغيّر أسلوب النص.",
      [TEXT, F("purpose", "Rewrite it as", "اكتبه ك", "select", options=["A short dialogue", "A story", "Instructions step by step", "A formal letter", "A friendly message to parents", "A quiz introduction"], default="A story")],
      "Rewrite the text for the requested purpose. Keep the facts."),
    T("translator", "text", "Translate", "ترجمة", "English to Arabic or Arabic to English.", "إنجليزي لعربي أو عربي لإنجليزي.",
      [TEXT, F("direction", "Direction", "الاتجاه", "select", options=["English to Arabic", "Arabic to English"], default="English to Arabic")],
      "Translate the text in the requested direction. Keep the meaning, the layout and the tone. Output only the translation."),
    T("proofreader", "text", "Proofread", "تصحيح لغوي", "Fixes spelling and grammar, and lists what changed.", "بيصحح الإملاء والقواعد ويقولك إيه اللي اتغيّر.",
      [TEXT],
      "Correct spelling, grammar and punctuation. First give the corrected text. Then a short list of the changes made and why."),
    T("clear_directions", "text", "Clearer directions", "تعليمات أوضح", "Makes instructions easy to follow.", "بيخلّي التعليمات سهلة المتابعة.",
      [F("text", "Paste the directions", "الصق التعليمات", "textarea", rows=5)],
      "Rewrite the directions as short numbered steps with simple words. Put the most important action first in each step. Add one example of a finished answer if useful."),
    # ---- feedback and messages
    T("work_feedback", "talk", "Feedback on student work", "ملاحظات على شغل طالب", "Praise, what to improve and the next step.", "إيجابيات وإيه اللي يتحسّن والخطوة الجاية.",
      [F("work", "The student's work", "شغل الطالب", "textarea", rows=7), F("criteria", "What it is judged on (optional)", "بيتقيّم على إيه (اختياري)", "textarea", rows=2, required=False)],
      "Write feedback for the student: one specific thing done well (quote it), two things to improve with how to improve each, and one clear next step. Speak to the student kindly in the second person. Use [student] for the name if you need it.", True),
    T("report_comment", "talk", "Report card comment", "تعليق الشهادة", "A short, kind comment for a report card.", "تعليق قصير ولطيف للشهادة.",
      [F("strengths", "Strengths", "نقط القوة", "textarea", rows=2), F("improve", "To improve", "محتاج يحسّن", "textarea", rows=2, required=False), F("tone", "Tone", "الأسلوب", "select", options=["Warm and encouraging", "Balanced", "Firm but supportive"], default="Balanced"), F("words", "Length (words)", "الطول (كلمة)", "number", default="50")],
      "Write a report card comment of about the given number of words, in the third person, positive first, with one clear next step. Use [student] wherever the name goes. Never invent facts that were not given.", True),
    T("newsletter", "talk", "Class newsletter", "نشرة الفصل", "A short newsletter for families.", "نشرة قصيرة لأولياء الأمور.",
      [F("learned", "What we learned", "اتعلمنا إيه", "textarea", rows=3), F("coming", "Coming up (dates, quizzes, trips)", "الجاي (مواعيد وكويزات ورحلات)", "textarea", rows=3, required=False), F("ask", "What parents can do at home (optional)", "ولي الأمر يعمل إيه في البيت (اختياري)", "textarea", rows=2, required=False)],
      "Write a friendly one-page class newsletter for families: a short greeting, what the class learned, what is coming up, how parents can help at home, and a closing line. Do not mention any student by name."),
    T("email_reply", "talk", "Reply to an email", "رد على إيميل", "Writes a polite reply to a message.", "بيكتب رد مهذب على رسالة.",
      [F("email", "The message you received", "الرسالة اللي وصلتلك", "textarea", rows=6), F("intent", "What you want to say", "عاوز تقول إيه", "textarea", rows=2)],
      "Write a polite, clear and short reply from the teacher. Answer every question in the message, include what the teacher wants to say, and end with a courteous closing. Use [student] if a student is mentioned."),
    T("syllabus", "talk", "Course syllabus", "منهج المادة (Syllabus)", "A course overview for the term or year.", "نظرة عامة على المادة للفصل أو السنة.",
      [F("course", "Course and grade", "المادة والصف", ph="ICT, Grade 7"), F("length", "Length", "المدة", ph="Trimester 1", default="Trimester 1"), F("topics", "Main topics (optional)", "الموضوعات الأساسية (اختياري)", "textarea", rows=3, required=False)],
      "Write a course syllabus: course description, learning goals, topics by week or month (table: period | topic | assessment), materials, assessment and grading, classroom expectations, and how to contact the teacher."),
]
BY_ID = {t["id"]: t for t in TOOLS}
