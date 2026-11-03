# DLIS Teacher Assistant

A desktop app (Windows and Mac) for the teachers of Dar Luqman Al-Hakim International School: timetable and calendar, the fixed DLIS Word files (lesson plan, quiz, revision sheet, grading sheet, trimester plan, cover sheet), an Excel table for the LMS, PowerPoint lesson slides, tasks and weekly follow-up, reminders, a lesson log, a school map, and an AI chat that never receives student names. Arabic (right to left) and English.

* Teachers: install `DLIS_Teacher_Assistant_Setup.exe` (Windows) or the `.dmg` (Mac). The guide is inside the app (Help).
* Developers: see [`docs/DEVELOPER.md`](docs/DEVELOPER.md). Arabic notes for building the installers: [`README_AR.md`](README_AR.md).

```
pip install -r requirements.txt
python run.py
python -m unittest discover -s tests
```
