@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building the Windows program ...
if not exist ".venv\Scripts\python.exe" (
  echo Preparing the app files first. This happens once and needs internet...
  py -3 -m venv .venv
  if errorlevel 1 goto nopython
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller
if errorlevel 1 goto fail
rem a folder build (not one big exe): starts faster and has no "temporary directory" warning
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --icon "resources\icon.ico" --name DLIS_Teacher_Assistant --add-data "app\web;app\web" --add-data "resources;resources" --collect-data docx --collect-data certifi --collect-all pypdfium2 --hidden-import webview --hidden-import pystray._win32 run.py
if errorlevel 1 goto fail

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" goto noinno
"%ISCC%" installer\dlis.iss
if errorlevel 1 goto fail
echo.
echo Done. Send this file to the teachers:
echo   installer\Output\DLIS_Teacher_Assistant_Setup.exe
pause
exit /b 0

:noinno
echo.
echo The program was built here: dist\DLIS_Teacher_Assistant\DLIS_Teacher_Assistant.exe
echo To make the one-file installer for teachers, install "Inno Setup" (free) from
echo https://jrsoftware.org/isdl.php  and run this file again.
pause
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
