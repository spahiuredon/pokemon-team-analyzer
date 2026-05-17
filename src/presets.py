"""Vorgefertigte Champion-Teams aus mehreren Pokemon-Generationen.

Die Teams sind kuratiert aus den Hauptspielen - berühmte Trainer
und ihre Endgame-Teams. Wir referenzieren sie nur per Namen; die
echten Pokemon-Daten kommen über den API-Client (Cache oder Netz).

Dieses Modul ist bewusst nur Daten + eine kleine Lade-Funktion -
keine Logik, keine Klassen. So bleibt es einfach zu erweitern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .pokemon import Pokemon
from .team import Team

if TYPE_CHECKING:
    from .api_client import PokeAPIClient


# Jeder Eintrag: (Anzeige-Name, Liste der Pokemon-Namen).
# Reihenfolge entspricht ungefähr der Spielauswahl der Champions.
PRESET_TEAMS: dict[str, list[str]] = {
    "Gen 1 - Klassiker (Rot/Blau)": [
        "charizard", "blastoise", "venusaur",
        "pikachu", "snorlax", "dragonite",
    ],
    "Gen 1 - Champion Blue": [
        "pidgeot", "alakazam", "rhydon",
        "exeggutor", "gyarados", "arcanine",
    ],
    "Gen 3 - Champion Steven (Hoenn)": [
        "skarmory", "claydol", "aggron",
        "cradily", "armaldo", "metagross",
    ],
    "Gen 4 - Champion Cynthia (Sinnoh)": [
        "spiritomb", "roserade", "togekiss",
        "lucario", "milotic", "garchomp",
    ],
}


def available_presets() -> list[str]:
    """Liefert die Anzeige-Namen aller verfügbaren Presets (alphabetisch sortiert)."""
    return sorted(PRESET_TEAMS.keys())


def load_preset(name: str, client: "PokeAPIClient") -> Team:
    """Baut ein `Team` aus einem benannten Preset.

    Args:
        name: Anzeige-Name des Presets (Schlüssel aus PRESET_TEAMS).
        client: PokeAPIClient, der die Pokemon-Daten besorgt (Cache + Netz).

    Raises:
        KeyError: wenn `name` kein bekanntes Preset ist.
        ValueError / PokeAPIError: wenn ein Pokemon nicht ladbar ist.
    """
    if name not in PRESET_TEAMS:
        raise KeyError(f"Unbekanntes Preset: {name!r}")
    members: list[Pokemon] = []
    for pkmn_name in PRESET_TEAMS[name]:
        data = client.get_pokemon(pkmn_name)
        members.append(Pokemon.from_api(data))
    return Team(name=name, members=members)
