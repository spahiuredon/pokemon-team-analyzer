"""Python-API für das Web-GUI (pywebview).

Diese Klasse wird pywebview als ``js_api`` übergeben - jede öffentliche
Methode ist aus JavaScript via ``window.pywebview.api.<methode>(...)``
aufrufbar und liefert JSON-taugliche Dicts/Listen zurück.

Die Klasse ist bewusst frei von pywebview-Importen, damit sie ohne
GUI-Umgebung getestet werden kann.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Any

from .analyzer import TeamAnalyzer
from .api_client import PokeAPIClient, PokeAPIError
from .app_paths import data_dir
from .pokemon import Pokemon
from .presets import available_presets, load_preset
from .save_sync import (
    GAMES,
    GAMES_BY_KEY,
    FTPError,
    SyncConfig,
    ThreeDSFTP,
    find_azahar_save,
    sync_game,
)
from .team import Team
from .team_completer import GENERATION_RANGES, TeamCompleter
from .translations import display_name, matches_query, to_english
from .type_chart import ALL_TYPES, TypeChart

ARTWORK_URL = ("https://raw.githubusercontent.com/PokeAPI/sprites/master/"
               "sprites/pokemon/other/official-artwork/{id}.png")


def _b64_image(path: Path) -> str | None:
    try:
        return ("data:image/png;base64,"
                + base64.b64encode(path.read_bytes()).decode("ascii"))
    except OSError:
        return None


class Api:
    """Backend-API für das Web-Frontend."""

    def __init__(self) -> None:
        self.client = PokeAPIClient(cache_dir=data_dir() / "cache",
                                    sprite_dir=data_dir() / "sprites")
        self.team = Team("Mein Team")
        self.sync_config = SyncConfig.load()
        # Fortschritt des Bulk-Downloads (von JS gepollt).
        self._download_state: dict[str, Any] = {"running": False}
        self._sync_log: list[str] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Pokemon-Liste & Suche
    # ------------------------------------------------------------------ #
    def _cached_names(self) -> list[str]:
        return sorted(
            f.stem.removeprefix("pokemon_")
            for f in self.client.cache_dir.glob("pokemon_*.json")
        )

    def _pokemon_brief(self, pokemon: Pokemon) -> dict[str, Any]:
        return {
            "name": pokemon.name,
            "display": display_name(pokemon.name),
            "id": pokemon.pokedex_id,
            "types": list(pokemon.types),
            "total": pokemon.total_stats(),
            "stats": pokemon.stats,
        }

    def search_pokemon(self, query: str = "", limit: int = 60) -> dict[str, Any]:
        """Liste für die Sidebar - matcht deutsche und englische Namen."""
        names = self._cached_names()
        if query:
            names = [n for n in names if matches_query(n, query)]
        total = len(names)
        items = []
        for name in names[:limit]:
            try:
                pokemon = Pokemon.from_api(self.client.get_pokemon(name))
            except (PokeAPIError, ValueError):
                continue
            entry = self._pokemon_brief(pokemon)
            sprite = self.client.get_sprite(pokemon.pokedex_id,
                                            pokemon.sprite_url,
                                            allow_download=False)
            entry["sprite"] = _b64_image(sprite) if sprite else None
            items.append(entry)
        return {"total": total, "items": items}

    def get_artwork(self, pokedex_id: int) -> str | None:
        """Offizielles Artwork (gross, hübsch) als Data-URL.

        Wird lokal als art_<id>.png gecached; Download nur bei Bedarf.
        """
        path = self.client.sprite_dir / f"art_{pokedex_id}.png"
        if not path.exists():
            try:
                raw = self.client._http_get_with_retries(
                    ARTWORK_URL.format(id=pokedex_id))
                path.write_bytes(raw)
            except (PokeAPIError, OSError):
                # Fallback: normaler Pixel-Sprite
                sprite = self.client.get_sprite(pokedex_id, None,
                                                allow_download=True)
                return _b64_image(sprite) if sprite else None
        return _b64_image(path)

    # ------------------------------------------------------------------ #
    # Team-Operationen
    # ------------------------------------------------------------------ #
    def get_team(self) -> list[dict[str, Any]]:
        return [self._pokemon_brief(p) for p in self.team.members]

    def add_pokemon(self, name: str) -> dict[str, Any]:
        try:
            pokemon = Pokemon.from_api(
                self.client.get_pokemon(to_english(name)))
            self.team.add(pokemon)
        except (PokeAPIError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "team": self.get_team(),
                "added": display_name(pokemon.name)}

    def remove_pokemon(self, name: str) -> dict[str, Any]:
        try:
            self.team.remove(name)
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "team": self.get_team()}

    def clear_team(self) -> dict[str, Any]:
        self.team = Team(self.team.name)
        return {"ok": True, "team": []}

    def list_presets(self) -> list[str]:
        return available_presets()

    def load_preset_team(self, name: str) -> dict[str, Any]:
        try:
            self.team = load_preset(name, self.client)
        except (PokeAPIError, ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "team": self.get_team()}

    def generation_options(self) -> list[int]:
        return sorted(GENERATION_RANGES)

    def auto_complete(self, gen_mode: str = "all", gen: int = 0,
                      allow_legendary: bool = False) -> dict[str, Any]:
        """Füllt das Team auf. gen_mode: 'all' | 'max' | 'exact'."""
        if len(self.team) >= Team.MAX_SIZE:
            return {"ok": False,
                    "error": "Team ist schon voll - erst Platz schaffen."}
        pool: list[Pokemon] = []
        for name in self._cached_names():
            try:
                pool.append(Pokemon.from_api(self.client.get_pokemon(name)))
            except (PokeAPIError, ValueError):
                continue
        if not pool:
            return {"ok": False, "error": "Kein Pokemon im Cache - zuerst "
                                          "'Alle Pokemon laden' ausführen."}
        max_gen = int(gen) if gen_mode == "max" else None
        exact_gen = int(gen) if gen_mode == "exact" else None
        try:
            TeamCompleter(pool).complete(
                self.team, max_generation=max_gen,
                exact_generation=exact_gen,
                allow_legendary=bool(allow_legendary))
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "team": self.get_team()}

    # ------------------------------------------------------------------ #
    # Analyse (JSON statt matplotlib - das Frontend zeichnet selbst)
    # ------------------------------------------------------------------ #
    def get_analysis(self) -> dict[str, Any]:
        if len(self.team) == 0:
            return {"empty": True}
        analyzer = TeamAnalyzer(self.team)
        df = analyzer.to_stats_dataframe().reset_index()
        coverage = analyzer.type_coverage().reset_index()
        weaknesses = [
            {"type": t, "count": int(c)}
            for t, c in analyzer.biggest_weaknesses(top_n=18).items()
            if c > 0
        ]
        summary = analyzer.summary()
        members = [self._pokemon_brief(p) for p in self.team.members]
        # Heatmap-Daten: pro Mitglied der Schadensmultiplikator je Angriffstyp.
        chart = TypeChart()
        matrix = []
        for p in self.team.members:
            matrix.append({
                "display": display_name(p.name),
                "mults": {atk: chart.effectiveness(atk, p.types)
                          for atk in ALL_TYPES},
            })
        return {
            "empty": False,
            "members": members,
            "table": df.to_dict(orient="records"),
            "coverage": coverage.to_dict(orient="records"),
            "coverage_matrix": matrix,
            "weaknesses": weaknesses,
            "avg_total": round(float(summary.loc["mean", "total"]), 1),
            "team_size": len(self.team),
        }

    # ------------------------------------------------------------------ #
    # Bulk-Download (Thread + Poll)
    # ------------------------------------------------------------------ #
    def start_bulk_download(self) -> dict[str, Any]:
        with self._lock:
            if self._download_state.get("running"):
                return {"ok": False, "error": "Download läuft bereits."}
            self._download_state = {"running": True, "done": 0,
                                    "total": 0, "name": ""}

        def worker() -> None:
            try:
                from data.fetch_all_pokemon import bulk_fetch

                def progress(done: int, total: int, name: str) -> None:
                    self._download_state.update(
                        done=done, total=total, name=name)

                success, total, _pruned = bulk_fetch(workers=16, prune=True,
                                                     progress=progress)
                self._download_state.update(
                    running=False, finished=True,
                    success=success, total=total)
            except Exception as exc:
                self._download_state.update(
                    running=False, finished=True, error=str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def get_download_progress(self) -> dict[str, Any]:
        return dict(self._download_state)

    # ------------------------------------------------------------------ #
    # Cache-Verwaltung
    # ------------------------------------------------------------------ #
    def clear_sprites(self) -> dict[str, Any]:
        removed = self.client.clear_sprites()
        return {"ok": True, "removed": removed}

    def clear_all_cache(self) -> dict[str, Any]:
        sprites = self.client.clear_sprites()
        data = self.client.clear_pokemon_cache()
        return {"ok": True, "sprites": sprites, "data": data}

    # ------------------------------------------------------------------ #
    # 3DS-Sync
    # ------------------------------------------------------------------ #
    def get_sync_config(self) -> dict[str, Any]:
        cfg = self.sync_config
        games = []
        for g in GAMES:
            game_cfg = cfg.games.get(g.key)
            local = (game_cfg.local_path if game_cfg else "") or ""
            if not local and g.platform == "3ds":
                auto = find_azahar_save(g)
                if auto:
                    local = f"(auto) {auto}"
            games.append({
                "key": g.key, "title": g.title, "platform": g.platform,
                "generation": g.generation,
                "local_path": local,
                "remote_path": (game_cfg.remote_path if game_cfg else "") or "",
            })
        return {"host": cfg.ftp_host, "port": cfg.ftp_port,
                "cloud_dir": cfg.cloud_dir, "games": games}

    def save_sync_settings(self, host: str, port: int,
                           cloud_dir: str) -> dict[str, Any]:
        self.sync_config.ftp_host = (host or "").strip()
        try:
            self.sync_config.ftp_port = int(port or 5000)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Port muss eine Zahl sein."}
        self.sync_config.cloud_dir = (cloud_dir or "").strip()
        self.sync_config.save()
        return {"ok": True}

    def save_game_paths(self, key: str, local_path: str,
                        remote_path: str) -> dict[str, Any]:
        if key not in GAMES_BY_KEY:
            return {"ok": False, "error": f"Unbekanntes Spiel: {key}"}
        game_cfg = self.sync_config.game(key)
        game_cfg.local_path = (local_path or "").strip()
        game_cfg.remote_path = (remote_path or "").strip()
        self.sync_config.save()
        return {"ok": True}

    def detect_azahar_save(self, key: str) -> dict[str, Any]:
        game = GAMES_BY_KEY.get(key)
        if game is None:
            return {"ok": False, "error": "Unbekanntes Spiel."}
        found = find_azahar_save(game)
        if found is None:
            return {"ok": False,
                    "error": "Kein Azahar/Citra-Save gefunden. Spiel im "
                             "Emulator einmal starten und speichern."}
        return {"ok": True, "path": str(found)}

    def test_connection(self) -> dict[str, Any]:
        cfg = self.sync_config
        if not cfg.ftp_host:
            return {"ok": False, "error": "Bitte zuerst die 3DS-IP eintragen."}
        try:
            with ThreeDSFTP(cfg.ftp_host, cfg.ftp_port,
                            cfg.ftp_user, cfg.ftp_password):
                return {"ok": True}
        except FTPError as exc:
            return {"ok": False, "error": str(exc)}

    def ftp_list(self, path: str = "/") -> dict[str, Any]:
        cfg = self.sync_config
        try:
            with ThreeDSFTP(cfg.ftp_host, cfg.ftp_port,
                            cfg.ftp_user, cfg.ftp_password) as ftp:
                entries = [{"name": n, "dir": d}
                           for n, d in ftp.list_dir(path)]
            return {"ok": True, "path": path, "entries": entries}
        except FTPError as exc:
            return {"ok": False, "error": str(exc)}

    def run_sync(self, key: str, force_winner: str | None = None,
                 use_ftp: bool = True) -> dict[str, Any]:
        self._sync_log = []

        def log(msg: str) -> None:
            self._sync_log.append(msg)

        try:
            result = sync_game(key, self.sync_config, use_ftp=bool(use_ftp),
                               force_winner=force_winner, log=log)
            self.sync_config.save()
        except (FTPError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "log": self._sync_log}
        game = GAMES_BY_KEY[key]
        needs_restore = (not result.skipped and game.platform == "3ds"
                         and "3DS" in result.updated)
        return {
            "ok": True,
            "skipped": result.skipped,
            "winner": result.winner,
            "updated": result.updated,
            "backed_up": result.backed_up,
            "messages": result.messages,
            "log": self._sync_log,
            "needs_checkpoint_restore": needs_restore,
        }
