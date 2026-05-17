"""Tests für die Team-Auto-Vervollständigung."""

from __future__ import annotations

import unittest

from src.pokemon import Pokemon
from src.team import Team
from src.team_completer import (
    GENERATION_RANGES,
    TeamCompleter,
    generation_of,
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


if __name__ == "__main__":
    unittest.main()
