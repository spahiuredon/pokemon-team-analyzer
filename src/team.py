"""Team-Klasse: Sammlung von Pokemon."""

from __future__ import annotations

from typing import Iterable, Iterator

from .pokemon import Pokemon


class Team:
    """Ein Pokemon-Team (max. 6, wie in den Spielen)."""

    MAX_SIZE = 6

    def __init__(self, name: str, members: Iterable[Pokemon] | None = None) -> None:
        if not name:
            raise ValueError("Team-Name darf nicht leer sein.")
        self._name = name
        self._members: list[Pokemon] = []
        if members is not None:
            for pkmn in members:
                self.add(pkmn)

    @property
    def name(self) -> str:
        return self._name

    @property
    def members(self) -> tuple[Pokemon, ...]:
        return tuple(self._members)

    def add(self, pokemon: Pokemon) -> None:
        """Fügt ein Pokemon hinzu (Duplikate verboten)."""
        if not isinstance(pokemon, Pokemon):
            raise TypeError("Nur Pokemon-Objekte dürfen ins Team.")
        if len(self._members) >= self.MAX_SIZE:
            raise ValueError(f"Team ist voll (max. {self.MAX_SIZE} Pokemon).")
        if pokemon in self._members:
            raise ValueError(f"{pokemon.name} ist bereits im Team.")
        self._members.append(pokemon)

    def remove(self, pokemon_name: str) -> None:
        """Entfernt ein Pokemon nach Namen."""
        name = pokemon_name.lower()
        for i, p in enumerate(self._members):
            if p.name == name:
                del self._members[i]
                return
        raise KeyError(f"Pokemon '{pokemon_name}' nicht im Team.")

    def __len__(self) -> int:
        return len(self._members)

    def __iter__(self) -> Iterator[Pokemon]:
        return iter(self._members)

    def __repr__(self) -> str:
        names = ", ".join(p.name.capitalize() for p in self._members)
        return f"Team({self._name!r}: {names or 'leer'})"
