"""TeamAnalyzer - die "Data-Science"-Schicht der Anwendung.

Hier kommen Pandas DataFrames zum Einsatz:
- to_stats_dataframe(): wandelt das Team in einen DataFrame um
- type_coverage(): aggregiert Schwächen und Resistenzen über alle Teammitglieder
- summary(): Pandas-Statistik (mean, max, min) über alle Base-Stats
- Visualisierungen mit matplotlib

Komplexitäts-Hinweis:
Die Methoden iterieren genau einmal über die Teammitglieder (O(n))
und einmal über die 18 Typen (konstant, weil 18 fix). Das ergibt
O(n * 18) = O(n), keine versteckten quadratischen Schleifen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from .type_chart import ALL_TYPES, TypeChart

if TYPE_CHECKING:  # nur für Typ-Hints, keine Laufzeit-Abhängigkeit
    from matplotlib.axes import Axes

    from .team import Team


class TeamAnalyzer:
    """Analysiert ein Team mit Pandas und matplotlib."""

    def __init__(self, team: "Team", type_chart: TypeChart | None = None) -> None:
        if len(team) == 0:
            raise ValueError("Team ist leer - nichts zu analysieren.")
        self._team = team
        self._type_chart = type_chart or TypeChart()

    # ------------------------------------------------------------------ #
    # DataFrames
    # ------------------------------------------------------------------ #
    def to_stats_dataframe(self) -> pd.DataFrame:
        """Ein Pokemon pro Zeile, eine Stat pro Spalte."""
        rows = []
        for p in self._team:
            row = {"name": p.name, "pokedex_id": p.pokedex_id,
                   "types": "/".join(p.types)}
            row.update(p.stats)
            row["total"] = p.total_stats()
            rows.append(row)
        df = pd.DataFrame(rows).set_index("name")
        return df

    def summary(self) -> pd.DataFrame:
        """Statistik (mean, min, max, std) pro Base-Stat über das Team."""
        df = self.to_stats_dataframe()
        # Nur numerische Spalten beachten - 'types' ist Text.
        numeric = df.drop(columns=["pokedex_id", "types"])
        return numeric.agg(["mean", "min", "max", "std"]).round(2)

    # ------------------------------------------------------------------ #
    # Typ-Coverage
    # ------------------------------------------------------------------ #
    def type_coverage(self) -> pd.DataFrame:
        """Für jeden der 18 Angriffstypen: wie viele Teammitglieder
        sind schwach / neutral / resistent?

        Liefert einen DataFrame mit Spalten 'weak', 'neutral', 'resists', 'immune'
        indiziert nach Angriffstyp.
        """
        # Vorberechnung: Für jedes Pokemon, gegen jeden Typ, der Multiplikator.
        # Komplexität: O(team_size * 18). Kein quadratischer Algorithmus.
        per_member: list[dict[str, float]] = []
        for p in self._team:
            mults = {
                atk: self._type_chart.effectiveness(atk, p.types)
                for atk in ALL_TYPES
            }
            per_member.append(mults)

        rows = []
        for atk in ALL_TYPES:
            weak = neutral = resists = immune = 0
            for member_mults in per_member:
                m = member_mults[atk]
                if m == 0.0:
                    immune += 1
                elif m < 1.0:
                    resists += 1
                elif m > 1.0:
                    weak += 1
                else:
                    neutral += 1
            rows.append({
                "type": atk,
                "weak": weak,
                "neutral": neutral,
                "resists": resists,
                "immune": immune,
            })
        return pd.DataFrame(rows).set_index("type")

    def biggest_weaknesses(self, top_n: int = 5) -> pd.Series:
        """Die Angriffstypen, gegen die das Team am meisten Pokemon mit Schwäche hat."""
        cov = self.type_coverage()
        return cov["weak"].sort_values(ascending=False).head(top_n)

    # ------------------------------------------------------------------ #
    # Visualisierungen
    # ------------------------------------------------------------------ #
    def plot_stats_comparison(self, ax: "Axes | None" = None) -> "Axes":
        """Gruppiertes Balkendiagramm: jede Stat als Gruppe, ein Balken pro Pokemon."""
        import matplotlib.pyplot as plt  # lokal importiert für Test-Performance

        df = self.to_stats_dataframe().drop(columns=["pokedex_id", "types", "total"])
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 5))
        df.T.plot(kind="bar", ax=ax)
        ax.set_title(f"Base-Stats - Team {self._team.name}")
        ax.set_ylabel("Wert")
        ax.set_xlabel("Stat")
        ax.legend(title="Pokemon", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.figure.tight_layout()
        return ax

    def plot_type_coverage_heatmap(self, ax: "Axes | None" = None) -> "Axes":
        """Heatmap: Zeilen = Teammitglieder, Spalten = Angriffstypen, Farbe = Multiplikator."""
        import matplotlib.pyplot as plt

        # Wir bauen die Matrix einmal sauber als DataFrame, dann mit imshow plotten
        # (statt seaborn zu importieren, das ist nicht in den Anforderungen).
        data = []
        names = []
        for p in self._team:
            names.append(p.name)
            data.append([
                self._type_chart.effectiveness(atk, p.types)
                for atk in ALL_TYPES
            ])
        df = pd.DataFrame(data, index=names, columns=ALL_TYPES)

        if ax is None:
            _, ax = plt.subplots(figsize=(12, max(3, 0.6 * len(df)) + 1))
        im = ax.imshow(df.values, cmap="RdYlGn_r", vmin=0, vmax=4, aspect="auto")
        ax.set_xticks(range(len(ALL_TYPES)))
        ax.set_xticklabels(ALL_TYPES, rotation=45, ha="right")
        ax.set_yticks(range(len(df)))
        ax.set_yticklabels(df.index)
        # Werte auf die Felder schreiben (kleines Hilfsmittel zum Lesen)
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                ax.text(j, i, f"{df.values[i, j]:g}", ha="center", va="center",
                        fontsize=8, color="black")
        ax.set_title(f"Typ-Schaden gegen Team {self._team.name} (Angriffstyp -> Mitglied)")
        ax.figure.colorbar(im, ax=ax, label="Multiplikator")
        ax.figure.tight_layout()
        return ax

    def plot_total_stats(self, ax: "Axes | None" = None) -> "Axes":
        """Horizontaler Balken: Total-Stats pro Pokemon (sortiert)."""
        import matplotlib.pyplot as plt

        df = self.to_stats_dataframe().sort_values("total")
        if ax is None:
            _, ax = plt.subplots(figsize=(8, max(3, 0.5 * len(df))))
        ax.barh(df.index, df["total"], color="#3b82f6")
        ax.set_xlabel("Total Base-Stats")
        ax.set_title(f"Gesamt-Stats - Team {self._team.name}")
        for i, v in enumerate(df["total"]):
            ax.text(v + 5, i, str(int(v)), va="center", fontsize=9)
        ax.figure.tight_layout()
        return ax
