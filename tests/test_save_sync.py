"""Tests für die Save-Sync-Engine (ohne echte FTP-Verbindung).

Die Engine arbeitet nur mit der SaveSource-Abstraktion, daher lassen
sich Konfliktlogik, Backups und Hash-Vergleich komplett offline testen.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.save_sync import (
    GAMES,
    GAMES_BY_KEY,
    GameSyncConfig,
    SaveSource,
    SyncConfig,
    SyncEngine,
    cloud_source,
    file_source,
)


def make_source(name: str, data: bytes | None, mtime: float | None):
    """Baut eine In-Memory-Quelle für Tests. Schreibvorgänge landen in
    ``store['data']``."""
    store = {"data": data, "mtime": mtime, "writes": 0}

    def read():
        return store["data"]

    def write(new: bytes):
        store["data"] = new
        store["writes"] += 1

    def get_mtime():
        return store["mtime"]

    return SaveSource(name=name, read=read, write=write,
                      get_mtime=get_mtime), store


class TestRegistry(unittest.TestCase):
    def test_all_games_present(self):
        keys = {g.key for g in GAMES}
        # Platin bis Ultra Sonne/Mond = 15 Spiele
        self.assertEqual(len(GAMES), 15)
        self.assertIn("platinum", keys)
        self.assertIn("ultra-sun", keys)
        self.assertIn("ultra-moon", keys)

    def test_platforms(self):
        self.assertEqual(GAMES_BY_KEY["platinum"].platform, "nds")
        self.assertEqual(GAMES_BY_KEY["ultra-sun"].platform, "3ds")

    def test_checkpoint_hex(self):
        # Title-ID-Low >> 8, fünfstellig hex: Ultra Sonne = 0x01B50
        self.assertEqual(GAMES_BY_KEY["ultra-sun"].checkpoint_hex, "0x01B50")
        self.assertEqual(GAMES_BY_KEY["sun"].checkpoint_hex, "0x01648")
        # NDS-Spiele haben keine Title-ID
        self.assertEqual(GAMES_BY_KEY["platinum"].checkpoint_hex, "")


class TestSyncEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = SyncEngine(backup_dir=Path(self.tmp.name))
        self.game = GAMES_BY_KEY["platinum"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_identical_content_skips(self):
        a, store_a = make_source("PC", b"same", 100.0)
        b, store_b = make_source("3DS", b"same", 200.0)
        result = self.engine.sync(self.game, [a, b])
        self.assertTrue(result.skipped)
        self.assertEqual(store_a["writes"], 0)
        self.assertEqual(store_b["writes"], 0)

    def test_newer_wins(self):
        a, store_a = make_source("PC", b"old", 100.0)
        b, store_b = make_source("3DS", b"new", 200.0)
        result = self.engine.sync(self.game, [a, b])
        self.assertEqual(result.winner, "3DS")
        self.assertEqual(store_a["data"], b"new")
        self.assertEqual(store_b["writes"], 0)
        self.assertIn("PC", result.updated)

    def test_loser_gets_backed_up(self):
        a, _ = make_source("PC", b"old", 100.0)
        b, _ = make_source("3DS", b"new", 200.0)
        result = self.engine.sync(self.game, [a, b])
        self.assertIn("PC", result.backed_up)
        backups = list(Path(self.tmp.name).glob("platinum/*_PC.sav"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old")

    def test_missing_source_gets_populated_without_backup(self):
        a, store_a = make_source("PC", None, None)
        b, _ = make_source("3DS", b"data", 200.0)
        result = self.engine.sync(self.game, [a, b])
        self.assertEqual(store_a["data"], b"data")
        self.assertNotIn("PC", result.backed_up)  # nichts zu sichern
        self.assertIn("PC", result.updated)

    def test_all_empty(self):
        a, _ = make_source("PC", None, None)
        b, _ = make_source("3DS", None, None)
        result = self.engine.sync(self.game, [a, b])
        self.assertTrue(result.skipped)

    def test_force_winner_overrides_mtime(self):
        # PC ist älter, soll aber gewinnen (Modus "Nur PC -> 3DS").
        a, _ = make_source("PC", b"pc-data", 100.0)
        b, store_b = make_source("3DS", b"ds-data", 200.0)
        result = self.engine.sync(self.game, [a, b], force_winner="PC")
        self.assertEqual(result.winner, "PC")
        self.assertEqual(store_b["data"], b"pc-data")

    def test_force_winner_missing(self):
        a, _ = make_source("PC", None, None)
        b, store_b = make_source("3DS", b"ds-data", 200.0)
        result = self.engine.sync(self.game, [a, b], force_winner="PC")
        self.assertTrue(result.skipped)
        self.assertEqual(store_b["writes"], 0)

    def test_three_sources_cloud(self):
        a, store_a = make_source("PC", b"v1", 100.0)
        b, store_b = make_source("3DS", b"v2", 300.0)
        c, store_c = make_source("Cloud", b"v1", 50.0)
        result = self.engine.sync(self.game, [a, b, c])
        self.assertEqual(result.winner, "3DS")
        self.assertEqual(store_a["data"], b"v2")
        self.assertEqual(store_c["data"], b"v2")
        self.assertEqual(store_b["writes"], 0)

    def test_size_warning(self):
        game = GAMES_BY_KEY["ultra-sun"]  # erwartet 441856 Bytes
        a, _ = make_source("PC", b"tiny", 100.0)
        b, _ = make_source("3DS", b"tiny2", 200.0)
        result = self.engine.sync(game, [a, b])
        self.assertTrue(any("unerwartete Grösse" in m for m in result.messages))


class TestFileSources(unittest.TestCase):
    def test_file_source_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "save.sav"
            src = file_source("PC", path)
            self.assertIsNone(src.read())
            self.assertIsNone(src.get_mtime())
            src.write(b"hello")  # legt Ordner an
            self.assertEqual(src.read(), b"hello")
            self.assertIsNotNone(src.get_mtime())

    def test_cloud_source_path_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = GAMES_BY_KEY["platinum"]
            src = cloud_source(game, Path(tmp))
            src.write(b"x")
            expected = Path(tmp) / "pokemon_saves" / "platinum.sav"
            self.assertTrue(expected.exists())


class TestConfig(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SyncConfig(ftp_host="192.168.1.50", ftp_port=5000,
                             cloud_dir="/tmp/drive")
            cfg.games["platinum"] = GameSyncConfig(
                local_path="/saves/platin.sav",
                remote_path="/roms/nds/saves/platin.sav")
            cfg.save(Path(tmp))
            loaded = SyncConfig.load(Path(tmp))
            self.assertEqual(loaded.ftp_host, "192.168.1.50")
            self.assertEqual(loaded.cloud_dir, "/tmp/drive")
            self.assertEqual(loaded.games["platinum"].local_path,
                             "/saves/platin.sav")

    def test_load_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SyncConfig.load(Path(tmp))
            self.assertEqual(cfg.ftp_host, "")
            self.assertEqual(cfg.ftp_port, 5000)

    def test_game_creates_entry(self):
        cfg = SyncConfig()
        g = cfg.game("platinum")
        self.assertIsInstance(g, GameSyncConfig)
        self.assertIs(cfg.game("platinum"), g)


if __name__ == "__main__":
    unittest.main()
