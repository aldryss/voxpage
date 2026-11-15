#!/usr/bin/env python3
"""Télécharge les voix livrées dans `voices/` (à lancer au build uniquement, jamais par l'application).

Usage : python tools/fetch_voices.py [dossier_voices]
Bibliothèque standard uniquement ; fonctionne sous Linux et Windows.
"""

import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

BASE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"

VOICES = [
    {
        "id": "fr_FR-siwis-medium",
        "archive": "vits-piper-fr_FR-siwis-medium.tar.bz2",
        "sha256": "375909aa30842b3a4efa10b1beb1d761af792960ae6873b4d53889f96c66195b",
        "name": "Français, voix féminine (Siwis)",
        "lang": "fr",
        "speakers": [],
        "license": "CC BY 4.0",
        "source": "https://datashare.is.ed.ac.uk/handle/10283/2353",
        "attribution": "Corpus SIWIS, University of Edinburgh (CC BY 4.0) ; modèle Piper fr_FR-siwis-medium.",
    },
    {
        "id": "fr_FR-upmc-medium",
        "archive": "vits-piper-fr_FR-upmc-medium.tar.bz2",
        "sha256": "e9830a331a16f6cc5ef3116a287065e015d3495c3f56b974889a266da7f89a7f",
        "name": "Français, UPMC",
        "lang": "fr",
        "speakers": ["Jessica (voix féminine)", "Pierre (voix masculine)"],
        "license": "CC BY-SA 4.0",
        "source": "https://github.com/marytts/upmc-pierre-data",
        "attribution": "Corpus UPMC Jessica et Pierre (CC BY-SA 4.0) ; modèle Piper fr_FR-upmc-medium.",
    },
    {
        "id": "en_GB-cori-medium",
        "archive": "vits-piper-en_GB-cori-medium.tar.bz2",
        "sha256": "49c9a5361bbdd95d7ca9687c4de11e5908481f65e7c7c368960df79949fdac2b",
        "name": "English, female voice (Cori)",
        "lang": "en",
        "speakers": [],
        "license": "Domaine public (LibriVox)",
        "source": "https://librivox.org",
        "attribution": "Enregistrements LibriVox (domaine public) ; modèle Piper en_GB-cori-medium.",
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _safe_extract(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:bz2") as tar:
        root = target.resolve()
        for member in tar.getmembers():
            if not (target / member.name).resolve().is_relative_to(root) or not (
                member.isfile() or member.isdir()
            ):
                raise SystemExit(f"Archive suspecte : {member.name}")
        if hasattr(tarfile, "data_filter"):
            tar.extractall(target, filter="data")
        else:
            tar.extractall(target)


def fetch(voice: dict, voices_dir: Path) -> None:
    final = voices_dir / voice["id"]
    if (final / "voice.json").is_file():
        print(f"{voice['id']} : déjà présente")
        return
    with tempfile.TemporaryDirectory(prefix="voxpage-voice-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / voice["archive"]
        print(f"{voice['id']} : téléchargement…")
        _download(BASE_URL + voice["archive"], archive)
        digest = _sha256(archive)
        if digest != voice["sha256"]:
            raise SystemExit(f"{voice['id']} : somme SHA-256 inattendue ({digest}), voix refusée.")
        out = tmp_dir / "out"
        out.mkdir()
        _safe_extract(archive, out)
        (src,) = [p for p in out.iterdir() if p.is_dir()]
        for needed in ("tokens.txt", "espeak-ng-data"):
            if not (src / needed).exists():
                raise SystemExit(f"{voice['id']} : « {needed} » absent de l'archive.")
        if not list(src.glob("*.onnx")):
            raise SystemExit(f"{voice['id']} : aucun modèle .onnx dans l'archive.")
        meta = {k: voice[k] for k in ("name", "lang", "speakers", "license", "source", "attribution")}
        (src / "voice.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        voices_dir.mkdir(parents=True, exist_ok=True)
        if final.exists():
            shutil.rmtree(final)
        shutil.move(str(src), str(final))
    print(f"{voice['id']} : installée")


def main() -> None:
    voices_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "voices"
    for voice in VOICES:
        fetch(voice, voices_dir)


if __name__ == "__main__":
    main()
