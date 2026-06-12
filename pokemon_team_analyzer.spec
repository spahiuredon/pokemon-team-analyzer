# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für den Pokemon Team-Analyzer.

Bauen:
    macOS:    pyinstaller pokemon_team_analyzer.spec   (ergibt dist/Pokemon Team-Analyzer.app)
    Windows:  pyinstaller pokemon_team_analyzer.spec   (ergibt dist/Pokemon Team-Analyzer/...exe)

Wichtig: Der Build muss auf der Zielplattform laufen - eine Windows-.exe
entsteht nur auf Windows, eine .app nur auf macOS.
"""

import sys
from pathlib import Path

APP_NAME = "Pokemon Team-Analyzer"
ROOT = Path(SPECPATH)

# Mitgelieferte Daten: Pokemon-Cache, Sprites und Icons. Damit startet
# die App offline-fähig mit voller Pokemon-Liste (Seeding beim 1. Start).
datas = [
    (str(ROOT / "data" / "cache"), "data/cache"),
    (str(ROOT / "data" / "sprites"), "data/sprites"),
    (str(ROOT / "data" / "app_icon.png"), "data"),
    (str(ROOT / "data" / "german_names.json"), "data"),
    (str(ROOT / "web" / "index.html"), "web"),
]

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    # `data.fetch_all_pokemon` wird erst zur Laufzeit importiert
    # (Bulk-Download) - PyInstaller sieht das nicht automatisch.
    hiddenimports=["data.fetch_all_pokemon"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["jupyter", "notebook", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    icon_file = str(ROOT / "data" / "app_icon.icns")
elif sys.platform.startswith("win"):
    icon_file = str(ROOT / "data" / "app_icon.ico")
else:
    icon_file = None

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI-App: kein Terminal-Fenster
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

# Auf macOS zusätzlich ein richtiges .app-Bundle (Dock-Name & Icon).
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon_file,
        bundle_identifier="ch.redon.pokemon-team-analyzer",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "NSHighResolutionCapable": True,
        },
    )
