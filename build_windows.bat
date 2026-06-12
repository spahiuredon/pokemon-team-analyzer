@echo off
REM Baut die Windows-App (dist\Pokemon Team-Analyzer\Pokemon Team-Analyzer.exe).
REM Voraussetzung: Python 3.10+ von python.org (inkl. tkinter, ist Standard).
cd /d "%~dp0"

if not exist venv-build (
    python -m venv venv-build
)
call venv-build\Scripts\activate.bat
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller

pyinstaller --noconfirm pokemon_team_analyzer.spec

echo.
echo Fertig: dist\Pokemon Team-Analyzer\Pokemon Team-Analyzer.exe
echo Den ganzen Ordner kopieren oder eine Verknuepfung zur .exe anlegen.
pause
