"""Tests für die Team-Auto-Vervollständigung."""

from __future__ import annotations

import random
import unittest

from src.pokemon import Pokemon
from src.team import Team
from src.team_completer import (
    GENERATION_RANGES,
    TeamCompleter,
    generation_of,
    is_special,
)


def make_pokemon(name: str, pid: int, types: list[str], total: int = 500) -> Pokemon:
    per = total // 6
    rest = total - per * 6
    stats = {
        "hp": per + rest, "attack": per, "defense": per,
        "special-attack": per, "special-defense": per, "speed": per,
    }
    return Pokemon(name=name, pokedex_id=pid, types=types, stats=stats)


class GenerationOfTests(unittest.TestCase):

    def test_known_generations(self):
        self.assertEqual(generation_of(25), 1)   # pikachu
        self.assertEqual(generation_of(151), 1)  # mew (Gen 1 Grenze)
        self.assertEqual(generation_of(152), 2)  # chikorita (Gen 2 Anfang)
        self.assertEqual(generation_of(445), 4)  # garchomp
        self.assertEqual(generation_of(700), 6)  # sylveon
        self.assertEqual(generation_of(1000), 9) # gholdengo

    def test_unknown_ids_return_zero(self):
        self.assertEqual(generation_of(0), 0)
        self.assertEqual(generation_of(99999), 0)

    def test_generation_ranges_are_contiguous(self):
        # Sanity-Check: keine Lücken in den Bereichen.
        prev_hi = 0
        for gen in sorted(GENERATION_RANGES):
            lo, hi = GENERATION_RANGES[gen]
            self.assertEqual(lo, prev_hi + 1,
                             f"Lücke vor Gen {gen}")
            prev_hi = hi


class TeamCompleterTests(unittest.TestCase):

    def setUp(self) -> None:
        # Ein Pool aus Pokemon verschiedener Generationen und Typen.
        self.pool = [
            # Gen 1
            make_pokemon("charizard", 6, ["fire", "flying"], 534),
            make_pokemon("blastoise", 9, ["water"], 530),
            make_pokemon("pikachu", 25, ["electric"], 320),
            make_pokemon("snorlax", 143, ["normal"], 540),
            # Gen 3
            make_pokemon("metagross", 376, ["steel", "psychic"], 600),
            make_pokemon("swampert", 260, ["water", "ground"], 535),
            # Gen 4
            make_pokemon("garchomp", 445, ["dragon", "ground"], 600),
            # Gen 5
            make_pokemon("hydreigon", 635, ["dark", "dragon"], 600),
            # Gen 6
            make_pokemon("sylveon", 700, ["fairy"], 525),
            # Gen 9
            make_pokemon("gholdengo", 1000, ["steel", "ghost"], 550),
        ]

    def test_completer_fills_empty_team_to_six(self):
        completer = TeamCompleter(self.pool)
        team = Team("Test")
        completer.complete(team)
        # Pool hat genug Pokemon -> auf 6 aufgefüllt
        self.assertEqual(len(team), 6)

    def test_completer_respects_existing_team(self):
        completer = TeamCompleter(self.pool)
        starter = self.pool[0]  # charizard
        team = Team("Test", [starter])
        completer.complete(team)
        # Charizard ist noch drin und das Team ist auf 6 voll
        self.assertEqual(len(team), 6)
        self.assertIn(starter, team.members)

    def test_generation_filter_excludes_newer_pokemon(self):
        completer = TeamCompleter(self.pool)
        team = Team("Test")
        completer.complete(team, max_generation=3)
        # Es dürfen nur Gen 1-3 Pokemon drin sein
        for p in team:
            gen = generation_of(p.pokedex_id)
            self.assertLessEqual(gen, 3,
                                 f"{p.name} ist Gen {gen}, sollte aber <= 3 sein")

    def test_completer_handles_pool_smaller_than_six(self):
        small_pool = self.pool[:2]
        completer = TeamCompleter(small_pool)
        team = Team("Test")
        completer.complete(team)
        # Mit nur 2 Kandidaten kann das Team nur auf 2 wachsen
        self.assertEqual(len(team), 2)

    def test_empty_pool_raises(self):
        with self.assertRaises(ValueError):
            TeamCompleter([])

    def test_score_components_are_finite(self):
        # Sanity-Check: Score darf nie NaN oder Inf werden.
        completer = TeamCompleter(self.pool)
        team = Team("T", [self.pool[0]])  # ein Pokemon drin
        for candidate in self.pool[1:]:
            s = completer.score(candidate, team)
            self.assertFalse(s != s, "Score ist NaN")  # NaN != NaN ist True
            self.assertTrue(0 <= s < 100, f"Score {s} ausserhalb erwarteter Range")


