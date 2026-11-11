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
| `app/server` | `Service` is built from one mixin per feature (list below). `http.py` is a small router: a list of `(method, regex, handler)`. |
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

## What is where (generated: `python scripts/make_dev_docs.py`)
Feature files (each is a mixin of `Service`):

<!-- AUTO:features -->
| Mixin | File | Lines |
|---|---|---|
| `BankMixin` | `app/server/bank_service.py` | 156 |
| `HealthMixin` | `app/server/health_service.py` | 61 |
| `SeatingMixin` | `app/server/seating_service.py` | 56 |
| `BehaviorMixin` | `app/server/behavior_service.py` | 89 |
| `UpdateMixin` | `app/server/update_service.py` | 111 |
| `InsightsMixin` | `app/server/grades_service.py` | 264 |
| `GradesMixin` | `app/server/grades_service.py` | 264 |
| `ToolsMixin` | `app/server/tools_service.py` | 65 |
| `SchemeMixin` | `app/server/scheme_service.py` | 150 |
| `LibraryMixin` | `app/server/library_service.py` | 230 |
| `ParentWeekMixin` | `app/server/parent_week_service.py` | 73 |
| `CoverageMixin` | `app/server/coverage_service.py` | 117 |
| `CloudMixin` | `app/server/cloud_service.py` | 420 |
| `DocsMixin` | `app/server/docs_service.py` | 418 |
| `AiMixin` | `app/server/ai_service.py` | 374 |
| `AiChatMixin` | `app/server/ai_chat_service.py` | 101 |
| `ChatsMixin` | `app/server/chats_service.py` | 62 |
| `AlarmsMixin` | `app/server/alarms_service.py` | 74 |
| `ChangesMixin` | `app/server/changes_service.py` | 97 |
| `LogMixin` | `app/server/log_service.py` | 86 |
| `SlidesMixin` | `app/server/slides_service.py` | 373 |
| `RevisionMixin` | `app/server/revision_service.py` | 104 |
| `MapMixin` | `app/server/map_service.py` | 97 |
| `SourceMixin` | `app/server/source_service.py` | 499 |
| `WeekMixin` | `app/server/week_service.py` | 62 |
| `WeeklyMixin` | `app/server/weekly_service.py` | 70 |
<!-- /AUTO:features -->

Pages:

<!-- AUTO:pages -->
Menu pages: `today`, `timetable`, `calendar`, `tasks`, `scheme`, `docs`, `library`, `chat`, `classes`, `announcements`, `followup`, `map`, `settings`, `help`.

Tabs inside a menu page: `reminders` (tab of `tasks`), `tools` (tab of `docs`), `publish` (tab of `library`), `bank` (tab of `library`), `log` (tab of `classes`), `progress` (tab of `classes`), `grades` (tab of `classes`), `behavior` (tab of `classes`), `seating` (tab of `classes`), `insights` (tab of `classes`), `parentweek` (tab of `announcements`).
<!-- /AUTO:pages -->

Files in the teacher's data folder: <!-- AUTO:datafiles -->
`ai_prompts.json`, `behavior.json`, `calendar.json`, `chats.json`, `cloud.json`, `cloud_students.json`, `config.json`, `data_version.json`, `grades.json`, `lesson_log.json`, `library.json`, `map.json`, `parent_week.json`, `plans.json`, `question_bank.json`, `reminders.json`, `schedule.json`, `seating.json`, `sources.json`, `structure.json`, `tasks.json`, `weekly.json` (plus `data_version.json`, written by the store).
<!-- /AUTO:datafiles -->

## Keeping the code healthy
Run all of this before every delivery (GitHub "Check" runs the same):
```
ruff check app scripts tests          # unused or missing names, errors hidden by "raise", "any error" in tests
python -m unittest discover -s tests  # includes tests/test_hygiene.py (layers, import circles, dead functions, JS parses, dead CSS)
bash scripts/check_i18n.sh            # every text exists in English and Arabic
python scripts/css_dedupe.py --fix    # removes CSS declarations that a later identical rule always overrides
python scripts/make_dev_docs.py       # refreshes the generated parts of this file
python scripts/stress.py              # a school year of data, many requests at once
python scripts/e2e.py                 # the whole app in a browser
python scripts/ui_snapshot.py a.json  # before/after a big change: proves nothing moved on screen (then: --compare a.json b.json)
```
Rules the tests enforce: `app/core` never imports `app/server` or the launcher; no two modules import each other at the top of the file (an import inside a function is the way out of a circle); every function in `app/` is called somewhere (names called from outside Python go in `ALLOWED` in `tests/test_hygiene.py`); every JavaScript file parses; no CSS rule is written twice for the same property.

