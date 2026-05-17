"""Erzeugt das App-Icon (klassischer Pokeball) als hochauflösendes PNG.

Aufruf:
    python data/make_app_icon.py

Ergebnis: data/app_icon.png (512x512). Das GUI lädt dieses Bild beim
Start als Fenster- und Dock-Icon.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def make_pokeball(size: int = 512) -> Image.Image:
    """Zeichnet einen klassischen Pokeball mit Anti-Aliasing.

    Trick gegen pixelige Ränder: zuerst doppelt so gross zeichnen,
    am Ende mit `Image.LANCZOS` herunterskalieren.
    """
    scale = 2
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(s * 0.02)
    bbox = (pad, pad, s - pad, s - pad)
    ring_width = int(s * 0.04)
    mid_y = s // 2
    band_half = int(s * 0.05)

    # Aussen-Ring (schwarz) als gefüllter Kreis.
    d.ellipse(bbox, fill=(0, 0, 0, 255))
    # Innenraum etwas kleiner.
    inner_pad = pad + ring_width
    inner = (inner_pad, inner_pad, s - inner_pad, s - inner_pad)

    # Untere Halbkugel: weiss.
    d.pieslice(inner, start=0, end=180, fill=(245, 245, 245, 255))
    # Obere Halbkugel: rot.
    d.pieslice(inner, start=180, end=360, fill=(229, 53, 53, 255))

    # Horizontaler schwarzer Balken in der Mitte.
    d.rectangle((pad, mid_y - band_half, s - pad, mid_y + band_half),
                fill=(0, 0, 0, 255))

    # Mittelknopf: aussen schwarz, innen weiss, ganz innen kleiner heller Kreis.
    cx, cy = s // 2, s // 2
    outer_r = int(s * 0.13)
    inner_r = int(s * 0.10)
    glint_r = int(s * 0.02)
    d.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
              fill=(0, 0, 0, 255))
    d.ellipse((cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
              fill=(255, 255, 255, 255))
    # Kleiner Highlight-Glanz oben links auf dem Knopf.
    d.ellipse((cx - inner_r + glint_r, cy - inner_r + glint_r,
               cx - inner_r + 3 * glint_r, cy - inner_r + 3 * glint_r),
              fill=(220, 220, 220, 255))

    # Glanz-Reflex oben links auf der roten Halbkugel.
    glow_box = (int(s * 0.18), int(s * 0.15),
                int(s * 0.42), int(s * 0.30))
    d.ellipse(glow_box, fill=(255, 255, 255, 70))

    # Auf die Zielgrösse herunterskalieren -> weiche Kanten.
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    icon_path = out_dir / "app_icon.png"
    icon = make_pokeball(512)
    icon.save(icon_path)
    print(f"Icon gespeichert: {icon_path}")

    # Zusätzlich ein kleines 64er Icon für den Fenster-Header (manche
    # Window-Manager nehmen lieber die kleine Variante).
    small_path = out_dir / "app_icon_64.png"
    icon.resize((64, 64), Image.LANCZOS).save(small_path)
    print(f"Kleine Variante: {small_path}")


if __name__ == "__main__":
    main()