class SpecialPokemonTests(unittest.TestCase):
    """Legendäre/Mythische/Ultrabestien erkennen und filtern."""

    def test_is_special_known_ids(self):
        self.assertTrue(is_special(150))    # Mewtu
        self.assertTrue(is_special(151))    # Mew (mythisch)
        self.assertTrue(is_special(384))    # Rayquaza
        self.assertTrue(is_special(493))    # Arceus
        self.assertTrue(is_special(793))    # Anego (Ultrabestie)
        self.assertTrue(is_special(1007))   # Koraidon

    def test_is_special_normal_pokemon(self):
        for pid in (1, 25, 6, 445, 700, 1000):
            self.assertFalse(is_special(pid), f"#{pid} ist nicht legendär")

    def test_complete_excludes_legendaries_by_default(self):
        pool = [
            make_pokemon("mewtwo", 150, ["psychic"], 680),
            make_pokemon("rayquaza", 384, ["dragon", "flying"], 680),
            make_pokemon("charizard", 6, ["fire", "flying"], 534),
            make_pokemon("blastoise", 9, ["water"], 530),
            make_pokemon("venusaur", 3, ["grass", "poison"], 525),
        ]
        team = Team("Test")
        TeamCompleter(pool).complete(team)
        ids = {p.pokedex_id for p in team}
        self.assertNotIn(150, ids)
        self.assertNotIn(384, ids)
        self.assertEqual(len(team), 3)  # nur die drei normalen

    def test_allow_legendary_includes_them(self):
        pool = [
            make_pokemon("mewtwo", 150, ["psychic"], 680),
            make_pokemon("charizard", 6, ["fire", "flying"], 534),
        ]
        completer = TeamCompleter(pool)
        self.assertEqual(len(completer.candidates(allow_legendary=False)), 1)
        self.assertEqual(len(completer.candidates(allow_legendary=True)), 2)
        team = Team("Test")
        completer.complete(team, allow_legendary=True)
        self.assertEqual(len(team), 2)

    def test_mega_forms_are_filtered_from_pool(self):
        pool = [
            make_pokemon("charizard", 6, ["fire", "flying"], 534),
            make_pokemon("charizard-mega-x", 10034, ["fire", "dragon"], 634),
            make_pokemon("gengar-gmax", 10202, ["ghost", "poison"], 600),
        ]
        completer = TeamCompleter(pool)
        self.assertEqual(completer.pool_size, 1)

    def test_pool_with_only_megas_raises(self):
        with self.assertRaises(ValueError):
            TeamCompleter([make_pokemon("charizard-mega-x", 10034,
                                        ["fire", "dragon"], 634)])


class ScoringAndVarietyTests(unittest.TestCase):
    """Sweet-Spot-Scoring und Zufalls-Varianz."""

    def test_sweet_spot_beats_raw_power(self):
        # Bei leerem Team zählt praktisch nur der Stats-Score: ein
        # 510er-Pokemon muss besser abschneiden als ein 720er-Legendäres.
        pool = [
            make_pokemon("balanced", 100, ["water"], 510),
            make_pokemon("monster", 101, ["water"], 720),
        ]
        completer = TeamCompleter(pool)
        team = Team("leer")
        self.assertGreater(completer.score(pool[0], team),
                           completer.score(pool[1], team))

    def test_weak_pokemon_score_low(self):
        pool = [
            make_pokemon("caterpie", 10, ["bug"], 195),
            make_pokemon("butterfree", 12, ["bug", "flying"], 395),
        ]
        completer = TeamCompleter(pool)
        team = Team("leer")
        self.assertLess(completer.score(pool[0], team),
                        completer.score(pool[1], team))

    def test_variety_is_reproducible_with_seed(self):
        pool = [make_pokemon(f"mon{i}", i, ["normal"], 450 + i)
                for i in range(1, 30)]
        team_a = TeamCompleter(pool, rng=random.Random(42)).complete(Team("A"))
        team_b = TeamCompleter(pool, rng=random.Random(42)).complete(Team("B"))
        self.assertEqual([p.pokedex_id for p in team_a],
                         [p.pokedex_id for p in team_b])

    def test_variety_false_is_deterministic_greedy(self):
        pool = [make_pokemon(f"mon{i}", i, ["normal"], 400 + i * 10)
                for i in range(1, 15)]
        team_a = TeamCompleter(pool).complete(Team("A"), variety=False)
        team_b = TeamCompleter(pool).complete(Team("B"), variety=False)
        self.assertEqual({p.pokedex_id for p in team_a},
                         {p.pokedex_id for p in team_b})


if __name__ == "__main__":
    unittest.main()
