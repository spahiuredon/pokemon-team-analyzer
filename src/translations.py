"""Deutsche Pokemon-Namen.

Die PokeAPI (und damit der Cache) arbeitet mit englischen Namen.
``data/german_names.json`` enthält das offizielle Mapping aller 1025
Pokemon (Quelle: PokeAPI-Stammdaten), sodass Suche und Anzeige auch auf
Deutsch funktionieren - komplett offline.

Format der JSON-Datei:
    {"6": {"en": "charizard", "de": "Glurak"}, ...}
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .app_paths import bundle_data_dir, is_frozen, project_data_dir


def _names_file() -> Path:
    base = bundle_data_dir() if is_frozen() else project_data_dir()
    return base / "german_names.json"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, str], dict[str, str], dict[int, str]]:
    """Lädt das Mapping einmalig.

    Returns:
        (deutsch_lower -> englisch, englisch -> Deutsch, dex_id -> Deutsch)
    """
    de_to_en: dict[str, str] = {}
    en_to_de: dict[str, str] = {}
    id_to_de: dict[int, str] = {}
    path = _names_file()
    if not path.exists():
        return de_to_en, en_to_de, id_to_de
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return de_to_en, en_to_de, id_to_de
    for pid, entry in raw.items():
        en = entry.get("en", "")
        de = entry.get("de", "")
        if en and de:
            de_to_en[de.lower()] = en
            en_to_de[en] = de
            id_to_de[int(pid)] = de
    return de_to_en, en_to_de, id_to_de


def to_english(name: str) -> str:
    """Übersetzt einen deutschen Pokemon-Namen ins Englische.

    Unbekannte (oder bereits englische) Namen kommen unverändert zurück -
    der Aufrufer kann das Ergebnis also direkt an die API/den Cache geben.
    """
    return _load()[0].get(name.strip().lower(), name)


def to_german(english_name: str) -> str | None:
    """Deutscher Anzeigename zu einem englischen Namen, oder None."""
    return _load()[1].get(english_name.strip().lower())


def display_name(english_name: str) -> str:
    """Anzeigename: Deutsch falls bekannt, sonst Englisch kapitalisiert."""
    return to_german(english_name) or english_name.capitalize()


def matches_query(english_name: str, query: str) -> bool:
    """Passt der Suchbegriff auf den englischen ODER deutschen Namen?"""
    q = query.strip().lower()
    if not q:
        return True
    if q in english_name.lower():
        return True
    german = to_german(english_name)
    return german is not None and q in german.lower()
