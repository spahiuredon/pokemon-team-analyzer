"""Auto-Vervollständigung für Pokemon-Teams.

Ausgangslage: das Team enthält bereits einige Lieblings-Pokemon. Der
Completer füllt es auf bis zu 6 Mitglieder auf, sodass die Typ-Abdeckung
des Gesamtteams möglichst stabil ist und das Team zur jeweiligen
Generation passt.

Philosophie: Es soll ein *interessantes* Team entstehen, kein maximal
starkes. Darum:
- Legendäre und Mythische Pokemon sind standardmässig ausgeschlossen
  (per `allow_legendary=True` zuschaltbar).
- Statt roher Stat-Summe zählt ein "Sweet Spot" um ~510 Total-Stats -
  also voll entwickelte, spielbare Pokemon. Pseudo-Legendäre (600) sind
  weiterhin möglich, dominieren aber nicht mehr automatisch.
- Pro Schritt wird gewichtet-zufällig aus den besten Kandidaten gewählt,
  sodass nicht jedes Mal dasselbe Team herauskommt.

Algorithmus:
1. Für jeden Kandidaten wird ein Score berechnet (siehe `score()`).
2. Aus den Top-Kandidaten wird einer (Score-gewichtet) gezogen.
3. Schritt 1 und 2 wiederholen, bis das Team voll ist oder
   keine Kandidaten mehr im Pool sind.
"""

from __future__ import annotations

import random
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


# Pokédex-IDs aller Legendären, Mythischen und Ultrabestien (Gen 1-9).
# Statisches Spielwissen, analog zur Typ-Tabelle - so braucht es keinen
# zusätzlichen API-Aufruf pro Pokemon (die Info steckt im
# /pokemon-species-Endpoint, nicht in den gecachten /pokemon-Daten).
SPECIAL_POKEMON_IDS: frozenset[int] = frozenset(
    # Gen 1: Arktos, Zapdos, Lavados, Mewtu, Mew
    [144, 145, 146, 150, 151]
    # Gen 2: Raikou, Entei, Suicune, Lugia, Ho-Oh, Celebi
    + [243, 244, 245, 249, 250, 251]
    # Gen 3: Regis, Latias/Latios, Kyogre, Groudon, Rayquaza,
    #        Jirachi, Deoxys
    + [377, 378, 379, 380, 381, 382, 383, 384, 385, 386]
    # Gen 4: Seenplatten-Trio, Dialga, Palkia, Heatran, Regigigas,
    #        Giratina, Cresselia, Phione, Manaphy, Darkrai, Shaymin, Arceus
    + list(range(480, 494))
    # Gen 5: Victini, Musketier-Trio, Kami-Trio, Reshiram, Zekrom,
    #        Landorus, Kyurem, Keldeo, Meloetta, Genesect
    + [494] + list(range(638, 650))
    # Gen 6: Xerneas, Yveltal, Zygarde, Diancie, Hoopa, Volcanion
    + list(range(716, 722))
    # Gen 7: Typ:Null & Amigento, Kapu-Quartett, Cosmog-Linie,
    #        Ultrabestien, Necrozma, Magearna, Marshadow, Zeraora,
    #        Meltan, Melmetal
    + [772, 773] + list(range(785, 810))
    # Gen 8: Zacian, Zamazenta, Endynalos, Wulaosu-Linie, Zarude,
    #        Regieleki/Regidrago, Polaross/Phantoross, Coronospa, Cupidos
    + list(range(888, 899)) + [905]
    # Gen 9: Schatztruhen-Quartett, Koraidon/Miraidon,
    #        Treuhand-Trio + Ogerpon, Terapagos, Infamomo
    + list(range(1001, 1005)) + [1007, 1008]
    + list(range(1014, 1018)) + [1024, 1025]
)


def is_special(pokedex_id: int) -> bool:
    """True für Legendäre, Mythische und Ultrabestien."""
    return pokedex_id in SPECIAL_POKEMON_IDS


def _is_alternate_form(name: str) -> bool:
    """Erkennt Mega-/Gigadynamax-/Totem-Formen am Namen.

    Solche Einträge sollten nach dem Bulk-Download gar nicht im Cache
    sein, aber falls doch, werden sie bei der Team-Vervollständigung
    ignoriert.
    """
    lowered = name.lower()
    return any(tag in lowered for tag in ("-mega", "-gmax", "-totem"))


