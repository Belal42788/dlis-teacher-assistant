# DLIS Teacher Assistant — developer guide

Version 1.0.0. A local web app shown in a desktop window (pywebview). Python backend, plain JavaScript front end, no build step.

## Run it
```
pip install -r requirements.txt
python run.py                # window; add --no-window to print the URL and use any browser
python -m unittest discover -s tests
bash scripts/check_i18n.sh   # every t("key") exists in English and Arabic
python scripts/e2e.py        # drives the real app with Playwright and a fake AI server; pictures go to /tmp/shots
TOUR=/tmp/tour python scripts/e2e.py   # also saves a picture of every page and tab
```
Windows installer: `build_windows.bat` (needs Python and Inno Setup) or the GitHub workflow in `.github/workflows/build.yml` (Actions → Build apps → Run workflow; downloads a Windows Setup.exe and a Mac dmg).

## Layout
| Folder | What is in it |
|---|---|
| `app/core` | No web code. `paths` (folders, prefs, log), `store` (reads/writes the data folder, backups), `documents` (fills the Word templates, grade table), `pptx_builder`, `ai_client` (OpenAI-compatible and Anthropic adapters, urllib only), `image_client`, `models` (pydantic), `academic` (calendar, weeks), `timetable`, `translit`. |
| `app/server` | `Service` = mixins, one file per feature (`docs`, `ai`, `ai_chat`, `chats`, `alarms`, `changes`, `log`, `slides`, `revision`, `map`, `source`, `week`, `weekly`). `http.py` is a small router: a list of `(method, regex, handler)`. |
| `app/web` | Vanilla ES modules. `js/pages/*` one file per page, `js/components/*` shared pieces, `js/i18n.js` (English and Arabic), `js/help_content.json` (the in-app guide), `css/style.css`. |
| `app/launcher.py` | The window, tray icon, single instance, title bar controls (`WindowControls`), native reminder sound. |
| `resources` | Word templates, logo, bell schedule, official calendar, built-in roster, school map seed, AI provider list and prompts. |
| `tests`, `scripts` | Unit tests; e2e, i18n check, guide builder. |

## Data (the teacher's folder, default `My DLIS`)
`config.json`, `structure.json` (grades, classes), `schedule.json` (timetable and one-day changes), `calendar.json`, `tasks.json`, `reminders.json`, `lesson_log.json`, `plans.json` (lesson and trimester topics, slide counts), `weekly.json`, `map.json` (a copy of `resources/school_map.json` once edited), `sources.json`, `chats.json`, `ai_prompts.json`, `rooms/<class>/students.csv`, `Documents/<grade>/…docx|xlsx|csv`, `Documents/Cover_Sheets`, `Slides/…pptx`, `Exports/…zip`, `_backup/` (older copies of changed json files).

Per computer, outside the folder (`paths.app_support_dir`): `ai.json` (API keys and image-service credentials), `source_pages/` (slide pictures), `slide_images/`, `error.log`. Keys never go in the data folder, so syncing it through Drive does not share them.

All JSON writes go through `Store.write_json` (atomic, with a backup of the old file). Readers pass a `check=` function; a damaged file is replaced by its last good copy.

## AI
* Providers are described in `resources/ai_providers.json` (base URL, key help, default models, `vision_models`/`vision_any`). A "custom" provider takes any OpenAI-compatible URL.
* Every prompt leaves through `AiMixin._ask`, which removes student names (`redact`). The parent-message helper uses a `[student]` placeholder that the browser fills in.
* The wording of each helper (`lesson`, `quiz`, `trimester`, `slides`, `revision`, `chat`) can be edited by the teacher (`ai_prompts.json`); the JSON output format stays in code.
* Pictures in slides are read by `SourceMixin._vision_chat`, which tries the configured model and then the provider's vision models.

## Adding things
* **A page:** `js/pages/x.js` with `export async function renderX(root)`, an entry in `PAGES` in `js/main.js`, keys in `i18n.js` (both languages), a route in `http.py`, a Service method, a test.
* **A provider:** one entry in `ai_providers.json`.
* **A language:** add a dictionary in `i18n.js` and set `dir` in `setLang`.
* **Version:** `app/core/paths.py` and `installer/dlis.iss` (a test checks they match).

