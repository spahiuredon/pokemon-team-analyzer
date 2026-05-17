"""TypeChart - Typ-Effektivität für Pokemon.

Die Tabelle ist in den Spielen fest (18 Typen). Sie wäre auch über die
PokeAPI abrufbar (über /type/<name>), wird hier aber als statisches Dict
hinterlegt, damit:
- die Klasse offline arbeitet und Tests deterministisch sind
- die Logik im Notebook auch ohne Netz vorgeführt werden kann

Multiplikatoren:
- 0.0 -> Immune (z.B. Normal-Attacke auf Geist-Pokemon)
- 0.5 -> Nicht sehr effektiv
- 1.0 -> Normal
- 2.0 -> Sehr effektiv

Bei Dual-Typen werden die Multiplikatoren multipliziert
(0.5 * 0.5 = 0.25, 2.0 * 2.0 = 4.0).
"""

from __future__ import annotations

from typing import Iterable

# Die 18 Typen aus den modernen Pokemon-Spielen
ALL_TYPES: tuple[str, ...] = (
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
)

# Effektivität: TYPE_MATCHUPS[angreifender_typ][verteidigender_typ]
# Wenn nicht eingetragen, gilt 1.0 (normaler Schaden).
TYPE_MATCHUPS: dict[str, dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0,
                 "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0,
                 "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0,
                 "flying": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5,
                 "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0,
                 "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5,
                 "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5,
                 "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0,
                 "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5,
                 "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0,
                 "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0,
                 "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0,
                 "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5,
                 "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0,
                 "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5,
                 "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5,
                 "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0,
                 "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0,
                 "dark": 2.0, "steel": 0.5},
}


class TypeChart:
    """Berechnet, wie effektiv ein Angriff gegen ein (Dual-)Typ-Pokemon ist."""

    def __init__(self, matchups: dict[str, dict[str, float]] | None = None) -> None:
        self._matchups = matchups if matchups is not None else TYPE_MATCHUPS
        self._types = tuple(ALL_TYPES)

    @property
    def types(self) -> tuple[str, ...]:
        return self._types

    def effectiveness(self, attacker: str, defenders: Iterable[str]) -> float:
        """Effektivitäts-Multiplikator eines Angriffs.

        Args:
            attacker: Typ des Angriffs (z.B. 'fire').
            defenders: Typ(en) des verteidigenden Pokemon ('grass', 'water'...).

        Returns:
            Multiplikator (0.0, 0.25, 0.5, 1.0, 2.0, 4.0).
        """
        attacker = attacker.lower().strip()
        if attacker not in self._types:
            raise ValueError(f"Unbekannter Angreifer-Typ: {attacker}")
        defenders = list(defenders)
        if not defenders:
            raise ValueError("Mindestens ein Verteidiger-Typ erforderlich.")
        multiplier = 1.0
        for defender in defenders:
            d = defender.lower().strip()
            if d not in self._types:
                raise ValueError(f"Unbekannter Verteidiger-Typ: {d}")
            multiplier *= self._matchups.get(attacker, {}).get(d, 1.0)
        return multiplier

    def weaknesses_of(self, defender_types: Iterable[str]) -> dict[str, float]:
        """Für ein gegebenes Pokemon: welche Typen sind super-effektiv?

        Liefert nur Typen mit Multiplikator > 1.0.
        """
        defender_types = list(defender_types)
        return {
            atk: self.effectiveness(atk, defender_types)
            for atk in self._types
            if self.effectiveness(atk, defender_types) > 1.0
        }

    def resistances_of(self, defender_types: Iterable[str]) -> dict[str, float]:
        """Welche Typen machen <1.0 Schaden (Resistenzen + Immunitäten)?"""
        defender_types = list(defender_types)
        return {
            atk: self.effectiveness(atk, defender_types)
            for atk in self._types
            if self.effectiveness(atk, defender_types) < 1.0
        }
