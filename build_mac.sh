#!/usr/bin/env bash
# Baut die macOS-App (dist/Pokemon Team-Analyzer.app).
# Voraussetzung: python3 mit tkinter (python.org-Installer empfohlen).
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv venv-build 2>/dev/null || true
source venv-build/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller

pyinstaller --noconfirm pokemon_team_analyzer.spec

echo
echo "Fertig: dist/Pokemon Team-Analyzer.app"
echo "Einfach in den Programme-Ordner ziehen."
