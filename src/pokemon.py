"""Pokemon-Klassen.

- Konstruktor (__init__)
- Kapselung (private Attribute mit Validierung)
- Vererbung: MegaPokemon erbt von Pokemon und überschreibt total_stats()
- Spezielle Methoden: __repr__, __eq__

Die Pokemon-Klasse trennt die "rohen" API-Daten vom Domänenmodell:
Wir nehmen das große Dict von der PokeAPI und ziehen die wichtigen
Felder heraus, damit der Rest der App damit arbeiten kann ohne das
ganze JSON-Format kennen zu müssen.
"""

from __future__ import annotations

from typing import Any

# Die sechs Base-Stats wie in den Spielen
STAT_NAMES = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")


class Pokemon:
    """Repräsentiert ein einzelnes Pokemon mit Stats und Typen."""

    def __init__(
        self,
        name: str,
        pokedex_id: int,
        types: list[str],
        stats: dict[str, int],
        sprite_url: str | None = None,
    ) -> None:
        # Validierung im Konstruktor (V06 - Robustness)
        if not name or not isinstance(name, str):
            raise ValueError("Pokemon-Name muss ein nicht-leerer String sein.")
        if not isinstance(pokedex_id, int) or pokedex_id <= 0:
            raise ValueError("pokedex_id muss eine positive ganze Zahl sein.")
        if not types or not all(isinstance(t, str) for t in types):
            raise ValueError("types muss eine nicht-leere Liste von Strings sein.")
        if len(types) > 2:
            raise ValueError("Ein Pokemon hat höchstens zwei Typen.")
        missing = [s for s in STAT_NAMES if s not in stats]
        if missing:
            raise ValueError(f"Fehlende Stats: {missing}")
        for stat_name, stat_value in stats.items():
            if not isinstance(stat_value, int) or stat_value < 0:
                raise ValueError(f"Stat {stat_name} muss eine nicht-negative ganze Zahl sein.")

        self._name = name.lower()
        self._pokedex_id = pokedex_id
        # Wir kopieren die Listen/Dicts, damit Aufrufer sie nicht versehentlich mutieren.
        self._types = tuple(t.lower() for t in types)
        self._stats = dict(stats)
        self._sprite_url = sprite_url

    # --- Eigenschaften (gekapselt) --------------------------------------- #
    @property
    def name(self) -> str:
        return self._name

    @property
    def pokedex_id(self) -> int:
        return self._pokedex_id

    @property
    def types(self) -> tuple[str, ...]:
        return self._types

    @property
    def stats(self) -> dict[str, int]:
        # Defensive copy: außenstehender Code darf das Dict nicht ändern
        return dict(self._stats)

    @property
    def sprite_url(self) -> str | None:
        """Optionale URL zum Front-Sprite (PNG). Wird beim Laden via from_api gesetzt."""
        return self._sprite_url

    # --- Verhalten ------------------------------------------------------- #
    def total_stats(self) -> int:
        """Summe der sechs Base-Stats (gängigste Kennzahl für Pokemon-Stärke)."""
        return sum(self._stats.values())

    def is_dual_type(self) -> bool:
        return len(self._types) == 2

    # --- Erzeuger ------------------------------------------------------- #
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Pokemon":
        """Erstellt ein Pokemon aus dem Rohdaten-Dict der PokeAPI.

        Beispiel-Struktur, die wir erwarten:
            {
              "name": "pikachu",
              "id": 25,
              "types": [{"type": {"name": "electric"}}, ...],
              "stats": [{"stat": {"name": "hp"}, "base_stat": 35}, ...],
            }
        """
        try:
            name = data["name"]
            pokedex_id = int(data["id"])
            types = [entry["type"]["name"] for entry in data["types"]]
            stats = {
                entry["stat"]["name"]: int(entry["base_stat"])
                for entry in data["stats"]
            }
            # Das sprite-Feld ist optional - die PokeAPI liefert es bei allen
            # echten Pokemon, aber wir geben uns mit None zufrieden, falls nicht.
            sprite_url = None
            sprites = data.get("sprites")
            if isinstance(sprites, dict):
                sprite_url = sprites.get("front_default")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"PokeAPI-Daten haben unerwartetes Format: {exc}") from exc
        return cls(name=name, pokedex_id=pokedex_id, types=types,
                   stats=stats, sprite_url=sprite_url)

    # --- Standard-Magic-Methods ----------------------------------------- #
    def __repr__(self) -> str:
        types_str = "/".join(t.capitalize() for t in self._types)
        return f"Pokemon(#{self._pokedex_id} {self._name.capitalize()} [{types_str}])"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Pokemon):
            return NotImplemented
        return self._pokedex_id == other._pokedex_id

    def __hash__(self) -> int:
        return hash(("Pokemon", self._pokedex_id))


class MegaPokemon(Pokemon):
    """Eine Mega-Entwicklung eines Pokemon.

    Demonstriert Vererbung (V03):
    - Erbt alle Attribute & Methoden von Pokemon
    - Erweitert um einen Stats-Boost
    - Überschreibt total_stats(): zählt den Mega-Bonus mit
    """

    MEGA_STAT_BOOST = 100  # Pauschal +100 auf die Summe (Schätzwert im Sinne der Aufgabe)

    def __init__(
        self,
        name: str,
        pokedex_id: int,
        types: list[str],
        stats: dict[str, int],
        base_form: str,
        sprite_url: str | None = None,
    ) -> None:
        super().__init__(name=name, pokedex_id=pokedex_id, types=types,
                         stats=stats, sprite_url=sprite_url)
        if not base_form:
            raise ValueError("base_form muss angegeben sein (z.B. 'charizard').")
        self._base_form = base_form.lower()

    @property
    def base_form(self) -> str:
        return self._base_form

    def total_stats(self) -> int:
        # Überschreibung: Mega-Pokemon haben einen festen Bonus auf ihre Stats-Summe.
        return super().total_stats() + self.MEGA_STAT_BOOST

    def __repr__(self) -> str:
        return f"MegaPokemon(of {self._base_form.capitalize()} -> {self._name})"
