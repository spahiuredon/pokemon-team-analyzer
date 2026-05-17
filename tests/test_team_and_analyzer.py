"""Unit-Tests für Team und TeamAnalyzer (inklusive Pandas-Pipeline)."""

from __future__ import annotations

import unittest

import pandas as pd

from src.analyzer import TeamAnalyzer
from src.pokemon import Pokemon
from src.team import Team


def make_pokemon(name: str, pid: int, types: list[str], total: int = 300) -> Pokemon:
    per = total // 6
    rest = total - per * 6
    stats = {
        "hp": per + rest,
        "attack": per,
        "defense": per,
        "special-attack": per,
        "special-defense": per,
        "speed": per,
    }
    return Pokemon(name=name, pokedex_id=pid, types=types, stats=stats)


class TeamTests(unittest.TestCase):

    def test_team_basic_operations(self):
        team = Team("Reds Team")
        self.assertEqual(len(team), 0)
        p = make_pokemon("pikachu", 25, ["electric"])
        team.add(p)
        self.assertEqual(len(team), 1)
        self.assertIn(p, team.members)

    def test_team_rejects_duplicates_and_overflow(self):
        team = Team("T")
        team.add(make_pokemon("a", 1, ["fire"]))
        # Gleiche pokedex_id -> Duplikat (__eq__ basiert auf der ID)
        with self.assertRaises(ValueError):
            team.add(make_pokemon("a-again", 1, ["fire"]))
        # Maximalgröße 6
        for i in range(2, 7):
            team.add(make_pokemon(f"p{i}", i, ["normal"]))
        self.assertEqual(len(team), 6)
        with self.assertRaises(ValueError):
            team.add(make_pokemon("seventh", 99, ["normal"]))

    def test_team_remove(self):
        team = Team("T", [make_pokemon("a", 1, ["fire"]),
                          make_pokemon("b", 2, ["water"])])
        team.remove("a")
        self.assertEqual(len(team), 1)
        with self.assertRaises(KeyError):
            team.remove("not-here")


class AnalyzerTests(unittest.TestCase):

    def setUp(self) -> None:
        self.team = Team("Analyse-Team", [
            make_pokemon("charizard", 6, ["fire", "flying"], total=534),
            make_pokemon("blastoise", 9, ["water"], total=530),
            make_pokemon("venusaur", 3, ["grass", "poison"], total=525),
        ])
        self.analyzer = TeamAnalyzer(self.team)

    def test_stats_dataframe_shape(self):
        df = self.analyzer.to_stats_dataframe()
        self.assertIsInstance(df, pd.DataFrame)
        # 3 Pokemon, alle 6 Stats + types + pokedex_id + total
        self.assertEqual(len(df), 3)
        self.assertIn("total", df.columns)
        self.assertIn("hp", df.columns)
        # Total muss zur Konstruktion (~530) passen (+/- Rundungen, siehe make_pokemon)
        self.assertTrue((df["total"] >= 520).all())

    def test_type_coverage_counts_correctly(self):
        cov = self.analyzer.type_coverage()
        # Alle 18 Typen müssen Zeilen haben.
        self.assertEqual(len(cov), 18)
        # Summe weak+neutral+resists+immune muss immer der Teamgröße entsprechen,
        # weil jedes Mitglied genau einer Kategorie zugeordnet wird.
        team_size = len(self.team)
        sums = cov[["weak", "neutral", "resists", "immune"]].sum(axis=1)
        self.assertTrue((sums == team_size).all())

    def test_biggest_weakness_includes_rock(self):
        # Charizard ist 4x schwach gegen Rock -> Rock sollte unter den Top-5
        # Schwächen sein.
        top_weak = self.analyzer.biggest_weaknesses(top_n=5)
        self.assertIn("rock", top_weak.index)

    def test_empty_team_rejected(self):
        with self.assertRaises(ValueError):
            TeamAnalyzer(Team("leer"))


if __name__ == "__main__":
    unittest.main()
