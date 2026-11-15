"""Prétraitement des images de pages avant la reconnaissance de caractères.

Trois opérations, toutes sur une image en niveaux de gris :

- `normalize_background` : éclairage inégal (ombre de reliure, dégradé du scanner) ; le fond est estimé par
  un maximum local flouté puis divisé, et le contraste est étiré ;
- `estimate_skew` / `deskew` : redressement léger (±5°) par maximisation de la variance du profil de
  projection horizontal des pixels sombres, sur une copie réduite ;
- `prepare` : l'enchaînement des deux, dans cet ordre.
"""

import numpy as np
from PIL import Image, ImageFilter

MAX_SKEW = 5.0  # degrés ; au-delà, la page est considérée comme volontairement tournée


def normalize_background(img: Image.Image) -> Image.Image:
    img = img.convert("L")
    small = img.resize((max(1, img.width // 8), max(1, img.height // 8)), Image.Resampling.BILINEAR)
    bg = small.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(4))
    bg_full = np.asarray(bg.resize(img.size, Image.Resampling.BILINEAR), dtype=np.float32)
    a = np.clip(np.asarray(img, dtype=np.float32) / np.maximum(bg_full, 1.0), 0.0, 1.0)
    lo, hi = np.percentile(a, [0.5, 60])
    if hi - lo < 0.05:  # page quasi uniforme (blanche) : rien à étirer
        return img
    a = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
    return Image.fromarray((a * 255).astype(np.uint8), "L")


def _profile_score(dark: Image.Image, angle: float) -> float:
    rotated = dark.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=0)
    rows = np.asarray(rotated, dtype=np.float32).sum(axis=1)
    return float(np.var(rows))


def estimate_skew(img: Image.Image) -> float:
    """Angle (degrés, sens trigonométrique) dont il faut tourner l'image pour redresser le texte ; 0.0 si
    la page porte trop peu de texte pour en juger."""
    img = img.convert("L")
    scale = 1000 / max(img.size)
    small = img
    if scale < 1:
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        small = img.resize(size, Image.Resampling.BOX)
    a = np.asarray(small, dtype=np.float32)
    thresh = min(float(np.percentile(a, 50)) * 0.75, 200.0)
    mask = a < thresh
    if mask.sum() < 0.002 * mask.size:
        return 0.0
    dark = Image.fromarray((mask * 255).astype(np.uint8), "L")
    coarse = np.arange(-MAX_SKEW, MAX_SKEW + 1e-6, 0.5)
    scores = [_profile_score(dark, float(t)) for t in coarse]
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(best - 0.5, best + 0.5 + 1e-6, 0.1)
    fine_scores = [_profile_score(dark, float(t)) for t in fine]
    best_fine = float(fine[int(np.argmax(fine_scores))])
    zero = _profile_score(dark, 0.0)
    # un gain négligeable sur l'angle nul n'est pas un défaut d'alignement
    if max(fine_scores) < zero * 1.03:
        return 0.0
    return best_fine


def deskew(img: Image.Image, angle: float | None = None) -> Image.Image:
    img = img.convert("L")
    if angle is None:
        angle = estimate_skew(img)
    if abs(angle) < 0.2:
        return img
    return img.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255, expand=False)


def prepare(img: Image.Image) -> Image.Image:
    return deskew(normalize_background(img))
