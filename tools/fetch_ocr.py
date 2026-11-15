#!/usr/bin/env python3
"""Télécharge les modèles OCR livrés dans `ocr/` (à lancer au build uniquement, jamais par l'application).

Usage : python tools/fetch_ocr.py [dossier_ocr]

Modèles PP-OCRv5 convertis en ONNX par RapidOCR : détection des lignes (« mobile ») et reconnaissance des
caractères latins (dont le français). Chaque fichier est vérifié par sa somme SHA-256 épinglée ; un fichier
déjà présent et conforme n'est pas retéléchargé. Bibliothèque standard uniquement.
"""

import hashlib
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/"

MODELS = [
    {
        "file": "ch_PP-OCRv5_det_mobile.onnx",
        "url": BASE_URL + "det/ch_PP-OCRv5_det_mobile.onnx",
        "sha256": "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
        "role": "détection des lignes de texte",
    },
    {
        "file": "latin_PP-OCRv5_rec_mobile.onnx",
        "url": BASE_URL + "rec/latin_PP-OCRv5_rec_mobile.onnx",
        "sha256": "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a",
        "role": "reconnaissance des caractères latins (dont le français)",
    },
]
LICENSE = "Apache-2.0"
SOURCE = "https://github.com/PaddlePaddle/PaddleOCR (modèles PP-OCRv5), convertis en ONNX par RapidOCR"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    last: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, dest.open("wb") as f:
                shutil.copyfileobj(r, f)
            return
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            print(f"  tentative {attempt} échouée : {exc}")
            time.sleep(5 * attempt)
    raise SystemExit(f"téléchargement impossible : {url} ({last})")


def fetch(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for m in MODELS:
        dest = target / m["file"]
        if dest.is_file() and _sha256(dest) == m["sha256"]:
            print(f"{m['file']} : déjà présent")
            continue
        print(f"{m['file']} : téléchargement {m['url']}")
        tmp = dest.with_suffix(".part")
        _download(m["url"], tmp)
        got = _sha256(tmp)
        if got != m["sha256"]:
            tmp.unlink()
            raise SystemExit(f"{m['file']} : SHA-256 inattendu ({got}), téléchargement rejeté")
        tmp.replace(dest)
    (target / "LISEZMOI.txt").write_text(
        "Modèles de reconnaissance de caractères (OCR) de Voxpage.\n"
        f"Licence : {LICENSE}. Source : {SOURCE}.\n"
        + "".join(f"- {m['file']} : {m['role']}\n" for m in MODELS),
        encoding="utf-8",
    )
    print(f"Modèles OCR prêts dans {target}")


if __name__ == "__main__":
    fetch(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "ocr")
