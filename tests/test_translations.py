"""Tests für die deutschen Pokemon-Namen (Suche und Anzeige)."""

from __future__ import annotations

import unittest

from src.translations import display_name, matches_query, to_english, to_german


class TranslationTests(unittest.TestCase):

    def test_to_english_known_names(self):
        self.assertEqual(to_english("Glurak"), "charizard")
        self.assertEqual(to_english("glurak"), "charizard")   # case-insensitiv
        self.assertEqual(to_english("  Knakrack "), "garchomp")
        self.assertEqual(to_english("Bisasam"), "bulbasaur")

    def test_to_english_passthrough(self):
        # Englische oder unbekannte Namen kommen unverändert zurück.
        self.assertEqual(to_english("charizard"), "charizard")
        self.assertEqual(to_english("quatschname"), "quatschname")

    def test_to_german(self):
        self.assertEqual(to_german("charizard"), "Glurak")
        self.assertEqual(to_german("pikachu"), "Pikachu")
        self.assertIsNone(to_german("nicht-existent"))

    def test_display_name(self):
        self.assertEqual(display_name("charizard"), "Glurak")
        # Fallback: kapitalisierter englischer Name
        self.assertEqual(display_name("somefakemon"), "Somefakemon")

    def test_matches_query_german_and_english(self):
        self.assertTrue(matches_query("charizard", "glurak"))
        self.assertTrue(matches_query("charizard", "Glu"))
        self.assertTrue(matches_query("charizard", "char"))
        self.assertFalse(matches_query("charizard", "bisa"))
        self.assertTrue(matches_query("charizard", ""))  # leer = alles

    def test_full_coverage_of_dex(self):
        # Alle 1025 Pokemon haben einen deutschen Namen.
        from src.translations import _load
        _, _, id_to_de = _load()
        self.assertGreaterEqual(len(id_to_de), 1025)


if __name__ == "__main__":
    unittest.main()
