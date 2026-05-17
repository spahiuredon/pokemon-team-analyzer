"""Lädt alle Pokemon aus der PokeAPI in den lokalen Cache.

Hintergrund: das GUI und die Auto-Vervollständigung können nur Pokemon
berücksichtigen, die im Cache liegen. Wer alle (~1300) Pokemon im
Auswahl-Pool haben möchte, führt dieses Skript einmal mit Internet aus.

Standalone-Aufruf:
    python data/fetch_all_pokemon.py [-j 16]

Das Skript ist idempotent: bereits vorhandene Cache-Einträge werden
nicht erneut heruntergeladen. Mit `-j` lässt sich die Anzahl paralleler
Downloads steuern (Default 16). Höhere Werte sind schneller, belasten
die PokeAPI aber stärker.
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
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int]:
    """Lädt alle Pokemon parallel in den Cache.

    Args:
        workers: Anzahl paralleler Download-Threads.
        progress: optionaler Callback `(done, total, name) -> None`,
            der nach jedem Pokemon aufgerufen wird (für Fortschrittsanzeigen).

    Returns:
        Tupel (erfolgreich, gesamt).
    """
    client = PokeAPIClient()
    names = client.list_all_pokemon_names(limit=1500)
    total = len(names)
    success = 0

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

    return success, total


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
    args = parser.parse_args()

    print(f"Starte Bulk-Download mit {args.workers} parallelen Threads ...")
    start = time.time()
    success, total = bulk_fetch(workers=args.workers, progress=_print_progress)
    elapsed = time.time() - start
    print()
    print(f"Fertig: {success}/{total} Pokemon geladen in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
