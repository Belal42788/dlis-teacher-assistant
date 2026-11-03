@echo off
chcp 65001 >nul
rem Makes a desktop shortcut with the school logo. Pin THIS shortcut to the taskbar (not the running window), so the taskbar shows our logo and not Python's.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run start_windows.bat once first, then run this file again.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\DLIS Teacher Assistant.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='run.py'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0resources\icon.ico'; $s.Save()"
echo Done: look for "DLIS Teacher Assistant" on your desktop. Right-click it, then "Pin to taskbar".
pause
