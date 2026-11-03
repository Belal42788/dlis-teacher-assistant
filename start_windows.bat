@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First start: installing what the app needs. This happens once and needs internet...
  py -3 -m venv .venv
  if errorlevel 1 goto nopython
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  if errorlevel 1 goto fail
)
start "" ".venv\Scripts\pythonw.exe" run.py
exit /b 0

:nopython
echo.
echo Python 3.11 or newer is required. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this file again.
pause
exit /b 1

:fail
echo.
echo Something failed. Copy the messages above and send them to Claude.
pause
exit /b 1
