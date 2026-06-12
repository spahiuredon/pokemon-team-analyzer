"""Tests für den PokeAPI-Client.
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


class PruneCacheTests(unittest.TestCase):
    """Testet die Aufräum-Funktion in `data/fetch_all_pokemon.py`."""

    def test_prune_removes_only_unknown_entries(self):
        # Test-Cache mit einer Mischung aus erwünschten und
        # Form-Einträgen anlegen.
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from data.fetch_all_pokemon import _prune_cache  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for name in ("pikachu", "charizard", "deoxys-attack",
                         "venusaur-mega", "pikachu-libre"):
                (cache / f"pokemon_{name}.json").write_text("{}")
            # Index-Dateien dürfen NICHT entfernt werden.
            (cache / "index_species_2000.json").write_text("{}")

            valid = {"pikachu", "charizard"}
            removed = _prune_cache(cache, valid)

            self.assertEqual(removed, 3)
            remaining = sorted(p.name for p in cache.glob("*.json"))
            self.assertEqual(remaining, [
                "index_species_2000.json",
                "pokemon_charizard.json",
                "pokemon_pikachu.json",
            ])


class CacheClearingTests(unittest.TestCase):
    """clear_sprites() und clear_pokemon_cache()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.client = PokeAPIClient(cache_dir=base / "cache",
                                    sprite_dir=base / "sprites")

    def tearDown(self):
        self.tmp.cleanup()

    def test_clear_sprites_removes_only_pngs(self):
        (self.client.sprite_dir / "1.png").write_bytes(b"img")
        (self.client.sprite_dir / "2.png").write_bytes(b"img")
        (self.client.cache_dir / "pokemon_pikachu.json").write_text("{}")
        removed = self.client.clear_sprites()
        self.assertEqual(removed, 2)
        self.assertEqual(list(self.client.sprite_dir.glob("*.png")), [])
        # Daten-Cache bleibt unangetastet
        self.assertTrue((self.client.cache_dir / "pokemon_pikachu.json").exists())

    def test_clear_pokemon_cache_removes_jsons(self):
        (self.client.cache_dir / "pokemon_pikachu.json").write_text("{}")
        (self.client.cache_dir / "type_fire.json").write_text("{}")
        (self.client.sprite_dir / "1.png").write_bytes(b"img")
        removed = self.client.clear_pokemon_cache()
        self.assertEqual(removed, 2)
        self.assertEqual(list(self.client.cache_dir.glob("*.json")), [])
        # Sprites bleiben unangetastet
        self.assertTrue((self.client.sprite_dir / "1.png").exists())

    def test_clear_on_empty_dirs_returns_zero(self):
        self.assertEqual(self.client.clear_sprites(), 0)
        self.assertEqual(self.client.clear_pokemon_cache(), 0)


if __name__ == "__main__":
    unittest.main()
