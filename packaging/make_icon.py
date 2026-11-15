"""Génère packaging/voxpage.ico (haut-parleur et ondes sur fond bleu) avec Pillow.

Usage : python packaging/make_icon.py [sortie.ico]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024  # dessin en grand, puis réduit pour chaque taille


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=200, fill=(18, 62, 130, 255))
    white = (255, 255, 255, 255)
    d.rectangle((190, 400, 340, 624), fill=white)  # boîtier du haut-parleur
    d.polygon([(330, 400), (560, 220), (560, 804), (330, 624)], fill=white)  # cône
    for r, w in ((190, 60), (310, 60)):  # ondes sonores
        box = (560 - r, 512 - r, 560 + r, 512 + r)
        d.arc(box, -42, 42, fill=white, width=w)
    return img


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "voxpage.ico"
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    draw().save(out, format="ICO", sizes=sizes)
    print(f"Icône écrite : {out}")


if __name__ == "__main__":
    main()
