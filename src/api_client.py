"""PokeAPI Client.

Holt Pokemon-Daten von https://pokeapi.co/.
Verwendet `urllib` aus der Standardbibliothek.

Robustheit:
- Retries mit exponentiellem Backoff bei Netzwerkfehlern
- Timeout pro Anfrage
- Validierung der API-Antwort (JSON-Struktur)
- Lokales Caching im JSON-Format, sodass die API nicht bei jedem Aufruf
  erneut kontaktiert wird (praktisch für Tests und langsame Verbindungen).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class PokeAPIError(Exception):
    """Wird geworfen, wenn die PokeAPI nicht erreichbar ist oder ungültige Daten liefert."""


class PokeAPIClient:
    """Einfacher HTTP-Client für die PokeAPI.

    Beispiel:
        >>> client = PokeAPIClient()
        >>> data = client.get_pokemon("pikachu")
        >>> data["name"]
        'pikachu'
    """

    BASE_URL = "https://pokeapi.co/api/v2"
    DEFAULT_TIMEOUT = 10  # Sekunden
    MAX_RETRIES = 3

    def __init__(
        self,
        base_url: str | None = None,
        cache_dir: str | Path | None = None,
        sprite_dir: str | Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        # Cache-Verzeichnis: Standard ist data/cache (frozen-aware,
        # siehe src/app_paths.py - gepackte App nutzt den User-Ordner).
        from .app_paths import data_dir
        if cache_dir is None:
            cache_dir = data_dir() / "cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Sprite-Verzeichnis: Standard ist data/sprites neben dem Cache.
        if sprite_dir is None:
            sprite_dir = data_dir() / "sprites"
        self.sprite_dir = Path(sprite_dir)
        self.sprite_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Öffentliche API
    # ------------------------------------------------------------------ #
    def get_pokemon(self, name_or_id: str | int) -> dict[str, Any]:
        """Lädt rohe Pokemon-Daten (Name, Stats, Typen, ...).

        Args:
            name_or_id: Pokemon-Name (z.B. 'pikachu') oder Pokédex-ID.

        Returns:
            Dictionary aus der PokeAPI.

        Raises:
            PokeAPIError: bei Netzwerkproblemen oder ungültigen Daten.
        """
        key = str(name_or_id).lower().strip()
        if not key:
            raise PokeAPIError("Pokemon-Name darf nicht leer sein.")
        endpoint = f"/pokemon/{key}"
        data = self._fetch_json(endpoint, cache_name=f"pokemon_{key}.json")
        # Validierung: minimale Felder müssen vorhanden sein
        for field in ("name", "stats", "types", "id"):
            if field not in data:
                raise PokeAPIError(
                    f"Antwort der PokeAPI ist unvollständig (fehlt: {field})."
                )
        return data

    def get_sprite(
        self,
        pokemon_id: int,
        sprite_url: str | None = None,
        allow_download: bool = True,
    ) -> Path | None:
        """Lädt das offizielle Pokemon-Sprite (96x96 PNG) und speichert es lokal.

        Versucht in dieser Reihenfolge:
        1. Cache auf der Platte (sprites/{id}.png)
        2. Über das Internet von der angegebenen URL (oder dem PokeAPI-Default)

        Mit `allow_download=False` wird Schritt 2 übersprungen - praktisch
        beim Aufbau der GUI, wenn der Cache schnell durchgegangen werden
        muss und Netz-Zugriff vermieden werden soll.

        Gibt den Pfad zum Sprite zurück, oder None, falls beides fehlschlägt.
        Wirft keine Exception, sodass Aufrufer einfach einen Platzhalter
        anzeigen können.
        """
        sprite_path = self.sprite_dir / f"{pokemon_id}.png"
        if sprite_path.exists():
            return sprite_path
        if not allow_download:
            return None
        if sprite_url is None:
            sprite_url = (
                "https://raw.githubusercontent.com/PokeAPI/sprites/"
                f"master/sprites/pokemon/{pokemon_id}.png"
            )
        try:
            raw = self._http_get_with_retries(sprite_url)
            sprite_path.write_bytes(raw)
            return sprite_path
        except (PokeAPIError, OSError):
            return None

    def list_all_pokemon_names(self, limit: int = 2000) -> list[str]:
        """Holt die Namen aller "echten" Pokemon (Stammformen).

        Nutzt den Endpoint `/pokemon-species`, der genau die kanonischen
        Pokemon listet (aktuell 1025, Stand Generation 9). Im Unterschied
        zu `/pokemon` enthält die Antwort keine Mega-, Gigantamax-, Form-
        oder Geschlechts-Varianten - genau das ist gewünscht, wenn das
        gesamte Pokedex einmalig in den Cache geladen werden soll.
        """
        endpoint = f"/pokemon-species?limit={int(limit)}"
        data = self._fetch_json(endpoint, cache_name=f"index_species_{limit}.json")
        results = data.get("results")
        if not isinstance(results, list):
            raise PokeAPIError("Antwort der PokeAPI hatte kein results-Feld.")
        names: list[str] = []
        for entry in results:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def get_type(self, type_name: str) -> dict[str, Any]:
        """Lädt Typ-Daten (Schwächen, Resistenzen).

        Wird vom TypeChart genutzt, um die offizielle Typ-Tabelle zu beziehen.
        """
        key = type_name.lower().strip()
        if not key:
            raise PokeAPIError("Typ-Name darf nicht leer sein.")
        endpoint = f"/type/{key}"
        data = self._fetch_json(endpoint, cache_name=f"type_{key}.json")
        if "damage_relations" not in data:
            raise PokeAPIError(f"Typ-Daten für '{key}' unvollständig.")
        return data

    # ------------------------------------------------------------------ #
    # Cache-Verwaltung
    # ------------------------------------------------------------------ #
    def clear_sprites(self) -> int:
        """Löscht alle gespeicherten Vorschaubilder (Sprites).

        Nützlich, wenn einzelne Bilder defekt oder nie richtig geladen
        worden sind - beim nächsten Anzeigen werden sie frisch von der
        PokeAPI heruntergeladen. Gibt die Anzahl gelöschter Dateien zurück.
        """
        removed = 0
        for sprite in self.sprite_dir.glob("*.png"):
            try:
                sprite.unlink()
                removed += 1
            except OSError:
                pass  # gesperrte/defekte Datei überspringen
        return removed

    def clear_pokemon_cache(self) -> int:
        """Löscht alle gecachten Pokemon-Daten (JSON).

        Achtung: danach ist die Pokemon-Liste leer, bis die Daten neu
        geladen werden (einzeln bei Bedarf oder über den Bulk-Download).
        Gibt die Anzahl gelöschter Dateien zurück.
        """
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    # ------------------------------------------------------------------ #
    # Interne Helfer
    # ------------------------------------------------------------------ #
    def _fetch_json(self, endpoint: str, cache_name: str | None = None) -> dict[str, Any]:
        """Lädt JSON von der API, nutzt lokalen Cache, falls vorhanden."""
        if cache_name:
            cached = self._read_cache(cache_name)
            if cached is not None:
                return cached

        url = f"{self.base_url}{endpoint}"
        raw = self._http_get_with_retries(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PokeAPIError(f"Antwort ist kein gültiges JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise PokeAPIError("Erwartet wurde ein JSON-Objekt von der PokeAPI.")

        if cache_name:
            self._write_cache(cache_name, data)
        return data

    def _http_get_with_retries(self, url: str) -> bytes:
        """HTTP GET mit Retries und exponentiellem Backoff."""
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PokemonTeamAnalyzer/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        raise PokeAPIError(
                            f"HTTP {resp.status} bei {url}"
                        )
                    return resp.read()
            except urllib.error.HTTPError as exc:
                # 404 = Pokemon existiert nicht -> sofort abbrechen, kein Retry
                if exc.code == 404:
                    raise PokeAPIError(f"Nicht gefunden: {url}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
            # Backoff: 0.5s, 1s, 2s ...
            if attempt < self.MAX_RETRIES:
                time.sleep(0.5 * (2 ** (attempt - 1)))
        raise PokeAPIError(
            f"PokeAPI nach {self.MAX_RETRIES} Versuchen nicht erreichbar: {last_error}"
        )

    def _read_cache(self, cache_name: str) -> dict[str, Any] | None:
        cache_file = self.cache_dir / cache_name
        if not cache_file.exists():
            return None
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            # Defekter Cache -> ignorieren, neu laden
            return None

    def _write_cache(self, cache_name: str, data: dict[str, Any]) -> None:
        cache_file = self.cache_dir / cache_name
        try:
            with cache_file.open("w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            # Cache ist nur optimisation; bei Fehler still durchgehen
            pass
