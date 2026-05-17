"""Unit-Tests für die TypeChart-Effektivitätsberechnung."""

from __future__ import annotations

import unittest

from src.type_chart import TypeChart


class TypeChartTests(unittest.TestCase):

    def setUp(self) -> None:
        self.chart = TypeChart()

    def test_super_effective_against_single_type(self):
        # Wasser ist sehr effektiv gegen Feuer (x2.0)
        self.assertEqual(self.chart.effectiveness("water", ["fire"]), 2.0)
        # Feuer ist sehr effektiv gegen Pflanze (x2.0)
        self.assertEqual(self.chart.effectiveness("fire", ["grass"]), 2.0)

    def test_not_very_effective_and_immune(self):
        # Elektro gegen Boden -> immun (x0.0)
        self.assertEqual(self.chart.effectiveness("electric", ["ground"]), 0.0)
        # Wasser gegen Wasser -> nicht sehr effektiv (x0.5)
        self.assertEqual(self.chart.effectiveness("water", ["water"]), 0.5)

    def test_dual_type_multiplier(self):
        # Eis gegen Drache/Flug (z.B. Dragonite) -> 2.0 * 2.0 = 4.0
        self.assertEqual(self.chart.effectiveness("ice", ["dragon", "flying"]), 4.0)
        # Feuer gegen Pflanze/Stahl -> 2.0 * 2.0 = 4.0
        self.assertEqual(self.chart.effectiveness("fire", ["grass", "steel"]), 4.0)
        # Wasser gegen Pflanze/Drache -> 0.5 * 0.5 = 0.25
        self.assertEqual(self.chart.effectiveness("water", ["grass", "dragon"]), 0.25)

    def test_invalid_types_raise(self):
        with self.assertRaises(ValueError):
            self.chart.effectiveness("laser", ["fire"])
        with self.assertRaises(ValueError):
            self.chart.effectiveness("fire", ["light"])
        with self.assertRaises(ValueError):
            self.chart.effectiveness("fire", [])

    def test_weaknesses_only_lists_super_effective(self):
        # Charizard ist Feuer/Flug -> klassisch 4x schwach gegen Rock.
        weaknesses = self.chart.weaknesses_of(["fire", "flying"])
        self.assertIn("rock", weaknesses)
        self.assertEqual(weaknesses["rock"], 4.0)
        # Alle Werte sollten > 1.0 sein
        for atk, mult in weaknesses.items():
            self.assertGreater(mult, 1.0, f"{atk} sollte super-effektiv sein")


if __name__ == "__main__":
    unittest.main()
