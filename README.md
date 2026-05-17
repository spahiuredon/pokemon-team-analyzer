# Pokémon Team-Analyzer

**INFPROG2 FS26 - Semesterprojekt**
Autor: Redon

## Projektbeschreibung

Der Pokémon Team-Analyzer lädt Pokemon-Daten von der öffentlichen
[PokeAPI](https://pokeapi.co/), packt sie in ein
benutzerdefiniertes Team, und analysiert die Stärken und
Schwächen des Teams mit Pandas und matplotlib. Insbesondere
berechnet er die Typ-Coverage (welche Angriffstypen sind für das
Team gefährlich) und visualisiert die Base-Stats der
Teammitglieder.

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

### GUI starten (empfohlen für die Live-Demo)

```bash
python -m src.gui
```

Es öffnet sich ein Fenster: links Team-Verwaltung (Pokemon
hinzufügen per Eingabe oder Doppelklick auf die Cache-Liste,
vorgefertigte Champion-Teams aus mehreren Generationen,
Entfernen, Leeren), in der Mitte das aktuelle Team mit Sprites,
rechts Tabs für Tabellen und eingebettete matplotlib-Plots
(Stats, Typ-Coverage, Heatmap). Tkinter kommt mit Python (auf
macOS und Windows von Haus aus, unter Linux mit
`apt install python3-tk`).

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

Erwartete Ausgabe: `Ran 21 tests in 0.00Xs - OK`.

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
| `tests/`               | 21 Unit-Tests, decken jede Klasse ab. Der API-Client wird mit `unittest.mock` getestet, damit keine echten Netzwerk-Aufrufe nötig sind. |
| `notebooks/demo.ipynb` | Demo, die alle Kompetenzen sichtbar macht. |
| `data/seed_cache.py`   | Optional: legt bekannte Pokemon im Cache an, damit die Demo auch ohne Internet funktioniert. |

## Datenquelle

Alle Pokemon-Daten stammen aus der offiziellen
[PokeAPI](https://pokeapi.co/) (frei, kein API-Key nötig). Die
Typ-Effektivitätstabelle ist im Code hinterlegt (statisches Wissen
aus den Spielen), um die Analyse unabhängig vom Netz zu machen.

## Komplexität

Die Hauptanalyse (`type_coverage`) iteriert einmal über alle
Teammitglieder ($n \le 6$) und einmal über die 18 Typen
(Konstante). Damit ist die Laufzeit $\mathcal{O}(n)$ - keine
versteckten quadratischen Schleifen.
