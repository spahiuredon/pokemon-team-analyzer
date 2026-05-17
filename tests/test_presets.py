"""Tests für die vordefinierten Champion-Teams.

Diese Tests laufen offline - sie nutzen den lokalen Cache, der vom
`data/seed_cache.py`-Skript befüllt wird.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.api_client import PokeAPIClient
from src.presets import PRESET_TEAMS, available_presets, load_preset


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


class PresetsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = PokeAPIClient(cache_dir=CACHE_DIR)

    def test_at_least_three_presets_available(self):
        names = available_presets()
        self.assertGreaterEqual(len(names), 3,
                                "Mindestens drei Generationen-Presets erwartet")
        # alphabetisch sortiert?
        self.assertEqual(names, sorted(names))

    def test_every_preset_has_six_members(self):
        # Ein klassisches Pokemon-Team hat 6 Mitglieder.
        for name, members in PRESET_TEAMS.items():
            with self.subTest(preset=name):
                self.assertEqual(len(members), 6,
                                 f"{name} sollte 6 Pokemon haben")

    def test_load_preset_returns_team_with_correct_size(self):
        # Das erste Preset stellvertretend prüfen.
        any_preset = next(iter(PRESET_TEAMS.keys()))
        team = load_preset(any_preset, self.client)
        self.assertEqual(len(team), 6)
        # Team-Name sollte dem Preset entsprechen
        self.assertEqual(team.name, any_preset)

    def test_unknown_preset_raises(self):
        with self.assertRaises(KeyError):
            load_preset("Ash's Team", self.client)


if __name__ == "__main__":
    unittest.main()