Habits that keep it simple: one feature = one `*_service.py` + one page + its keys in both languages + a test; a new data file goes through `Store.read_json/write_json`; when the shape of a data file changes, raise `DATA_VERSION` in `core/store.py` and add the step to `MIGRATIONS`; when you replace something, delete the old one in the same change.

## Adding things
* **A page:** `js/pages/x.js` with `export async function renderX(root)`, an entry in `PAGES` in `js/main.js`, keys in `i18n.js` (both languages), a route in `http.py`, a Service method, a test.
* **A provider:** one entry in `ai_providers.json`.
* **A language:** add a dictionary in `i18n.js` and set `dir` in `setLang`.
* **Version:** `app/core/paths.py`, `installer/dlis.iss` and a new entry in `resources/whats_new.json` (`{"1.0.1": {"ar": [...], "en": [...]}}`, the "What is new" window teachers see once after updating). `python scripts/check_release.py v1.0.1` says what is still missing; tests enforce the same.

## Changing how the data is stored
Raise `DATA_VERSION` in `core/store.py` and add `MIGRATIONS[old] = step`. BEFORE you change the shape, run `python scripts/make_golden_fixture.py` so the old shape is frozen in `tests/fixtures/data_vN`; the tests then upgrade that folder, check the copy made before the upgrade, and fail if a field the old data had is no longer known. Restore of a backup lives in `core/restore.py` (and "App health" in Settings).

## Building for a school
Edit `resources/school_server.json` (and `portal/config.js`) for the school, then `python scripts/school_check.py`. It refuses a secret Supabase key (service_role / sb_secret_) anywhere that ships, a url/key mismatch, and bad addresses. The Build and Release workflows run it first, so a wrong file never becomes an installer.

## Making a release (one click)
1. Change the three things above, upload to GitHub, wait for the green Check.
2. GitHub, "Releases", "Draft a new release", new tag `v1.0.1` (same number), write a few plain lines in the description, "Publish release".
3. The **Release** workflow checks the numbers (`scripts/check_release.py`), builds Windows and Mac (`build.yml`, called as a reusable workflow), attaches both installers to the release, writes `portal/latest.json` (`scripts/write_latest.py`) and starts the Pages deploy, so every installed app shows "a newer version is ready" within a day.
4. If the robot cannot push (a protected main branch), allow "GitHub Actions" to bypass it, or edit `portal/latest.json` by hand.

Other robots: **Dependabot** (`.github/dependabot.yml`) opens a weekly pull request for newer libraries and workflow tools; **Security check** (`security.yml`, every Monday) runs `pip-audit` on `requirements.txt`; **Check** also runs `actionlint` so a mistake in a workflow file is caught before it is ever used.

## Rules we keep
* Simple for teachers who are not technical; Arabic (right to left) and English; 12-hour times.
* Student names are never sent to an AI service.
* Fixed DLIS Word templates; the app only fills them.

## HTTP routes
The server listens on 127.0.0.1 only and every request carries the secret token (`X-DLIS-Token`, set when the page is served). Errors come back with the status of the `AppError` (see `core/errors.py`); the front end shows a translated message when `err_<code>` exists.

