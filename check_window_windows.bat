@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Checking why the app opens in the browser ...
if not exist ".venv\Scripts\python.exe" ( echo Run start_windows.bat once first. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip install --upgrade pywebview pythonnet
echo.
".venv\Scripts\python.exe" -c "import sys; print(sys.version); import webview; print('pywebview', webview.__version__ if hasattr(webview,'__version__') else 'ok'); import clr; print('pythonnet ok')"
echo.
echo If you see an error above, copy it and send it to Claude. Otherwise run start_windows.bat again.
pause
