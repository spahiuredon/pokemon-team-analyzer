"""Pfad-Logik für Entwicklung UND gepackte App (PyInstaller).

Im Entwicklungsmodus liegen Cache und Sprites wie gehabt im Projektordner
unter ``data/``. In der gepackten App (.app auf macOS, .exe auf Windows)
ist der Programmordner aber nicht zuverlässig beschreibbar - dort wandern
die Daten nach ``~/.pokemon_team_analyzer/data`` und werden beim ersten
Start einmalig aus den mitgelieferten Bundle-Daten befüllt (Seeding),
damit die App nicht mit leerer Pokemon-Liste startet.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True, wenn das Programm als PyInstaller-Bundle läuft."""
    return getattr(sys, "frozen", False)


def bundle_data_dir() -> Path:
    """Read-only-Datenordner im PyInstaller-Bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "data"


def project_data_dir() -> Path:
    """data/-Ordner im Projekt (Entwicklungsmodus)."""
    return Path(__file__).resolve().parent.parent / "data"


def user_data_dir() -> Path:
    """Beschreibbarer Datenordner für die gepackte App."""
    return Path.home() / ".pokemon_team_analyzer" / "data"


def data_dir() -> Path:
    """Liefert den richtigen (beschreibbaren) Datenordner.

    Gepackte App: ``~/.pokemon_team_analyzer/data`` - beim ersten Aufruf
    werden Cache und Sprites aus dem Bundle dorthin kopiert.
    Entwicklung: ``<projekt>/data`` wie bisher.
    """
    if not is_frozen():
        return project_data_dir()

    target = user_data_dir()
    if not (target / "cache").exists():
        target.mkdir(parents=True, exist_ok=True)
        source = bundle_data_dir()
        for sub in ("cache", "sprites"):
            src = source / sub
            if src.exists():
                shutil.copytree(src, target / sub, dirs_exist_ok=True)
    return target


def app_icon_path() -> Path:
    """Pfad zum App-Icon (PNG), funktioniert gepackt und ungepackt."""
    if is_frozen():
        return bundle_data_dir() / "app_icon.png"
    return project_data_dir() / "app_icon.png"
