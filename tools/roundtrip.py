"""Aller-retour synthèse -> reconnaissance vocale, pour vérifier sans écouter que la voix dit le texte.

Outil de développement (jamais livré) : chaque phrase est normalisée comme dans l'application, synthétisée
avec chaque voix française (et chaque locuteur), puis transcrite par Whisper (sherpa-onnx). On compare la
transcription au texte dit (taux d'erreur sur les mots, WER, après mise en minuscules, sans ponctuation,
nombres écrits en lettres des deux côtés). Le WER sert à repérer les phrases où la voix dit autre chose que
le texte (nombres, sigles, mots écorchés), pas à noter le modèle de reconnaissance.

Modèle de reconnaissance (une fois, ~640 Mo, dans un dossier ignoré par git) :

    DEV_NET=1 ./dev python tools/roundtrip.py --telecharger

Puis :

    ./dev python tools/roundtrip.py [--vitesses 1.0,0.8,1.5] [--phrases fichier.txt] [--rapport sortie.md]

`--phrases` : une phrase brute (telle qu'écrite dans le document) par ligne ; par défaut, les phrases
ci-dessous, tirées des documents de la recette (docs/recette.md).
"""

import argparse
import re
import shutil
import sys
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voxpage.document import Block, Chapter, Document  # noqa: E402
from voxpage.normalize import NormalizeOptions, normalize  # noqa: E402
from voxpage.normalize.text import speak  # noqa: E402

ASR_DIR = ROOT / ".cache" / "asr"
ASR_NAME = "sherpa-onnx-whisper-small"
ASR_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{ASR_NAME}.tar.bz2"
ASR_RATE = 16000

# Phrases tirées des documents de la recette : nombres, dates, sigles, noms propres, abréviations.
SENTENCES = [
    # Insee Première n° 2033
    "Au 1er janvier 2025, la France compte 68,6 millions d'habitants, soit 0,25 % de plus qu'un an "
    "auparavant.",
    "En 2024, 663 000 bébés sont nés en France.",
    "L'indicateur conjoncturel de fécondité s'établit à 1,62 enfant par femme, après 1,66 en 2023.",
    "En 2024, 646 000 personnes sont décédées en France, soit +1,1 % par rapport à 2023.",
    "Au 1er janvier 2023, la France représentait 15 % de la population de l'Union européenne à 27 pays "
    "(UE27).",
    "En 2022, l'ICF était le plus élevé de l'UE27 en France (1,78), puis en Roumanie, Bulgarie et Tchéquie.",
    # Constitution de 1958
    "Le Président de la République est élu pour cinq ans au suffrage universel direct.",
    "Sont admises à participer au scrutin les personnes remplissant les conditions fixées à l'article 2 "
    "de la loi n° 88-1028 du 9 novembre 1988.",
    "La République peut reconnaître la juridiction de la Cour pénale internationale dans les conditions "
    "prévues par le traité signé le 18 juillet 1998.",
    "Le Conseil constitutionnel veille à la régularité des opérations de référendum prévues aux articles "
    "11 et 89 et au titre XV.",
    "TITRE XI BIS - LE DÉFENSEUR DES DROITS",
    # Maupassant, Contes de la bécasse (Bibebook)
    "Le vieux baron des Ravots avait été pendant quarante ans le roi des chasseurs de sa province.",
    "Morin se trouvait dans cet état, quand il prit son billet pour La Rochelle par l'express de 8 heures "
    "40 du soir.",
    "Je laissai à M. le curé les vingt-sept francs pour l'enterrement.",
    # Article HAL (Schöpfel et al., 2024)
    "Aujourd'hui, début 2024, HAL joue un rôle central dans la politique de la science ouverte en France, "
    "avec 1,3 million de documents scientifiques.",
    "L'évaluation des laboratoires de recherche par le Hcéres examine comment la science ouverte est prise "
    "en compte (Coulhon et Larrouturou, 2023).",
    "Parmi ces outils, citons la suite HALUR développée à Rennes, l'outil OCdHAL développé à Grenoble et "
    "les HalTools développés par l'INRIA.",
    # Notice des impôts 2041-E
    "Accueil téléphonique : 01 72 95 20 42 (de 9 h à 16 h, horaires de métropole).",
    "Les dirigeants dont le chiffre d'affaires annuel est supérieur à 250 millions d'euros sont considérés "
    "comme étant domiciliés en France.",
    "1° ont en France leur foyer ou le lieu de leur séjour principal ;",
    # Notice Riviera-et-Bar BTA 850
    "Vous trouverez les coordonnées du Centre services agréé le plus proche de chez vous sur : "
    "www.riviera-et-bar.fr",
    "Nous vous recommandons une quantité de 2 à 3 g de thé par 200 ml d'eau (soit environ 1 cuillère à "
    "café).",
    "La capacité maximale de la verseuse pour la préparation de thé est de 1,2 litre.",
]


# --------------------------------------------------------------------------------------------- texte


def spoken(raw: str) -> str:
    """Texte dit par l'application pour cette phrase (segments recollés)."""
    doc = Document("", None, "fr", [Chapter("", [Block("paragraph", raw)])], [])
    return " ".join(s.text for ch in normalize(doc, NormalizeOptions()) for s in ch.segments)


def _num_words(text: str) -> str:
    from num2words import num2words

    text = re.sub(r"(\d)[  ](?=\d{3}\b)", r"\1", text)  # 663 000 -> 663000
    return re.sub(r"\d+", lambda m: " " + num2words(int(m.group(0)), lang="fr") + " ", text)


