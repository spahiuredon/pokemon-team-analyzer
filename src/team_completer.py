"""Auto-Vervollständigung für Pokemon-Teams.

Ausgangslage: das Team enthält bereits einige Lieblings-Pokemon. Der
Completer füllt es greedy auf bis zu 6 Mitglieder auf, sodass die
Typ-Abdeckung des Gesamtteams möglichst stabil und die durchschnittlichen
Base-Stats möglichst hoch sind.

Algorithmus:
1. Für jeden Kandidaten wird ein Score berechnet (siehe `score()`).
2. Der Kandidat mit dem höchsten Score wird ins Team aufgenommen.
3. Schritt 1 und 2 werden wiederholt, bis das Team voll ist oder
   keine Kandidaten mehr im Pool sind.

Komplexität:
- pro Iteration: O(|pool| * (|team| + 18 Typen))
- gesamt: O(6 * |pool| * (6 + 18)) = O(|pool|) bei festem Maximum 6
Das ist linear in der Pool-Grösse, ohne versteckte quadratische Pfade.

Limitierung:
- Optionaler `max_generation`-Filter (1-9). Kandidaten ausserhalb des
  gewünschten Bereichs werden vor der Auswahl entfernt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .type_chart import TypeChart

if TYPE_CHECKING:
    from .pokemon import Pokemon
    from .team import Team


# Bereiche der Pokemon-IDs pro Hauptserien-Generation (Stand: Gen 9).
# Quelle: Bulbapedia "List of Pokemon by National Pokedex number".
GENERATION_RANGES: dict[int, tuple[int, int]] = {
    1: (1, 151),
    2: (152, 251),
    3: (252, 386),
    4: (387, 493),
    5: (494, 649),
    6: (650, 721),
    7: (722, 809),
    8: (810, 905),
    9: (906, 1025),
}


def generation_of(pokedex_id: int) -> int:
    """Zu welcher Generation gehört dieses Pokemon?

    Liefert 0, wenn die ID ausserhalb aller bekannten Bereiche liegt
    (z.B. Mega-Formen mit künstlich hohen IDs).
    """
    for gen, (lo, hi) in GENERATION_RANGES.items():
        if lo <= pokedex_id <= hi:
            return gen
    return 0


class TeamCompleter:
    """Vervollständigt ein Team aus einem Pool von Kandidaten."""

    # Gewichte der drei Scoring-Komponenten - bewusst leicht abgestimmt,
    # damit Coverage am stärksten zählt (das ist der Hauptnutzen), aber
    # Stats und Diversität ihren Einfluss haben.
    WEIGHT_STATS = 1.5
    WEIGHT_COVERAGE = 2.5
    WEIGHT_DIVERSITY = 1.0

    # Realistische Obergrenze für Total-Stats (Arceus = 720). Wird für
    # die Normalisierung benutzt.
    MAX_TOTAL_STATS = 720.0

    def __init__(
        self,
        pool: Iterable["Pokemon"],
        type_chart: TypeChart | None = None,
    ) -> None:
        self._pool: list["Pokemon"] = list(pool)
        if not self._pool:
            raise ValueError("Pool darf nicht leer sein.")
        self._type_chart = type_chart or TypeChart()

    # ------------------------------------------------------------------ #
    # Pool-Verwaltung
    # ------------------------------------------------------------------ #
    @property
    def pool_size(self) -> int:
        return len(self._pool)

    def candidates(self, max_generation: int | None = None) -> list["Pokemon"]:
        """Alle Pool-Pokemon, optional gefiltert nach maximaler Generation.

        max_generation=None heisst: keine Filterung (alle Generationen).
        """
        if max_generation is None:
            return list(self._pool)
        return [p for p in self._pool
                if 0 < generation_of(p.pokedex_id) <= max_generation]

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def score(self, candidate: "Pokemon", current_team: "Team") -> float:
        """Wie gut passt der Kandidat zum aktuellen Team?

        Setzt sich aus drei Teilen zusammen:
        1. Stats-Stärke (normalisiert auf Total-Stats / MAX_TOTAL_STATS)
        2. Coverage-Bonus: macht der Kandidat Lücken im Team kleiner?
        3. Diversitäts-Bonus: bringt er Typen, die noch nicht im Team sind?
        """
        # 1. Stats - höhere Base-Total-Stats sind besser
        stat_score = candidate.total_stats() / self.MAX_TOTAL_STATS

        # 2. Coverage - welche Typen sind aktuelle Schwächen des Teams,
        # und wie gut deckt sie der Kandidat ab?
        coverage_score = 0.0
        team_size = len(current_team)
        if team_size > 0:
            # Welche Angriffstypen treffen mehrere Team-Mitglieder schwach?
            weak_count: dict[str, int] = {}
            for member in current_team:
                for atk in self._type_chart.weaknesses_of(member.types):
                    weak_count[atk] = weak_count.get(atk, 0) + 1
            # Pro relevanter Schwäche prüfen, ob der Kandidat resistent ist
            for atk, count in weak_count.items():
                if count <= team_size / 2:
                    # Nur Schwächen, die mindestens die Hälfte des Teams treffen
                    continue
                mult = self._type_chart.effectiveness(atk, candidate.types)
                if mult < 1.0:
                    # Belohnt wird sowohl Resistenz (0.5) als auch Immunität (0.0).
                    coverage_score += (1.0 - mult) * (count / team_size)

        # 3. Diversität - neue Typen sind willkommen
        existing_types: set[str] = set()
        for member in current_team:
            existing_types.update(member.types)
        new_types = sum(1 for t in candidate.types if t not in existing_types)
        diversity_score = new_types / max(len(candidate.types), 1)

        return (
            self.WEIGHT_STATS * stat_score
            + self.WEIGHT_COVERAGE * coverage_score
            + self.WEIGHT_DIVERSITY * diversity_score
        )

    # ------------------------------------------------------------------ #
    # Greedy-Auswahl
    # ------------------------------------------------------------------ #
    def complete(
        self,
        team: "Team",
        max_generation: int | None = None,
    ) -> "Team":
        """Fülle das Team auf bis zu Team.MAX_SIZE Pokemon auf.

        Wenn das Team schon voll oder kein Kandidat verfügbar ist, gibt
        es einfach das unveränderte Team zurück.

        Mutiert das übergebene Team und gibt es ebenfalls zurück
        (praktisch für Method-Chaining im Notebook).
        """
        already_in_team = {p.pokedex_id for p in team}
        candidates = [
            c for c in self.candidates(max_generation)
            if c.pokedex_id not in already_in_team
        ]

        # Greedy: bei jedem Schritt das maximale Element nehmen.
        while len(team) < team.MAX_SIZE and candidates:
            best = max(candidates, key=lambda c: self.score(c, team))
            team.add(best)
            candidates.remove(best)
        return team
