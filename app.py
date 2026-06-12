"""Einstiegspunkt der App (pywebview-Web-GUI).

    python app.py            startet das moderne Web-GUI
    python -m src.gui        startet das alte Tkinter-GUI (Legacy)
"""

from src.webgui import start

if __name__ == "__main__":
    start()
