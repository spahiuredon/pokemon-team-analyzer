"""Pokemon Team Analyzer - Hauptpaket.

Dieses Paket enthält die Module für den Pokemon Team-Analyzer:
- api_client: Zugriff auf die PokeAPI
- pokemon: Pokemon-Klassen mit Vererbung
- type_chart: Typ-Effektivität (18 Typen)
- team: Team-Klasse zum Verwalten mehrerer Pokemon
- analyzer: Analyse von Team-Stats und Typ-Coverage mit Pandas
"""

from .pokemon import Pokemon, MegaPokemon
from .type_chart import TypeChart
from .team import Team
from .api_client import PokeAPIClient
from .analyzer import TeamAnalyzer
from .presets import PRESET_TEAMS, available_presets, load_preset
from .team_completer import GENERATION_RANGES, TeamCompleter, generation_of

__all__ = [
    "Pokemon",
    "MegaPokemon",
    "TypeChart",
    "Team",
    "PokeAPIClient",
    "TeamAnalyzer",
    "PRESET_TEAMS",
    "available_presets",
    "load_preset",
    "TeamCompleter",
    "generation_of",
    "GENERATION_RANGES",
]
