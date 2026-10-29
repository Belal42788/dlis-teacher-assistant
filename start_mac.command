#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "First start: installing what the app needs (once, needs internet)..."
  python3 -m venv .venv && .venv/bin/pip install --quiet -r requirements.txt || { echo "Python 3.11+ is required: https://www.python.org/downloads/"; read -n1; exit 1; }
fi
exec .venv/bin/python run.py
