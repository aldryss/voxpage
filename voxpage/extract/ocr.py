"""Reconnaissance de caractères (OCR) locale des pages scannées.

Moteur : RapidOCR (onnxruntime) avec les modèles PP-OCRv5 (détection « mobile », lecture « latin »), livrés
dans le dossier `ocr/` de l'application (voir tools/fetch_ocr.py) : aucun téléchargement ni écriture à
l'exécution. Le choix du moteur est documenté et mesuré dans docs/ocr.md.

Chaîne : rendu de la page (pypdfium2, 300 dpi, niveaux de gris) → fond uniformisé et redressement léger
(ocr_prep) → détection et lecture des lignes → `OcrPage` (lignes avec leur géométrie en points PDF et leur
confiance). L'extracteur PDF transforme ensuite ces lignes en `PageData` (`to_page_data`) pour leur appliquer
le même traitement de structure que le texte natif : en-têtes et pieds répétés, colonnes, paragraphes,
césures.

Ce module s'importe toujours sans erreur ; les bibliothèques lourdes sont chargées à la première page.
`available()` dit si le moteur et ses modèles sont présents ; sinon l'extracteur garde son comportement
sans OCR.
"""

import importlib.util
import os
import re
import statistics
import threading
from dataclasses import dataclass
from pathlib import Path

from voxpage.extract.pdf_layout import Frag, PageData, Span
from voxpage.extract.pdf_text import clean_text

RENDER_DPI = 300
MAX_PIXELS = 36_000_000  # au-delà (affiches), on réduit la résolution de rendu
ENGINE_LONG_SIDE = 2400  # taille (px) du grand côté confiée au moteur : mesurée dans docs/ocr.md
DET_MODEL = "ch_PP-OCRv5_det_mobile.onnx"
REC_MODEL = "latin_PP-OCRv5_rec_mobile.onnx"
MIN_SCORE_WARN = 0.80  # confiance moyenne en dessous de laquelle la page est signalée


class OcrError(Exception):
    """Échec de la reconnaissance sur une page (le message n'est pas destiné à l'utilisateur)."""


@dataclass(frozen=True)
class OcrLine:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float  # coordonnées en points PDF, origine en haut à gauche
    score: float  # confiance du moteur, 0..1


@dataclass
class OcrPage:
    width: float
    height: float
    lines: list[OcrLine]

    @property
    def mean_score(self) -> float:
        total = sum(len(ln.text) for ln in self.lines)
        if not total:
            return 1.0
        return sum(ln.score * len(ln.text) for ln in self.lines) / total


# Confusions de lettres du moteur : en police sans empattement, « I » (i majuscule) et « l » (L minuscule)
# ont la même forme. Les règles ci-dessous ne s'appliquent qu'aux formes impossibles en français (« Ie »,
# « I’hôtel », « aIors ») et jamais à un mot valide (« Il », « Ici », « Italie »).
_ELISION_I = re.compile(r"\bI(?=['’][aeiouyhàâäéèêëîïôöùûüœ])")
_INNER_I = re.compile(r"(?<=[a-zà-ÿœ])I(?=[a-zà-ÿœ]|\b)")
_WORD_I = {
    "Ie": "le", "Ia": "la", "Ies": "les", "Ieur": "leur", "Ieurs": "leurs", "Iui": "lui", "Iequel": "lequel",
    "Iaquelle": "laquelle", "Iesquels": "lesquels", "Iesquelles": "lesquelles", "Ià": "là",
    "ll": "il", "lls": "ils",
}
_TOKEN = re.compile(r"(?<![\w'’])([Il][a-zà-ÿœ]*|ll|lls)(?![\w])")


def fix_confusions(text: str, lang: str | None = None) -> str:
    """Corrige les confusions « I »/« l » du moteur pour le français (ne touche pas aux textes anglais)."""
    if lang == "en":
        return text
    text = _ELISION_I.sub("l", text)
    text = _INNER_I.sub("l", text)

    def token(m: re.Match) -> str:
        word = m.group(1)
        fixed = _WORD_I.get(word)
        if fixed is None:
            return word
        before = text[: m.start()].rstrip()
        if not before or before[-1] in ".!?…«:\"":
            fixed = fixed.capitalize()
        return fixed

    return _TOKEN.sub(token, text)


def models_dir() -> Path:
    from voxpage import settings  # import tardif : settings tire audio et mutagen

    override = os.environ.get("VOXPAGE_OCR")
    return Path(override) if override else settings.app_dir() / "ocr"


def available() -> bool:
    """Le moteur est-il importable et ses modèles présents ?"""
    folder = models_dir()
    if not (folder / DET_MODEL).is_file() or not (folder / REC_MODEL).is_file():
        return False
    return all(importlib.util.find_spec(name) is not None for name in ("rapidocr", "onnxruntime", "cv2"))


_lock = threading.Lock()
_engine = None
_engine_dir: Path | None = None