<!-- AUTO:routes -->
| Method | Route | Service method |
|---|---|---|
| GET | `/api/ping` |  |
| GET | `/api/bootstrap` | `bootstrap` |
| PUT | `/api/prefs` | `set_language` |
| POST | `/api/data-folder` | `set_data_folder` |
| GET | `/api/reminders` | `get_reminders` |
| GET | `/api/sources` | `list_sources` |
| POST | `/api/sources/import` | `import_source` |
| POST | `/api/sources/url` | `import_url` |
| GET | `/api/sources/([0-9a-f]{10})` | `get_source` |
| POST | `/api/sources/([0-9a-f]{10})/read` | `read_source` |
| POST | `/api/sources/([0-9a-f]{10})/digest` | `digest_source` |
| POST | `/api/sources/([0-9a-f]{10})/delete` | `delete_source` |
| GET | `/api/weekly` | `get_weekly` |
| PUT | `/api/weekly` | `set_weekly` |
| POST | `/api/usage` | `record_usage` |
| POST | `/api/feedback` | `add_feedback` |
| POST | `/api/feedback/export` | `export_feedback` |
| GET | `/api/parent-week` | `get_parent_week` |
| PUT | `/api/parent-week` | `save_parent_week` |
| POST | `/api/parent-week/publish` | `save_parent_week` |
| POST | `/api/parent-week/unpublish` | `save_parent_week` |
| GET | `/api/docs/revision-cover` | `revision_cover_suggest` |
| POST | `/api/docs/revision-cover` | `make_revision_cover` |
| GET | `/api/tomorrow` | `tomorrow_prep` |
| GET | `/api/insights` | `insights_get` |
| GET | `/api/grades` | `grades_get` |
| PUT | `/api/grades` | `grades_put` |
| POST | `/api/grades/import` | `grades_import` |
| POST | `/api/grades/upload` | `grades_upload` |
| GET | `/api/week-prep` | `week_prep_status` |
| GET | `/api/tools` | `tools_catalog` |
| POST | `/api/tools/run` | `tools_run` |
| POST | `/api/tools/word` | `tools_word` |
| GET | `/api/scheme` | `scheme_get` |
| PUT | `/api/scheme` | `scheme_put` |
| GET | `/api/library` | `library_list` |
| POST | `/api/library/share` | `library_share` |
| POST | `/api/library/place` | `library_place` |
| POST | `/api/library/place/add` | `library_place_add` |
| POST | `/api/library/place/delete` | `library_place_delete` |
| POST | `/api/library/source` | `library_source` |
| POST | `/api/library/public` | `library_set_public` |
| POST | `/api/library/unshare` | `library_unshare` |
| GET | `/api/coverage` | `coverage` |
| POST | `/api/inspection-pack` | `inspection_pack` |
| POST | `/api/status/push` | `push_status` |
| GET | `/api/status/staff` | `staff_status` |
| GET | `/api/cloud` | `get_cloud` |
| PUT | `/api/cloud` | `put_cloud` |
| POST | `/api/cloud/code` | `cloud_code_make` |
| POST | `/api/cloud/join` | `cloud_join` |
| POST | `/api/cloud/forget` | `cloud_forget_school` |
| POST | `/api/cloud/login` | `cloud_login` |
| POST | `/api/cloud/logout` | `cloud_logout` |
| GET | `/api/announcements` | `list_announcements` |
| POST | `/api/announcements` | `post_announcement` |
| POST | `/api/announcements/([0-9a-f-]{36})/update` | `update_announcement` |
| POST | `/api/announcements/([0-9a-f-]{36})/delete` | `delete_announcement` |
| GET | `/api/publications` | `list_publications` |
| POST | `/api/publications` | `add_publication` |
| POST | `/api/publications/([0-9a-f-]{36})` | `set_publication` |
| POST | `/api/publications/([0-9a-f-]{36})/delete` | `delete_publication` |
| GET | `/api/codes` | `codes_status` |
| POST | `/api/codes/prepare` | `prepare_codes` |
| POST | `/api/cloud/backup` | `cloud_backup` |
| POST | `/api/cloud/test` | `cloud_test` |
| GET | `/api/map` | `get_map` |
| PUT | `/api/map` | `put_map` |
| PUT | `/api/reminders` | `put_reminders` |
| GET | `/api/background` | `get_background` |
| PUT | `/api/background` | `put_background` |
| GET | `/api/alarms` | `list_alarms` |
| POST | `/api/alarms` | `add_alarm` |
| POST | `/api/alarms/([a-z0-9_-]+)/update` | `update_alarm` |
| POST | `/api/alarms/([a-z0-9_-]+)/delete` | `delete_alarm` |
| GET | `/api/school-calendar` | `school_calendar` |
| POST | `/api/fs/native` | `pick_folder_native` |
| GET | `/api/fs/list` | `fs_list` |
| POST | `/api/fs/mkdir` | `fs_mkdir` |
| GET | `/api/settings` | `get_settings` |
| PUT | `/api/settings` | `put_settings` |
| POST | `/api/setup/finish` | `finish_setup` |
| GET | `/api/structure` | `get_structure` |
| PUT | `/api/structure` | `put_structure` |
| POST | `/api/structure/build` | `build_structure` |
| GET | `/api/rooms/([a-z0-9_-]+)/students` | `get_students` |
| PUT | `/api/rooms/([a-z0-9_-]+)/students` | `put_students` |
| POST | `/api/students/parse` | `parse_students` |
| GET | `/api/timetable` | `get_timetable` |
| PUT | `/api/timetable` | `put_timetable` |
| GET | `/api/calendar` | `get_calendar` |
| PUT | `/api/calendar` | `put_calendar` |
| POST | `/api/today/change` | `change_today` |
| GET | `/api/log/last` | `log_last` |
| GET | `/api/log` | `log_list` |
| POST | `/api/log` | `log_save` |
| POST | `/api/log/([a-z0-9_-]+)/delete` | `log_delete` |
| GET | `/api/overview` | `overview` |
| GET | `/api/today` | `today` |
| POST | `/api/import/legacy` | `import_old` |
| POST | `/api/backup` | `backup` |
| GET | `/api/docs/context` | `docs_context` |
| POST | `/api/docs/lesson-plan` | `make_lesson_plan` |
| POST | `/api/docs/trimester-plan` | `make_trimester_plan` |
| POST | `/api/docs/quiz` | `make_quiz` |
| POST | `/api/docs/quiz-export` | `export_quiz` |
| POST | `/api/docs/revision` | `make_revision` |
| POST | `/api/docs/cover-sheet` | `make_cover_sheet` |
| POST | `/api/docs/certificates` | `make_certificates` |
| POST | `/api/docs/grading-sheet` | `make_grading_sheet` |
| POST | `/api/open` | `open_file` |
| GET | `/api/ai` | `ai_state` |
| POST | `/api/ai/save` | `ai_save` |
| POST | `/api/ai/off` | `ai_off` |
| POST | `/api/ai/test` | `ai_test` |
| POST | `/api/ai/models` | `ai_models` |
| GET | `/api/ai/prompts` | `ai_prompts_get` |
| PUT | `/api/ai/prompts` | `ai_prompts_put` |
| POST | `/api/ai/chat` | `ai_chat` |
| GET | `/api/chats` | `chats_list` |
| POST | `/api/chats` | `chat_save` |
| GET | `/api/chats/([a-z0-9]+)` | `chat_get` |
| PUT | `/api/chats/([a-z0-9]+)` | `chat_save` |
| POST | `/api/chats/([a-z0-9]+)/delete` | `chat_delete` |
| GET | `/api/slides/topics` | `slide_topics` |
| POST | `/api/slides/notebooklm` | `notebooklm_prompt` |
| GET | `/api/slides/image-config` | `image_state` |
| PUT | `/api/slides/image-config` | `image_save` |
| POST | `/api/slides/image-test` | `image_test` |
| POST | `/api/slides/image` | `slide_image` |
| POST | `/api/slides/plan` | `slide_plan` |
| POST | `/api/slides/build` | `slide_build` |
| POST | `/api/slides/source` | `notebooklm_source` |
| POST | `/api/ai/lesson` | `ai_generate_lesson` |
| POST | `/api/ai/quiz` | `ai_generate_quiz` |
| POST | `/api/ai/revision` | `ai_generate_revision` |
| POST | `/api/ai/trimester` | `ai_generate_trimester` |
| GET | `/api/behavior` | `behavior_list` |
| POST | `/api/behavior` | `behavior_save` |
| POST | `/api/behavior/([a-z0-9_-]+)/done` | `behavior_done` |
| POST | `/api/behavior/([a-z0-9_-]+)/delete` | `behavior_delete` |
| GET | `/api/seating` | `seating_get` |
| PUT | `/api/seating` | `seating_save` |
| GET | `/api/update` | `check_update` |
| POST | `/api/update/dismiss` | `dismiss_update` |
| GET | `/api/bank` | `bank_list` |
| POST | `/api/bank` | `bank_add` |
| POST | `/api/bank/pick` | `bank_pick` |
| PUT | `/api/bank/([a-z0-9]+)` | `bank_update` |
| POST | `/api/bank/([a-z0-9]+)/delete` | `bank_delete` |
| GET | `/api/health` | `health` |
| POST | `/api/health/restore` | `backup_restore` |
| GET | `/api/whats-new` | `whats_new` |
| POST | `/api/whats-new/seen` | `mark_whats_new_seen` |
| POST | `/api/update/setting` | `set_update_check` |
| POST | `/api/open-url` | `open_url` |
| GET | `/api/tasks` | `list_tasks` |
| POST | `/api/tasks` | `add_task` |
| POST | `/api/tasks/([a-z0-9_:-]+)/update` | `update_task` |
| POST | `/api/tasks/([a-z0-9_:-]+)/delete` | `delete_task` |
| POST | `/api/tasks/dismiss` | `dismiss_task` |
<!-- /AUTO:routes -->

## Next
Phase 12: a server or Drive link; then the Android app (everything the desktop app has; online storage on a free service such as Firebase or Supabase).
