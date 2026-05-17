"""Befüllt den lokalen Cache mit ein paar bekannten Pokemon und erzeugt
typ-gefärbte Platzhalter-Sprites, damit Demo und GUI auch ohne Internet
hübsch aussehen.

Wozu?
- Damit Demos und Tests auch ohne Internet funktionieren.
- Die Daten entsprechen exakt dem Format, das die PokeAPI liefert
  (gekürzt auf die Felder, die das Projekt tatsächlich auswertet).

Das Skript muss nur einmal ausgeführt werden:
    python data/seed_cache.py
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Stats sind die offiziellen Base-Stats aus den Hauptspielen.
SEED_POKEMON: list[dict] = [
    {"name": "charizard", "id": 6, "types": ["fire", "flying"],
     "stats": {"hp": 78, "attack": 84, "defense": 78,
               "special-attack": 109, "special-defense": 85, "speed": 100}},
    {"name": "blastoise", "id": 9, "types": ["water"],
     "stats": {"hp": 79, "attack": 83, "defense": 100,
               "special-attack": 85, "special-defense": 105, "speed": 78}},
    {"name": "venusaur", "id": 3, "types": ["grass", "poison"],
     "stats": {"hp": 80, "attack": 82, "defense": 83,
               "special-attack": 100, "special-defense": 100, "speed": 80}},
    {"name": "pikachu", "id": 25, "types": ["electric"],
     "stats": {"hp": 35, "attack": 55, "defense": 40,
               "special-attack": 50, "special-defense": 50, "speed": 90}},
    {"name": "snorlax", "id": 143, "types": ["normal"],
     "stats": {"hp": 160, "attack": 110, "defense": 65,
               "special-attack": 65, "special-defense": 110, "speed": 30}},
    {"name": "dragonite", "id": 149, "types": ["dragon", "flying"],
     "stats": {"hp": 91, "attack": 134, "defense": 95,
               "special-attack": 100, "special-defense": 100, "speed": 80}},
    {"name": "gengar", "id": 94, "types": ["ghost", "poison"],
     "stats": {"hp": 60, "attack": 65, "defense": 60,
               "special-attack": 130, "special-defense": 75, "speed": 110}},
    {"name": "alakazam", "id": 65, "types": ["psychic"],
     "stats": {"hp": 55, "attack": 50, "defense": 45,
               "special-attack": 135, "special-defense": 95, "speed": 120}},
    {"name": "gyarados", "id": 130, "types": ["water", "flying"],
     "stats": {"hp": 95, "attack": 125, "defense": 79,
               "special-attack": 60, "special-defense": 100, "speed": 81}},
    {"name": "machamp", "id": 68, "types": ["fighting"],
     "stats": {"hp": 90, "attack": 130, "defense": 80,
               "special-attack": 65, "special-defense": 85, "speed": 55}},
    {"name": "tyranitar", "id": 248, "types": ["rock", "dark"],
     "stats": {"hp": 100, "attack": 134, "defense": 110,
               "special-attack": 95, "special-defense": 100, "speed": 61}},
    {"name": "metagross", "id": 376, "types": ["steel", "psychic"],
     "stats": {"hp": 80, "attack": 135, "defense": 130,
               "special-attack": 95, "special-defense": 90, "speed": 70}},
    {"name": "garchomp", "id": 445, "types": ["dragon", "ground"],
     "stats": {"hp": 108, "attack": 130, "defense": 95,
               "special-attack": 80, "special-defense": 85, "speed": 102}},
    {"name": "salamence", "id": 373, "types": ["dragon", "flying"],
     "stats": {"hp": 95, "attack": 135, "defense": 80,
               "special-attack": 110, "special-defense": 80, "speed": 100}},
    {"name": "lucario", "id": 448, "types": ["fighting", "steel"],
     "stats": {"hp": 70, "attack": 110, "defense": 70,
               "special-attack": 115, "special-defense": 70, "speed": 90}},
    {"name": "greninja", "id": 658, "types": ["water", "dark"],
     "stats": {"hp": 72, "attack": 95, "defense": 67,
               "special-attack": 103, "special-defense": 71, "speed": 122}},
    # --- für die vorgefertigten Champion-Teams ---
    {"name": "pidgeot", "id": 18, "types": ["normal", "flying"],
     "stats": {"hp": 83, "attack": 80, "defense": 75,
               "special-attack": 70, "special-defense": 70, "speed": 101}},
    {"name": "rhydon", "id": 112, "types": ["ground", "rock"],
     "stats": {"hp": 105, "attack": 130, "defense": 120,
               "special-attack": 45, "special-defense": 45, "speed": 40}},
    {"name": "exeggutor", "id": 103, "types": ["grass", "psychic"],
     "stats": {"hp": 95, "attack": 95, "defense": 85,
               "special-attack": 125, "special-defense": 75, "speed": 55}},
    {"name": "arcanine", "id": 59, "types": ["fire"],
     "stats": {"hp": 90, "attack": 110, "defense": 80,
               "special-attack": 100, "special-defense": 80, "speed": 95}},
    {"name": "skarmory", "id": 227, "types": ["steel", "flying"],
     "stats": {"hp": 65, "attack": 80, "defense": 140,
               "special-attack": 40, "special-defense": 70, "speed": 70}},
    {"name": "claydol", "id": 344, "types": ["ground", "psychic"],
     "stats": {"hp": 60, "attack": 70, "defense": 105,
               "special-attack": 70, "special-defense": 120, "speed": 75}},
    {"name": "aggron", "id": 306, "types": ["steel", "rock"],
     "stats": {"hp": 70, "attack": 110, "defense": 180,
               "special-attack": 60, "special-defense": 60, "speed": 50}},
    {"name": "cradily", "id": 346, "types": ["rock", "grass"],
     "stats": {"hp": 86, "attack": 81, "defense": 97,
               "special-attack": 81, "special-defense": 107, "speed": 43}},
    {"name": "armaldo", "id": 348, "types": ["rock", "bug"],
     "stats": {"hp": 75, "attack": 125, "defense": 100,
               "special-attack": 70, "special-defense": 80, "speed": 45}},
    {"name": "spiritomb", "id": 442, "types": ["ghost", "dark"],
     "stats": {"hp": 50, "attack": 92, "defense": 108,
               "special-attack": 92, "special-defense": 108, "speed": 35}},
    {"name": "roserade", "id": 407, "types": ["grass", "poison"],
     "stats": {"hp": 60, "attack": 70, "defense": 65,
               "special-attack": 125, "special-defense": 105, "speed": 90}},
    {"name": "togekiss", "id": 468, "types": ["fairy", "flying"],
     "stats": {"hp": 85, "attack": 50, "defense": 95,
               "special-attack": 120, "special-defense": 115, "speed": 80}},
    {"name": "milotic", "id": 350, "types": ["water"],
     "stats": {"hp": 95, "attack": 60, "defense": 79,
               "special-attack": 100, "special-defense": 125, "speed": 81}},
    # --- weitere starke Pokemon für die Auto-Vervollständigung ---
    # Gen 2
    {"name": "typhlosion", "id": 157, "types": ["fire"],
     "stats": {"hp": 78, "attack": 84, "defense": 78,
               "special-attack": 109, "special-defense": 85, "speed": 100}},
    {"name": "scizor", "id": 212, "types": ["bug", "steel"],
     "stats": {"hp": 70, "attack": 130, "defense": 100,
               "special-attack": 55, "special-defense": 80, "speed": 65}},
    {"name": "houndoom", "id": 229, "types": ["dark", "fire"],
     "stats": {"hp": 75, "attack": 90, "defense": 50,
               "special-attack": 110, "special-defense": 80, "speed": 95}},
    {"name": "heracross", "id": 214, "types": ["bug", "fighting"],
     "stats": {"hp": 80, "attack": 125, "defense": 75,
               "special-attack": 40, "special-defense": 95, "speed": 85}},
    # Gen 3
    {"name": "swampert", "id": 260, "types": ["water", "ground"],
     "stats": {"hp": 100, "attack": 110, "defense": 90,
               "special-attack": 85, "special-defense": 90, "speed": 60}},
    {"name": "gardevoir", "id": 282, "types": ["psychic", "fairy"],
     "stats": {"hp": 68, "attack": 65, "defense": 65,
               "special-attack": 125, "special-defense": 115, "speed": 80}},
    {"name": "breloom", "id": 286, "types": ["grass", "fighting"],
     "stats": {"hp": 60, "attack": 130, "defense": 80,
               "special-attack": 60, "special-defense": 60, "speed": 70}},
    # Gen 4
    {"name": "empoleon", "id": 395, "types": ["water", "steel"],
     "stats": {"hp": 84, "attack": 86, "defense": 88,
               "special-attack": 111, "special-defense": 101, "speed": 60}},
    {"name": "weavile", "id": 461, "types": ["dark", "ice"],
     "stats": {"hp": 70, "attack": 120, "defense": 65,
               "special-attack": 45, "special-defense": 85, "speed": 125}},
    {"name": "magnezone", "id": 462, "types": ["electric", "steel"],
     "stats": {"hp": 70, "attack": 70, "defense": 115,
               "special-attack": 130, "special-defense": 90, "speed": 60}},
    # Gen 5
    {"name": "serperior", "id": 497, "types": ["grass"],
     "stats": {"hp": 75, "attack": 75, "defense": 95,
               "special-attack": 75, "special-defense": 95, "speed": 113}},
    {"name": "excadrill", "id": 530, "types": ["ground", "steel"],
     "stats": {"hp": 110, "attack": 135, "defense": 60,
               "special-attack": 50, "special-defense": 65, "speed": 88}},
    {"name": "haxorus", "id": 612, "types": ["dragon"],
     "stats": {"hp": 76, "attack": 147, "defense": 90,
               "special-attack": 60, "special-defense": 70, "speed": 97}},
    {"name": "volcarona", "id": 637, "types": ["bug", "fire"],
     "stats": {"hp": 85, "attack": 60, "defense": 65,
               "special-attack": 135, "special-defense": 105, "speed": 100}},
    {"name": "hydreigon", "id": 635, "types": ["dark", "dragon"],
     "stats": {"hp": 92, "attack": 105, "defense": 90,
               "special-attack": 125, "special-defense": 90, "speed": 98}},
    # Gen 6
    {"name": "aegislash", "id": 681, "types": ["steel", "ghost"],
     "stats": {"hp": 60, "attack": 50, "defense": 150,
               "special-attack": 50, "special-defense": 150, "speed": 60}},
    {"name": "sylveon", "id": 700, "types": ["fairy"],
     "stats": {"hp": 95, "attack": 65, "defense": 65,
               "special-attack": 110, "special-defense": 130, "speed": 60}},
    {"name": "talonflame", "id": 663, "types": ["fire", "flying"],
     "stats": {"hp": 78, "attack": 81, "defense": 71,
               "special-attack": 74, "special-defense": 69, "speed": 126}},
    # Gen 7
    {"name": "decidueye", "id": 724, "types": ["grass", "ghost"],
     "stats": {"hp": 78, "attack": 107, "defense": 75,
               "special-attack": 100, "special-defense": 100, "speed": 70}},
    {"name": "mimikyu", "id": 778, "types": ["ghost", "fairy"],
     "stats": {"hp": 55, "attack": 90, "defense": 80,
               "special-attack": 50, "special-defense": 105, "speed": 96}},
    {"name": "toxapex", "id": 748, "types": ["poison", "water"],
     "stats": {"hp": 50, "attack": 63, "defense": 152,
               "special-attack": 53, "special-defense": 142, "speed": 35}},
    # Gen 8
    {"name": "cinderace", "id": 815, "types": ["fire"],
     "stats": {"hp": 80, "attack": 116, "defense": 75,
               "special-attack": 65, "special-defense": 75, "speed": 119}},
    {"name": "corviknight", "id": 823, "types": ["flying", "steel"],
     "stats": {"hp": 98, "attack": 87, "defense": 105,
               "special-attack": 53, "special-defense": 85, "speed": 67}},
    {"name": "dragapult", "id": 887, "types": ["dragon", "ghost"],
     "stats": {"hp": 88, "attack": 120, "defense": 75,
               "special-attack": 100, "special-defense": 75, "speed": 142}},
    # Gen 9
    {"name": "meowscarada", "id": 908, "types": ["grass", "dark"],
     "stats": {"hp": 76, "attack": 110, "defense": 70,
               "special-attack": 81, "special-defense": 70, "speed": 123}},
    {"name": "skeledirge", "id": 911, "types": ["fire", "ghost"],
     "stats": {"hp": 104, "attack": 75, "defense": 100,
               "special-attack": 110, "special-defense": 75, "speed": 66}},
    {"name": "gholdengo", "id": 1000, "types": ["steel", "ghost"],
     "stats": {"hp": 87, "attack": 60, "defense": 95,
               "special-attack": 133, "special-defense": 91, "speed": 84}},
]

# Offizielle Farben pro Typ - in den Spielen und auf bulbapedia identisch.
TYPE_COLORS: dict[str, str] = {
    "normal":   "#A8A77A", "fire":     "#EE8130", "water":    "#6390F0",
    "electric": "#F7D02C", "grass":    "#7AC74C", "ice":      "#96D9D6",
    "fighting": "#C22E28", "poison":   "#A33EA1", "ground":   "#E2BF65",
    "flying":   "#A98FF3", "psychic":  "#F95587", "bug":      "#A6B91A",
    "rock":     "#B6A136", "ghost":    "#735797", "dragon":   "#6F35FC",
    "dark":     "#705746", "steel":    "#B7B7CE", "fairy":    "#D685AD",
}


def to_api_shape(short: dict) -> dict:
    """Bringt einen kompakten Eintrag in das Original-API-Format."""
    pid = short["id"]
    sprite_url = (
        "https://raw.githubusercontent.com/PokeAPI/sprites/"
        f"master/sprites/pokemon/{pid}.png"
    )
    return {
        "name": short["name"],
        "id": pid,
        "types": [{"type": {"name": t}} for t in short["types"]],
        "stats": [
            {"stat": {"name": stat_name}, "base_stat": value}
            for stat_name, value in short["stats"].items()
        ],
        "sprites": {"front_default": sprite_url},
    }


def make_placeholder_sprite(pokemon: dict, out_path: Path, size: int = 96) -> None:
    """Erzeugt ein kleines Pokeball-ähnliches Sprite mit Typ-Farben.

    Aufbau:
    - Kreis: Primärtyp-Farbe (obere Hälfte) / Sekundär-Typ-Farbe (untere Hälfte)
    - Schwarzer Ring + weisser Knopf wie ein Pokéball
    - Pokemon-Initiale gross in der Mitte
    """
    if not HAS_PIL:
        return  # ohne Pillow wird der Schritt einfach übersprungen

    primary = pokemon["types"][0]
    secondary = pokemon["types"][1] if len(pokemon["types"]) > 1 else primary
    color_top = TYPE_COLORS.get(primary, "#888888")
    color_bot = TYPE_COLORS.get(secondary, "#888888")

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 4
    bbox = (pad, pad, size - pad, size - pad)
    # Obere Halbkugel
    draw.pieslice(bbox, start=180, end=360, fill=color_top, outline="black", width=2)
    # Untere Halbkugel
    draw.pieslice(bbox, start=0, end=180, fill=color_bot, outline="black", width=2)
    # Horizontaler "Pokeball-Balken"
    mid_y = size // 2
    draw.rectangle((pad, mid_y - 3, size - pad, mid_y + 3), fill="black")
    # Mittelknopf (weisser Kreis)
    knob_r = size // 6
    cx, cy = size // 2, size // 2
    draw.ellipse((cx - knob_r, cy - knob_r, cx + knob_r, cy + knob_r),
                 fill="white", outline="black", width=2)

    # Initiale
    initial = pokemon["name"][0].upper()
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=18)
    except OSError:
        font = ImageFont.load_default()
    # Etwas verschoben in den Bereich oberhalb des Knopfes
    text_bbox = draw.textbbox((0, 0), initial, font=font)
    tw, th = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
    draw.text((cx - tw // 2, mid_y // 2 - th // 2 + 4), initial,
              fill="white", font=font, stroke_width=2, stroke_fill="black")

    img.save(out_path)


def main() -> None:
    base = Path(__file__).resolve().parent
    cache_dir = base / "cache"
    sprite_dir = base / "sprites"
    cache_dir.mkdir(parents=True, exist_ok=True)
    sprite_dir.mkdir(parents=True, exist_ok=True)

    for short in SEED_POKEMON:
        # JSON-Cache schreiben
        full = to_api_shape(short)
        out = cache_dir / f"pokemon_{short['name']}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(full, f, indent=2)
        # Platzhalter-Sprite schreiben
        sprite_out = sprite_dir / f"{short['id']}.png"
        if not sprite_out.exists():
            make_placeholder_sprite(short, sprite_out)

    print(f"Cache befüllt mit {len(SEED_POKEMON)} Pokemon -> {cache_dir}")
    if HAS_PIL:
        print(f"Platzhalter-Sprites erzeugt -> {sprite_dir}")
    else:
        print("Hinweis: Pillow nicht installiert -> keine Platzhalter-Sprites.")


if __name__ == "__main__":
    main()
