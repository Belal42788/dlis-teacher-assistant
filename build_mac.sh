#!/bin/bash
# Builds dist/DLIS_Teacher_Assistant.app and a .dmg to give to teachers (run start_mac.command once first so .venv exists)
cd "$(dirname "$0")"
.venv/bin/pip install --quiet pyinstaller
.venv/bin/pyinstaller --noconfirm --clean --windowed --icon resources/icon.icns --name DLIS_Teacher_Assistant \
  --add-data "app/web:app/web" --add-data "resources:resources" --collect-data docx --collect-data certifi --collect-all pypdfium2 --hidden-import webview run.py
rm -f dist/DLIS_Teacher_Assistant.dmg
hdiutil create -volname "DLIS Teacher Assistant" -srcfolder dist/DLIS_Teacher_Assistant.app -ov -format UDZO dist/DLIS_Teacher_Assistant.dmg
echo "Done: dist/DLIS_Teacher_Assistant.dmg"