def _load_engine():
    global _engine, _engine_dir
    folder = models_dir()
    with _lock:
        if _engine is not None and _engine_dir == folder:
            return _engine
        try:
            from rapidocr import ModelType, OCRVersion, RapidOCR

            params = {
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.MOBILE,
                "Det.lang_type": "multi",
                "Det.model_path": str(folder / DET_MODEL),
                "Det.unclip_ratio": 1.6,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.lang_type": "latin",
                "Rec.model_path": str(folder / REC_MODEL),
                "Global.text_score": 0.0,  # aucun mot écarté pour faible confiance
                "Global.use_cls": False,
                "Global.log_level": "error",
                "Global.max_side_len": 100_000,
                "Global.min_side_len": 1,
            }
            _engine = RapidOCR(params=params)
        except Exception as exc:  # noqa: BLE001 — bibliothèque ou modèle inutilisable
            raise OcrError(f"moteur OCR indisponible : {exc}") from exc
        _engine_dir = folder
        return _engine


def self_test() -> str:
    """Charge le moteur et lit une image de test (pour `voxpage --diagnostic`) ; renvoie le texte lu."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (900, 160), 255)
    ImageDraw.Draw(img).text((30, 40), "Voxpage 2024", fill=0, font=ImageFont.load_default(64))
    page = recognize_image(img, 900.0, 160.0)
    return " ".join(ln.text for ln in page.lines)


def render_page(pdf_path: Path, page_index: int):
    """Image en niveaux de gris de la page à 300 dpi et taille de la page en points."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[page_index]
        width, height = page.get_size()
        scale = RENDER_DPI / 72
        if width * height * scale * scale > MAX_PIXELS:
            scale = (MAX_PIXELS / (width * height)) ** 0.5
        img = page.render(scale=scale, grayscale=True).to_pil().convert("L")
        return img, width, height
    finally:
        pdf.close()


def recognize_image(img, width: float, height: float, lang: str | None = None) -> OcrPage:
    """Lit une image de page (niveaux de gris) ; `width` et `height` sont la taille de la page en points."""
    import numpy as np
    from PIL import Image

    from voxpage.extract.ocr_prep import prepare

    engine = _load_engine()
    img = prepare(img)
    px_w, px_h = img.size
    k = ENGINE_LONG_SIDE / max(px_w, px_h)
    small = img
    if k < 1:
        small = img.resize((max(1, round(px_w * k)), max(1, round(px_h * k))), Image.Resampling.LANCZOS)
    try:
        result = engine(np.asarray(small.convert("RGB")))
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"échec de la lecture : {exc}") from exc
    lines: list[OcrLine] = []
    if result is None or result.boxes is None:
        return OcrPage(width, height, lines)
    to_pt_x, to_pt_y = width / small.width, height / small.height
    scores = list(result.scores) if result.scores is not None else [1.0] * len(result.txts)
    for box, text, score in zip(result.boxes, result.txts, scores, strict=False):
        text = fix_confusions(clean_text(text), lang)
        if not text:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        box_pt = (min(xs) * to_pt_x, min(ys) * to_pt_y, max(xs) * to_pt_x, max(ys) * to_pt_y)
        lines.append(OcrLine(text, *box_pt, float(score)))
    return OcrPage(width, height, lines)


def recognize(pdf_path: Path, page_index: int, lang: str | None = None) -> OcrPage:
    """OCR d'une page d'un PDF. Les modèles latins couvrent le français et l'anglais sans réglage ; `lang`
    ne sert qu'à décider des corrections propres au français."""
    try:
        img, width, height = render_page(Path(pdf_path), page_index)
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"rendu de la page impossible : {exc}") from exc
    return recognize_image(img, width, height, lang)


def to_page_data(page: OcrPage, index: int) -> PageData:
    """Convertit les lignes reconnues en `PageData` : un fragment par ligne, à la manière du texte natif.

    La géométrie est régularisée : la hauteur d'une boîte de détection varie avec les accents et les
    jambages, pas la taille de la police. Les lignes de hauteur proche de la médiane reçoivent la même
    taille ; seules celles nettement plus hautes (titres) gardent la leur, ce qui permet à l'extracteur de
    les reconnaître comme titres. Aucune ligne n'est plus petite que le corps (pas de fausse note de bas
    de page).
    """
    lines = [ln for ln in page.lines if ln.text.strip()]
    heights = [ln.bottom - ln.top for ln in lines]
    body_h = statistics.median(heights) if heights else 10.0
    frags: list[Frag] = []
    for ln, h in zip(lines, heights, strict=True):
        big = h > 1.3 * body_h
        size = (h if big else body_h) / 1.25
        mid = (ln.top + ln.bottom) / 2
        top, bottom = mid - 0.625 * size, mid + 0.625 * size
        frags.append(
            Frag([Span(ln.text)], ln.x0, ln.x1, top, bottom, mid + 0.3 * size, size, False, False, index)
        )
    data = PageData(index, page.width, page.height, frags, [], [])
    visible = "".join(ln.text for ln in lines if not ln.text.isspace())
    data.n_chars = len(visible)
    data.n_alnum = sum(1 for c in visible if c.isalnum())
    return data


def scale_sizes(data: PageData, target_body: float) -> None:
    """Ramène la taille de corps de la page OCR à celle du texte natif du document (les tailles ne servent
    qu'à comparer les lignes entre elles : titres, notes, corps)."""
    weights: dict[float, int] = {}
    for f in data.frags:
        weights[round(f.size, 1)] = weights.get(round(f.size, 1), 0) + len(f.text)
    if not weights:
        return
    own = max(weights, key=lambda s: weights[s])
    factor = target_body / own
    if 0.5 <= factor <= 2.0:
        for f in data.frags:
            f.size *= factor
