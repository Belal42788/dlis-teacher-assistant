@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting the app with messages visible ...
".venv\Scripts\python.exe" -X utf8 -c "import traceback, webview, sys; sys.argv=['run.py']; import runpy; runpy.run_path('run.py', run_name='__main__')"
echo.
echo ---- error.log ----
if exist "%APPDATA%\DLIS Teacher Assistant\error.log" type "%APPDATA%\DLIS Teacher Assistant\error.log"
if exist "%LOCALAPPDATA%\DLIS Teacher Assistant\error.log" type "%LOCALAPPDATA%\DLIS Teacher Assistant\error.log"
pause
