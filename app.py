"""Einstiegspunkt für die gepackte App (PyInstaller).

PyInstaller kommt mit einem Top-Level-Skript besser zurecht als mit
``python -m src.gui``. Für die Entwicklung funktioniert weiterhin beides:

    python app.py
    python -m src.gui
"""

from src.gui import main

if __name__ == "__main__":
    main()
