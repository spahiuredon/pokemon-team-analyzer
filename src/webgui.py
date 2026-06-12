"""Startet das Web-GUI in einem nativen Desktop-Fenster (pywebview).

Das Frontend liegt in ``web/index.html`` (HTML/CSS/JS), das Backend ist
``src.webgui_api.Api`` - pywebview verdrahtet beides: JavaScript ruft
``window.pywebview.api.<methode>()`` auf und bekommt Promises zurück.

Aufruf:
    python -m src.webgui     (oder: python app.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import webview

from .webgui_api import Api


def _frontend_path() -> Path:
    """Pfad zu web/index.html - im Bundle und in der Entwicklung."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "web" / "index.html"


class DesktopApi(Api):
    """Erweitert die Basis-API um native Datei-Dialoge (brauchen pywebview)."""

    def pick_file(self) -> dict:
        window = webview.windows[0]
        result = window.create_file_dialog(webview.OPEN_DIALOG)
        if not result:
            return {"ok": False}
        return {"ok": True, "path": result[0]}

    def pick_folder(self) -> dict:
        window = webview.windows[0]
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return {"ok": False}
        return {"ok": True, "path": result[0]}


def start() -> None:
    """Öffnet das Hauptfenster und startet die Event-Loop."""
    api = DesktopApi()
    webview.create_window(
        "Pokemon Team-Analyzer",
        url=str(_frontend_path()),
        js_api=api,
        width=1280,
        height=820,
        min_size=(980, 640),
    )
    webview.start()


if __name__ == "__main__":
    start()
