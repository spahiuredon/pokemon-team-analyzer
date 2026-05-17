"""Unit-Tests für die Pokemon-Klasse und ihre Vererbung."""

from __future__ import annotations

import unittest

from src.pokemon import MegaPokemon, Pokemon


def make_stats(hp=35, atk=55, df=40, sa=50, sd=50, sp=90) -> dict[str, int]:
    return {
        "hp": hp,
        "attack": atk,
        "defense": df,
        "special-attack": sa,
        "special-defense": sd,
        "speed": sp,
    }


class PokemonTests(unittest.TestCase):
    """Testet Konstruktor, Validierung, und das normale Verhalten."""

    def test_valid_pokemon_has_correct_total_stats(self):
        # Pikachu's "echte" Stats - Summe sollte 320 sein.
        pikachu = Pokemon(
            name="Pikachu",
            pokedex_id=25,
            types=["electric"],
            stats=make_stats(),
        )
        self.assertEqual(pikachu.total_stats(), 35 + 55 + 40 + 50 + 50 + 90)
        # Name wird normalisiert (klein)
        self.assertEqual(pikachu.name, "pikachu")
        # Typen kommen als Tuple zurück (immutable)
        self.assertEqual(pikachu.types, ("electric",))
        self.assertFalse(pikachu.is_dual_type())

    def test_constructor_rejects_invalid_input(self):
        # Leerer Name
        with self.assertRaises(ValueError):
            Pokemon(name="", pokedex_id=1, types=["normal"], stats=make_stats())
        # Falsche pokedex_id
        with self.assertRaises(ValueError):
            Pokemon(name="x", pokedex_id=-1, types=["normal"], stats=make_stats())
        # Drei Typen sind nicht erlaubt
        with self.assertRaises(ValueError):
            Pokemon(name="x", pokedex_id=1, types=["a", "b", "c"], stats=make_stats())
        # Negative Stats
        with self.assertRaises(ValueError):
            bad = make_stats()
            bad["hp"] = -10
            Pokemon(name="x", pokedex_id=1, types=["normal"], stats=bad)
        # Fehlende Stats
        with self.assertRaises(ValueError):
            Pokemon(name="x", pokedex_id=1, types=["normal"],
                    stats={"hp": 10})

    def test_stats_property_returns_copy(self):
        # Externe Mutation darf das Pokemon nicht ändern.
        p = Pokemon("a", 1, ["normal"], make_stats())
        s = p.stats
        s["hp"] = 999
        self.assertNotEqual(p.stats["hp"], 999)

    def test_from_api_parses_data(self):
        api_data = {
            "name": "bulbasaur",
            "id": 1,
            "types": [
                {"type": {"name": "grass"}},
                {"type": {"name": "poison"}},
            ],
            "stats": [
                {"stat": {"name": "hp"}, "base_stat": 45},
                {"stat": {"name": "attack"}, "base_stat": 49},
                {"stat": {"name": "defense"}, "base_stat": 49},
                {"stat": {"name": "special-attack"}, "base_stat": 65},
                {"stat": {"name": "special-defense"}, "base_stat": 65},
                {"stat": {"name": "speed"}, "base_stat": 45},
            ],
        }
        p = Pokemon.from_api(api_data)
        self.assertEqual(p.pokedex_id, 1)
        self.assertTrue(p.is_dual_type())
        self.assertEqual(p.types, ("grass", "poison"))
        self.assertEqual(p.total_stats(), 45 + 49 + 49 + 65 + 65 + 45)


class MegaPokemonTests(unittest.TestCase):
    """Testet, dass Vererbung das Verhalten korrekt erweitert."""

    def test_mega_pokemon_has_stat_boost(self):
        # Charizard total = 534; Mega-Charizard sollte +100 haben.
        stats = make_stats(78, 84, 78, 109, 85, 100)
        normal = Pokemon("charizard", 6, ["fire", "flying"], stats)
        mega = MegaPokemon("mega-charizard-x", 6, ["fire", "dragon"], stats,
                           base_form="charizard")
        self.assertEqual(normal.total_stats() + 100, mega.total_stats())
        # base_form ist nur bei MegaPokemon vorhanden
        self.assertEqual(mega.base_form, "charizard")

    def test_mega_pokemon_is_a_pokemon(self):
        mega = MegaPokemon("mega-x", 6, ["fire"], make_stats(),
                           base_form="charizard")
        # isinstance auf der Basisklasse muss True sein -> echte Vererbung
        self.assertIsInstance(mega, Pokemon)


if __name__ == "__main__":
    unittest.main()
