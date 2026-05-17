"""Lädt alle echten Pokemon-Stammformen in den lokalen Cache.

Hintergrund: das GUI und die Auto-Vervollständigung können nur Pokemon
berücksichtigen, die im Cache liegen. Wer alle ~1025 Stammformen im
Auswahl-Pool haben möchte, führt dieses Skript einmal mit Internet aus.

Standalone-Aufruf:
    python data/fetch_all_pokemon.py [-j 16] [--no-prune]

Das Skript nutzt den `/pokemon-species`-Endpoint der PokeAPI und
ignoriert damit gezielt Mega-, Gigantamax-, Form- und Geschlechts-
Varianten. Mit `--no-prune` werden alte Cache-Einträge nicht entfernt.

Höhere Werte für `-j` sind schneller, belasten die PokeAPI aber stärker.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

# Damit das Skript auch direkt (`python data/fetch_all_pokemon.py`)
# aufgerufen werden kann, wird das Projekt-Root in sys.path geschoben.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api_client import PokeAPIClient, PokeAPIError  # noqa: E402


def bulk_fetch(
    workers: int = 16,
    prune: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int, int]:
    """Lädt alle echten Pokemon-Species parallel in den Cache.

    Args:
        workers: Anzahl paralleler Download-Threads.
        prune: Wenn True, werden Cache-Einträge gelöscht, die nicht in
            der offiziellen Species-Liste vorkommen (Mega-Formen,
            Geschlechts-Varianten etc.).
        progress: optionaler Callback `(done, total, name) -> None`,
            der nach jedem Pokemon aufgerufen wird (für Fortschrittsanzeigen).

    Returns:
        Tupel (erfolgreich, gesamt, geprunt).
    """
    client = PokeAPIClient()
    names = client.list_all_pokemon_names(limit=2000)
    valid_names = set(names)
    total = len(names)
    success = 0
    pruned = 0

    # Optional: Pokemon-JSONs entfernen, die nicht (mehr) gewünscht sind.
    if prune:
        pruned = _prune_cache(client.cache_dir, valid_names)

    def load_one(name: str) -> tuple[str, bool]:
        try:
            client.get_pokemon(name)
            return name, True
        except PokeAPIError:
            return name, False

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(load_one, name): name for name in names}
        for i, future in enumerate(as_completed(futures), start=1):
            name, ok = future.result()
            if ok:
                success += 1
            if progress is not None:
                progress(i, total, name)

    return success, total, pruned


def _prune_cache(cache_dir: Path, valid_names: set[str]) -> int:
    """Löscht alle pokemon_*.json-Dateien, deren Name nicht in der
    `valid_names`-Liste vorkommt. Liefert die Anzahl gelöschter Dateien.

    Index-Dateien (z.B. `index_species_*.json`) bleiben unberührt.
    """
    if not cache_dir.exists():
        return 0
    removed = 0
    for cache_file in cache_dir.glob("pokemon_*.json"):
        name = cache_file.stem.removeprefix("pokemon_")
        if name not in valid_names:
            try:
                cache_file.unlink()
                removed += 1
            except OSError:
                # Falls die Datei nicht gelöscht werden kann, einfach weiter.
                pass
    return removed


def _print_progress(done: int, total: int, name: str) -> None:
    """Einfache Konsolen-Fortschrittsanzeige."""
    percent = 100 * done // max(total, 1)
    sys.stdout.write(f"\r[{done:4d}/{total}] {percent:3d}%  {name:<30s}")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-j", "--workers", type=int, default=16,
        help="Anzahl paralleler Downloads (Default: 16)",
    )
    parser.add_argument(
        "--no-prune", action="store_true",
        help="Lässt bestehende Mega/Form-Einträge im Cache, statt sie zu löschen.",
    )
    args = parser.parse_args()

    print(f"Starte Bulk-Download mit {args.workers} parallelen Threads ...")
    start = time.time()
    success, total, pruned = bulk_fetch(
        workers=args.workers,
        prune=not args.no_prune,
        progress=_print_progress,
    )
    elapsed = time.time() - start
    print()
    print(f"Fertig: {success}/{total} Pokemon geladen in {elapsed:.1f}s.")
    if pruned:
        print(f"Aus dem Cache entfernt: {pruned} Form-/Mega-Einträge.")


if __name__ == "__main__":
    main()
