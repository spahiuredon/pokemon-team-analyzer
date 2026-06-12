# Pokémon Team-Analyzer

Desktop-App zum Zusammenstellen und Analysieren von Pokemon-Teams -
mit eingebauter Save-Synchronisation zwischen einem gemoddeten 3DS
und PC-Emulatoren.

Die App lädt Pokemon-Daten von der öffentlichen
[PokeAPI](https://pokeapi.co/), packt sie in ein
benutzerdefiniertes Team und analysiert die Stärken und
Schwächen des Teams: Typ-Coverage (welche Angriffstypen sind für
das Team gefährlich), Base-Stats-Vergleiche und eine
Typ-Effektivitäts-Heatmap. Das GUI ist mit CustomTkinter gebaut
und folgt automatisch dem Hell-/Dunkelmodus des Systems.

## Installation

Voraussetzung: Python 3.10+.

```bash
git clone <repo-url>
cd pokemon-team-analyzer
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Ausführen

### GUI starten

```bash
python -m src.gui
```

Es öffnet sich ein Fenster: links die Sidebar mit Suche,
Pokemon-Liste, vorgefertigten Champion-Teams und
Auto-Vervollständigung; in der Mitte das aktuelle Team als Karten
mit Sprites und Typ-Badges; rechts Tabs für Stats-Tabelle,
Typ-Coverage, Plots und den 3DS-Sync. Die Analyse-Tabs
aktualisieren sich automatisch, sobald sich das Team ändert.
Tkinter kommt mit Python (auf macOS und Windows von Haus aus,
unter Linux mit `apt install python3-tk`).

### Demo-Notebook

```bash
jupyter notebook notebooks/demo.ipynb
```

Das Notebook lädt sechs Pokemon, baut ein Team, zeigt die Stats
als Pandas DataFrame, berechnet die Typ-Coverage und produziert
drei Diagramme.

### Tests laufen lassen

```bash
python -m unittest discover -s tests -v
```

Erwartete Ausgabe: `Ran 52 tests in 0.0Xs - OK`.

### Cache vorbefüllen (optional, hilfreich bei schlechtem Netz)

```bash
python data/seed_cache.py
```

## Modul-Übersicht

| Datei                  | Inhalt |
|------------------------|--------|
| `src/api_client.py`    | `PokeAPIClient` - HTTP via `urllib`, Retries, Timeouts, JSON-Validierung, lokaler Datei-Cache. |
| `src/pokemon.py`       | `Pokemon` (Basisklasse mit Validierung, `from_api`-Factory) und `MegaPokemon` (Vererbung mit überschriebener `total_stats()`). |
| `src/type_chart.py`    | `TypeChart` - die 18×18 Typ-Effektivitäts-Matrix, mit `effectiveness()`, `weaknesses_of()`, `resistances_of()`. |
| `src/team.py`          | `Team` - Sammlung von max. 6 Pokemon, mit `add`, `remove`, Duplikat- und Größenprüfung. |
| `src/analyzer.py`      | `TeamAnalyzer` - die Pandas-Schicht: `to_stats_dataframe`, `summary`, `type_coverage`, `biggest_weaknesses` und drei matplotlib-Plots. |
| `src/gui.py`           | `PokemonTeamGUI` - einfaches Tkinter-Fenster zum Zusammenstellen des Teams und zum Anzeigen aller Analysen + Plots. |
| `src/presets.py`       | Vorgefertigte Champion-Teams aus den Hauptspielen (Gen 1 Klassiker, Gen 1 Blue, Gen 3 Steven, Gen 4 Cynthia). |
| `src/team_completer.py`| `TeamCompleter` - Greedy-Algorithmus, der ein partielles Team auf 6 Pokemon auffüllt. Berücksichtigt Total-Stats, Typ-Coverage (deckt Schwächen ab) und Typ-Diversität. Mit optionalem Generations-Filter (Gen 1-9). |
| `src/save_sync.py`     | Save-Synchronisation 3DS↔PC: Spiele-Registry (Platin bis Ultra Mond), FTP-Client für ftpd, Sync-Engine (neuester gewinnt, SHA-256-Vergleich, automatische Backups), optionaler Cloud-Ordner. |
| `src/sync_gui.py`      | Der "3DS Sync"-Tab im GUI: Verbindung, Spiel-Einrichtung mit FTP-Browser, Sync-Buttons, Protokoll. |
| `src/app_paths.py`     | Frozen-aware Pfadlogik: die gepackte App (PyInstaller) nutzt `~/.pokemon_team_analyzer/data` statt des Programmordners. |
| `tests/`               | 52 Unit-Tests, decken jede Klasse ab. Der API-Client wird mit `unittest.mock` getestet, die Sync-Engine mit In-Memory-Quellen - keine echten Netzwerk-Aufrufe nötig. |
| `notebooks/demo.ipynb` | Notebook mit einer Beispiel-Analyse. |
| `data/seed_cache.py`   | Optional: legt bekannte Pokemon im Cache an, damit die Demo auch ohne Internet funktioniert. |

## Datenquelle

Alle Pokemon-Daten stammen aus der offiziellen
[PokeAPI](https://pokeapi.co/) (frei, kein API-Key nötig). Die
Typ-Effektivitätstabelle ist im Code hinterlegt (statisches Wissen
aus den Spielen), um die Analyse unabhängig vom Netz zu machen.

## Save-Sync: 3DS ↔ PC-Emulator

Der Tab **"3DS Sync"** synchronisiert Spielstände von Pokemon Platin bis
Pokemon Ultra Sonne/Ultra Mond zwischen einem gemoddeten 3DS und den
PC-Emulatoren **melonDS** (DS-Spiele) und **Azahar** (3DS-Spiele).

### Voraussetzungen

Auf dem 3DS (mit Custom Firmware):

- **ftpd** (FTP-Server, aus dem Homebrew-Store) - läuft während des Syncs,
  die IP-Adresse steht oben am Bildschirm. Standard-Port: 5000.
- Für **DS-Spiele** (Platin, HG/SS, Schwarz/Weiss, Schwarz 2/Weiss 2):
  **TWiLight Menu++**. Der Spielstand ist eine rohe `.sav`-Datei auf der
  SD-Karte - exakt das Format, das auch melonDS nutzt.
- Für **3DS-Spiele** (X/Y, OR/AS, Sonne/Mond, US/UM): **Checkpoint**.
  3DS-Saves liegen verschlüsselt im System; Checkpoint exportiert sie als
  rohe Dateien auf die SD-Karte, von wo die App sie holt.

### Ablauf

1. Auf dem 3DS ftpd starten, im Tab die IP eintragen, "Verbindung testen".
2. Spiel auswählen, "Einrichten...": PC-Save-Datei wählen (bei
   3DS-Spielen findet "Auto" den Azahar-Save selbst) und den 3DS-Pfad
   setzen (bei 3DS-Spielen wird das neueste Checkpoint-Backup automatisch
   gefunden; bei DS-Spielen die `.sav` über "3DS durchsuchen..." wählen).
3. "Sync" - der neueste Stand gewinnt (SHA-256-Vergleich erkennt
   identische Stände), die überschriebene Seite wird vorher automatisch
   nach `~/.pokemon_team_analyzer/backups` gesichert.

Besonderheit 3DS-Spiele: Richtung PC→3DS legt die App ein neues
Checkpoint-Backup `PCSYNC_<zeit>` an - auf dem 3DS dann in Checkpoint
einfach dieses Backup wiederherstellen. Richtung 3DS→PC: vorher auf dem
3DS in Checkpoint ein frisches Backup anlegen.

### Cloud-Sync (mehrere PCs)

Der 3DS kann nicht direkt mit Google Drive reden - aber die App kann
zusätzlich einen **Cloud-Ordner** mitsynchronisieren. Einfach den lokalen
Google-Drive-/Dropbox-Ordner als Cloud-Ordner wählen: Die App legt darin
`pokemon_saves/` an und bezieht ihn als dritte Quelle in den
"neuester gewinnt"-Vergleich ein. So bleiben mehrere PCs automatisch
über die Cloud synchron.

## Als App bauen (macOS und Windows)

Die Anwendung lässt sich mit PyInstaller zu einer eigenständigen App
bündeln (Python-Installation beim Endnutzer nicht nötig). Der Build muss
auf der jeweiligen Zielplattform laufen:

```bash
# macOS -> dist/Pokemon Team-Analyzer.app
./build_mac.sh
```

```bat
:: Windows -> dist\Pokemon Team-Analyzer\Pokemon Team-Analyzer.exe
build_windows.bat
```

Die Skripte legen ein eigenes Build-venv an, installieren PyInstaller und
bauen anhand von `pokemon_team_analyzer.spec`. Der Pokemon-Cache und die
Sprites werden mitgeliefert; beim ersten Start kopiert die App sie nach
`~/.pokemon_team_analyzer/data` (beschreibbar, App-Ordner bleibt sauber).

## Nächste Schritte

Das GUI weiter verbessern (z.B. Fortschrittsanzeige beim Sync mehrerer
Spiele auf einmal) und signierte Installer (DMG/MSI) für die Verteilung
ausserhalb des eigenen Rechners bauen.