class TeamCompleter:
    """Vervollständigt ein Team aus einem Pool von Kandidaten."""

    # Gewichte der drei Scoring-Komponenten - bewusst leicht abgestimmt,
    # damit Coverage am stärksten zählt (das ist der Hauptnutzen), aber
    # Stats und Diversität ihren Einfluss haben.
    WEIGHT_STATS = 1.5
    WEIGHT_COVERAGE = 2.5
    WEIGHT_DIVERSITY = 1.0

    # "Sweet Spot" für interessante Teams: voll entwickelte, spielbare
    # Pokemon liegen um ~480-550 Total-Stats. Der Stats-Score fällt
    # links und rechts davon linear ab - so dominieren weder schwache
    # Erstformen noch 700er-Legendäre die Auswahl.
    TARGET_TOTAL_STATS = 510.0
    STATS_TOLERANCE = 250.0

    # Aus wie vielen Top-Kandidaten pro Schritt gewichtet-zufällig
    # gezogen wird. 1 = immer der Beste (deterministisch).
    VARIETY_POOL_SIZE = 5

    def __init__(
        self,
        pool: Iterable["Pokemon"],
        type_chart: TypeChart | None = None,
        rng: random.Random | None = None,
    ) -> None:
        # Mega-/Sonderformen fliegen direkt beim Pool-Aufbau raus.
        self._pool: list["Pokemon"] = [
            p for p in pool if not _is_alternate_form(p.name)
        ]
        if not self._pool:
            raise ValueError("Pool darf nicht leer sein.")
        self._type_chart = type_chart or TypeChart()
        self._rng = rng or random.Random()

    # ------------------------------------------------------------------ #
    # Pool-Verwaltung
    # ------------------------------------------------------------------ #
    @property
    def pool_size(self) -> int:
        return len(self._pool)

    def candidates(
        self,
        max_generation: int | None = None,
        allow_legendary: bool = True,
        exact_generation: int | None = None,
    ) -> list["Pokemon"]:
        """Alle Pool-Pokemon, optional gefiltert.

        max_generation: nur Pokemon BIS zu dieser Generation (None = alle).
        exact_generation: nur Pokemon GENAU dieser Generation - z.B. für
            ein reines Gen-5-Team passend zu Schwarz/Weiss. Hat Vorrang
            vor max_generation.
        allow_legendary=False entfernt Legendäre/Mythische/Ultrabestien.
        """
        result = list(self._pool)
        if exact_generation is not None:
            result = [p for p in result
                      if generation_of(p.pokedex_id) == exact_generation]
        elif max_generation is not None:
            result = [p for p in result
                      if 0 < generation_of(p.pokedex_id) <= max_generation]
        if not allow_legendary:
            result = [p for p in result if not is_special(p.pokedex_id)]
        return result

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def score(self, candidate: "Pokemon", current_team: "Team") -> float:
        """Wie gut passt der Kandidat zum aktuellen Team?

        Setzt sich aus drei Teilen zusammen:
        1. Stats-Nähe zum Sweet Spot (~510 Total) - voll entwickelte,
           spielbare Pokemon, ohne dass Legendäre alles dominieren
        2. Coverage-Bonus: macht der Kandidat Lücken im Team kleiner?
        3. Diversitäts-Bonus: bringt er Typen, die noch nicht im Team sind?
        """
        # 1. Stats - am besten nahe am Sweet Spot, linear abfallend.
        distance = abs(candidate.total_stats() - self.TARGET_TOTAL_STATS)
        stat_score = max(0.0, 1.0 - distance / self.STATS_TOLERANCE)

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
    # Auswahl
    # ------------------------------------------------------------------ #
    def complete(
        self,
        team: "Team",
        max_generation: int | None = None,
        allow_legendary: bool = False,
        variety: bool = True,
        exact_generation: int | None = None,
    ) -> "Team":
        """Fülle das Team auf bis zu Team.MAX_SIZE Pokemon auf.

        Args:
            max_generation: nur Pokemon bis zu dieser Generation (None = alle).
            exact_generation: nur Pokemon GENAU dieser Generation - für
                ein sortenreines Team passend zu einem bestimmten Spiel.
            allow_legendary: Legendäre/Mythische/Ultrabestien zulassen
                (Standard: aus - für spannendere, nicht-overpowerte Teams).
            variety: pro Schritt gewichtet-zufällig aus den besten
                Kandidaten ziehen, statt stur den Top-Score zu nehmen.
                So entsteht bei jedem Aufruf ein anderes Team.

        Wenn das Team schon voll oder kein Kandidat verfügbar ist, gibt
        es einfach das unveränderte Team zurück. Mutiert das übergebene
        Team und gibt es ebenfalls zurück.
        """
        already_in_team = {p.pokedex_id for p in team}
        candidates = [
            c for c in self.candidates(max_generation, allow_legendary,
                                       exact_generation)
            if c.pokedex_id not in already_in_team
        ]

        while len(team) < team.MAX_SIZE and candidates:
            chosen = self._pick(candidates, team, variety)
            team.add(chosen)
            candidates.remove(chosen)
        return team

    def _pick(self, candidates: list["Pokemon"], team: "Team",
              variety: bool) -> "Pokemon":
        """Wählt den nächsten Kandidaten.

        variety=False: klassisch greedy (höchster Score gewinnt).
        variety=True: die besten VARIETY_POOL_SIZE Kandidaten kommen in
        einen Topf und einer wird Score-gewichtet gezogen - gute Wahl
        bleibt wahrscheinlich, aber das Ergebnis variiert.
        """
        scored = sorted(
            ((self.score(c, team), c) for c in candidates),
            key=lambda pair: pair[0], reverse=True,
        )
        if not variety or len(scored) == 1:
            return scored[0][1]
        top = scored[: self.VARIETY_POOL_SIZE]
        weights = [max(s, 0.01) ** 2 for s, _ in top]  # quadriert: gute bevorzugt
        return self._rng.choices([c for _, c in top], weights=weights, k=1)[0]