## Rules we keep
* Simple for teachers who are not technical; Arabic (right to left) and English; 12-hour times.
* Student names are never sent to an AI service.
* Fixed DLIS Word templates; the app only fills them.

## HTTP routes
The server listens on 127.0.0.1 only and every request carries the secret token (`X-DLIS-Token`, set when the page is served). Errors come back with the status of the `AppError` (see `core/errors.py`); the front end shows a translated message when `err_<code>` exists.

| Method | Route |
|---|---|
| GET | `/api/ping` |
| GET | `/api/bootstrap` |
| PUT | `/api/prefs` |
| POST | `/api/data-folder` |
| GET | `/api/reminders` |
| GET | `/api/sources` |
| POST | `/api/sources/import` |
| GET | `/api/sources/([0-9a-f]{10})` |
| POST | `/api/sources/([0-9a-f]{10})/read` |
| POST | `/api/sources/([0-9a-f]{10})/digest` |
| POST | `/api/sources/([0-9a-f]{10})/delete` |
| GET | `/api/weekly` |
| PUT | `/api/weekly` |
| GET | `/api/map` |
| PUT | `/api/map` |
| PUT | `/api/reminders` |
| GET | `/api/background` |
| PUT | `/api/background` |
| GET | `/api/alarms` |
| POST | `/api/alarms` |
| POST | `/api/alarms/([a-z0-9_-]+)/update` |
| POST | `/api/alarms/([a-z0-9_-]+)/delete` |
| GET | `/api/school-calendar` |
| POST | `/api/fs/native` |
| GET | `/api/fs/list` |
| POST | `/api/fs/mkdir` |
| GET | `/api/settings` |
| PUT | `/api/settings` |
| POST | `/api/setup/finish` |
| GET | `/api/structure` |
| PUT | `/api/structure` |
| POST | `/api/structure/build` |
| GET | `/api/rooms/([a-z0-9_-]+)/students` |
| PUT | `/api/rooms/([a-z0-9_-]+)/students` |
| POST | `/api/students/parse` |
| GET | `/api/timetable` |
| PUT | `/api/timetable` |
| GET | `/api/calendar` |
| PUT | `/api/calendar` |
| POST | `/api/today/change` |
| GET | `/api/log/last` |
| GET | `/api/log` |
| POST | `/api/log` |
| POST | `/api/log/([a-z0-9_-]+)/delete` |
| GET | `/api/overview` |
| GET | `/api/today` |
| POST | `/api/import/legacy` |
| POST | `/api/backup` |
| GET | `/api/docs/context` |
| POST | `/api/docs/lesson-plan` |
| POST | `/api/docs/trimester-plan` |
| POST | `/api/docs/quiz` |
| POST | `/api/docs/revision` |
| POST | `/api/docs/cover-sheet` |
| POST | `/api/docs/grading-sheet` |
| POST | `/api/open` |
| GET | `/api/ai` |
| POST | `/api/ai/save` |
| POST | `/api/ai/off` |
| POST | `/api/ai/test` |
| POST | `/api/ai/models` |
| GET | `/api/ai/prompts` |
| PUT | `/api/ai/prompts` |
| POST | `/api/ai/chat` |
| GET | `/api/chats` |
| POST | `/api/chats` |
| GET | `/api/chats/([a-z0-9]+)` |
| PUT | `/api/chats/([a-z0-9]+)` |
| POST | `/api/chats/([a-z0-9]+)/delete` |
| GET | `/api/slides/topics` |
| POST | `/api/slides/notebooklm` |
| GET | `/api/slides/image-config` |
| PUT | `/api/slides/image-config` |
| POST | `/api/slides/image-test` |
| POST | `/api/slides/image` |
| POST | `/api/slides/plan` |
| POST | `/api/slides/build` |
| POST | `/api/slides/source` |
| POST | `/api/ai/lesson` |
| POST | `/api/ai/quiz` |
| POST | `/api/ai/revision` |
| POST | `/api/ai/trimester` |
| POST | `/api/open-url` |
| GET | `/api/tasks` |
| POST | `/api/tasks` |
| POST | `/api/tasks/([a-z0-9_:-]+)/update` |
| POST | `/api/tasks/([a-z0-9_:-]+)/delete` |
| POST | `/api/tasks/dismiss` |

## Next
Phase 12: a server or Drive link; then the Android app (everything the desktop app has; online storage on a free service such as Firebase or Supabase).
