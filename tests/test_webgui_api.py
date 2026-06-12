"""Tests für die Web-GUI-API (ohne pywebview, ohne Netzwerk)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api_client import PokeAPIClient
from src.webgui_api import Api


def fake_pokemon_json(name: str, pid: int, types: list[str],
                      total: int = 480) -> dict:
    per = total // 6
    rest = total - per * 6
    stat_names = ["hp", "attack", "defense", "special-attack",
                  "special-defense", "speed"]
    return {
        "name": name, "id": pid,
        "types": [{"type": {"name": t}} for t in types],
        "stats": [{"stat": {"name": s},
                   "base_stat": per + (rest if s == "hp" else 0)}
                  for s in stat_names],
        "sprites": {"front_default": None},
    }


class ApiTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        # Api bauen, dann den Client auf temporäre Verzeichnisse umbiegen.
        with patch.object(Api, "__init__", lambda s: None):
            self.api = Api()
        self.api.client = PokeAPIClient(cache_dir=base / "cache",
                                        sprite_dir=base / "sprites")
        from src.team import Team
        from src.save_sync import SyncConfig
        self.api.team = Team("Test")
        self.api.sync_config = SyncConfig()
        self.api._download_state = {"running": False}
        self.api._sync_log = []
        import threading
        self.api._lock = threading.Lock()
        # Cache befüllen
        for name, pid, types in [("charizard", 6, ["fire", "flying"]),
                                 ("blastoise", 9, ["water"]),
                                 ("venusaur", 3, ["grass", "poison"])]:
            (self.api.client.cache_dir / f"pokemon_{name}.json").write_text(
                json.dumps(fake_pokemon_json(name, pid, types)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_finds_german_names(self):
        res = self.api.search_pokemon("glurak")
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["items"][0]["name"], "charizard")
        self.assertEqual(res["items"][0]["display"], "Glurak")

    def test_search_empty_query_lists_all(self):
        res = self.api.search_pokemon("")
        self.assertEqual(res["total"], 3)

    def test_add_remove_team(self):
        res = self.api.add_pokemon("Glurak")  # deutscher Name
        self.assertTrue(res["ok"])
        self.assertEqual(res["added"], "Glurak")
        self.assertEqual(len(self.api.get_team()), 1)
        res = self.api.remove_pokemon("charizard")
        self.assertTrue(res["ok"])
        self.assertEqual(len(self.api.get_team()), 0)

    def test_add_unknown_returns_error(self):
        res = self.api.add_pokemon("gibtsnicht")
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_clear_team(self):
        self.api.add_pokemon("charizard")
        res = self.api.clear_team()
        self.assertTrue(res["ok"])
        self.assertEqual(self.api.get_team(), [])

    def test_analysis_empty_and_filled(self):
        self.assertTrue(self.api.get_analysis()["empty"])
        self.api.add_pokemon("charizard")
        self.api.add_pokemon("blastoise")
        a = self.api.get_analysis()
        self.assertFalse(a["empty"])
        self.assertEqual(a["team_size"], 2)
        self.assertEqual(len(a["table"]), 2)
        self.assertEqual(len(a["coverage_matrix"]), 2)
        self.assertIn("mults", a["coverage_matrix"][0])
        # 18 Angriffstypen pro Mitglied
        self.assertEqual(len(a["coverage_matrix"][0]["mults"]), 18)

    def test_auto_complete_uses_cache_pool(self):
        res = self.api.auto_complete("all", 0, False)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["team"]), 3)  # nur 3 im Cache

    def test_auto_complete_full_team_errors(self):
        for i in range(6):
            (self.api.client.cache_dir / f"pokemon_mon{i}.json").write_text(
                json.dumps(fake_pokemon_json(f"mon{i}", 100 + i, ["normal"])))
        self.api.auto_complete("all", 0, False)
        res = self.api.auto_complete("all", 0, False)
        self.assertFalse(res["ok"])

    def test_sync_config_roundtrip(self):
        res = self.api.save_sync_settings("192.168.1.7", 5000, "")
        self.assertTrue(res["ok"])
        cfg = self.api.get_sync_config()
        self.assertEqual(cfg["host"], "192.168.1.7")
        self.assertEqual(len(cfg["games"]), 15)

    def test_save_game_paths(self):
        res = self.api.save_game_paths("platinum", "/a.sav", "/b.sav")
        self.assertTrue(res["ok"])
        cfg = self.api.get_sync_config()
        plat = next(g for g in cfg["games"] if g["key"] == "platinum")
        self.assertEqual(plat["local_path"], "/a.sav")
        self.assertEqual(plat["remote_path"], "/b.sav")

    def test_save_game_paths_unknown_game(self):
        res = self.api.save_game_paths("zelda", "", "")
        self.assertFalse(res["ok"])

    def test_test_connection_without_host(self):
        res = self.api.test_connection()
        self.assertFalse(res["ok"])

    def test_clear_cache_endpoints(self):
        (self.api.client.sprite_dir / "1.png").write_bytes(b"x")
        res = self.api.clear_sprites()
        self.assertEqual(res["removed"], 1)
        res = self.api.clear_all_cache()
        self.assertEqual(res["data"], 3)  # die drei Pokemon-JSONs


if __name__ == "__main__":
    unittest.main()
