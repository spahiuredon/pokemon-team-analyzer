"""Tests für den PokeAPI-Client - ohne echte Netzwerkaufrufe.

Wir patchen `urllib.request.urlopen`, damit die Tests deterministisch sind
und auch ohne Internet laufen.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api_client import PokeAPIClient, PokeAPIError


class FakeResponse:
    def __init__(self, data: dict, status: int = 200):
        self.status = status
        self._payload = json.dumps(data).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PokeAPIClientTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = PokeAPIClient(cache_dir=self.tmp.name)

    def test_get_pokemon_parses_and_caches(self):
        api_data = {
            "name": "pikachu",
            "id": 25,
            "types": [{"type": {"name": "electric"}}],
            "stats": [
                {"stat": {"name": "hp"}, "base_stat": 35},
                {"stat": {"name": "attack"}, "base_stat": 55},
                {"stat": {"name": "defense"}, "base_stat": 40},
                {"stat": {"name": "special-attack"}, "base_stat": 50},
                {"stat": {"name": "special-defense"}, "base_stat": 50},
                {"stat": {"name": "speed"}, "base_stat": 90},
            ],
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(api_data)) as mock_open:
            data = self.client.get_pokemon("pikachu")
            self.assertEqual(data["name"], "pikachu")
            # Cache-Datei wurde geschrieben
            self.assertTrue((Path(self.tmp.name) / "pokemon_pikachu.json").exists())
            # Zweiter Aufruf darf KEIN HTTP-Request mehr machen
            data2 = self.client.get_pokemon("pikachu")
            self.assertEqual(data2["name"], "pikachu")
            self.assertEqual(mock_open.call_count, 1, "Cache wurde nicht genutzt")

    def test_empty_name_raises(self):
        with self.assertRaises(PokeAPIError):
            self.client.get_pokemon("")

    def test_incomplete_response_raises(self):
        # Wenn die API ein Dict ohne 'stats' zurückgibt, soll validiert werden.
        bad = {"name": "x", "id": 1, "types": []}  # 'stats' fehlt
        with patch("urllib.request.urlopen", return_value=FakeResponse(bad)):
            with self.assertRaises(PokeAPIError):
                self.client.get_pokemon("ghost-pokemon")


if __name__ == "__main__":
    unittest.main()