def comparable(text: str) -> list[str]:
    """Mots comparables : même normalisation que l'application, nombres en lettres, minuscules, sans
    ponctuation ni traits d'union (« vingt-sept » = « vingt sept »)."""
    t = speak(text.replace("’", "'"), "fr")  # chiffres décimaux, %, unités… lus comme le fait Voxpage
    t = _num_words(t)
    t = t.lower().replace("œ", "oe")
    t = re.sub(r"[-‐–—'’]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = t.replace("_", " ")
    return t.split()


def wer(ref: list[str], hyp: list[str]) -> tuple[int, int]:
    """(erreurs, mots de référence) par distance d'édition sur les mots."""
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
            prev, d[j] = d[j], cur
    return d[len(hyp)], len(ref)


# --------------------------------------------------------------------------------------------- moteurs


def download() -> None:
    ASR_DIR.mkdir(parents=True, exist_ok=True)
    archive = ASR_DIR / f"{ASR_NAME}.tar.bz2"
    req = urllib.request.Request(ASR_URL, headers={"User-Agent": "voxpage-roundtrip"})
    with urllib.request.urlopen(req, timeout=600) as r, open(archive, "wb") as f:
        shutil.copyfileobj(r, f)
    with tarfile.open(archive) as t:
        t.extractall(ASR_DIR, filter="data")
    archive.unlink()
    print(f"Modèle installé dans {ASR_DIR / ASR_NAME}")


def recognizer(threads: int):
    import sherpa_onnx

    d = ASR_DIR / ASR_NAME
    if not d.is_dir():
        sys.exit(f"Modèle absent ({d}) : DEV_NET=1 ./dev python tools/roundtrip.py --telecharger")
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(d / "small-encoder.onnx"),
        decoder=str(d / "small-decoder.onnx"),
        tokens=str(d / "small-tokens.txt"),
        language="fr",
        task="transcribe",
        num_threads=threads,
    )


def to_16k(pcm: np.ndarray, rate: int) -> np.ndarray:
    x = pcm.astype(np.float32) / 32768.0
    if rate == ASR_RATE:
        return x
    n = int(round(len(x) * ASR_RATE / rate))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def transcribe(rec, audio: np.ndarray) -> str:
    # un peu de silence autour : Whisper coupe parfois le dernier mot d'un enregistrement très serré
    pad = np.zeros(ASR_RATE // 4, dtype=np.float32)
    stream = rec.create_stream()
    stream.accept_waveform(ASR_RATE, np.concatenate([pad, audio, pad]))
    rec.decode_stream(stream)
    return stream.result.text.strip()


# --------------------------------------------------------------------------------------------- mesure


@dataclass
class Row:
    voice: str
    speed: float
    raw: str
    said: str
    heard: str
    errors: int
    words: int


def run(sentences: list[str], speeds: list[float], threads: int) -> list[Row]:
    from voxpage.tts.sherpa import SherpaEngine

    eng = SherpaEngine(ROOT / "voices", num_threads=threads)
    rec = recognizer(threads)
    voices = [(v.id, k, v.speakers[k] if v.speakers else "") for v in eng.list_voices() if v.lang == "fr"
              for k in range(max(1, len(v.speakers)))]
    rows = []
    for vid, spk, spk_name in voices:
        label = f"{vid}" + (f" / {spk_name}" if spk_name else "")
        for speed in speeds:
            t0 = time.time()
            for raw in sentences:
                said = spoken(raw)
                pcm, rate = eng.synthesize(said, vid, spk, speed)
                heard = transcribe(rec, to_16k(pcm, rate))
                e, n = wer(comparable(said), comparable(heard))
                rows.append(Row(label, speed, raw, said, heard, e, n))
            print(f"{label} x{speed} : {time.time() - t0:.0f} s", file=sys.stderr)
    return rows


def report(rows: list[Row], threshold: float) -> str:
    out = ["## Aller-retour synthèse → reconnaissance (Whisper small)", ""]
    out += ["| Voix | Vitesse | WER | Phrases sans erreur |", "|---|---|---|---|"]
    keys = []
    for r in rows:
        if (r.voice, r.speed) not in keys:
            keys.append((r.voice, r.speed))
    for voice, speed in keys:
        sel = [r for r in rows if r.voice == voice and r.speed == speed]
        e, n = sum(r.errors for r in sel), sum(r.words for r in sel)
        ok = sum(1 for r in sel if r.errors == 0)
        out.append(f"| {voice} | {speed:g} | {100 * e / max(1, n):.1f} % | {ok}/{len(sel)} |")
    out += ["", f"### Phrases à WER > {threshold:.0%} (texte dit / transcription)", ""]
    for r in rows:
        if r.words and r.errors / r.words > threshold:
            out.append(f"- {r.voice} x{r.speed:g}, WER {100 * r.errors / r.words:.0f} %")
            out.append(f"  - dit : {r.said}")
            out.append(f"  - entendu : {r.heard}")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--telecharger", action="store_true", help="télécharge le modèle Whisper small")
    ap.add_argument("--phrases", type=Path, help="fichier : une phrase brute par ligne")
    ap.add_argument("--vitesses", default="1.0,0.8,1.5")
    ap.add_argument("--seuil", type=float, default=0.15, help="WER au-delà duquel une phrase est détaillée")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rapport", type=Path, help="écrit le rapport Markdown dans ce fichier")
    a = ap.parse_args()
    if a.telecharger:
        download()
        return
    sentences = SENTENCES
    if a.phrases:
        sentences = [ln.strip() for ln in a.phrases.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = run(sentences, [float(v) for v in a.vitesses.split(",")], a.threads)
    text = report(rows, a.seuil)
    if a.rapport:
        a.rapport.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
