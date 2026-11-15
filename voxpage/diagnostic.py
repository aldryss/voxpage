"""Diagnostic : `voxpage --diagnostic`. Vérifie les dossiers, les réglages et les bibliothèques embarquées.

Sert surtout à contrôler l'exécutable livré (bibliothèques natives et données présentes, réglages
inscriptibles à côté de l'exécutable). Écrit `settings.json` s'il n'existe pas encore.
"""

import sys
from collections.abc import Callable

from voxpage import __version__, settings


def _pdfium() -> str:
    import pypdfium2

    doc = pypdfium2.PdfDocument.new()
    try:
        doc.new_page(200, 200)
        return f"pdfium {pypdfium2.version.PDFIUM_INFO}"
    finally:
        doc.close()


def _pdfminer() -> str:
    from pdfminer.cmapdb import CMapDB

    cmap = CMapDB.get_cmap("UniJIS-UCS2-H")  # lit un fichier de données du paquet
    return f"cmap {type(cmap).__name__}"


def _num2words() -> str:
    from num2words import num2words

    return num2words(42, lang="fr")


def _lameenc() -> str:
    import lameenc

    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(22050)
    enc.set_channels(1)
    enc.set_quality(2)
    return f"{len(enc.encode(b'\0\0' * 2205) + enc.flush())} octets"


def _sherpa() -> str:
    import sherpa_onnx

    return f"sherpa-onnx {sherpa_onnx.__version__}"


def _ocr() -> str:
    from voxpage.extract import ocr

    if not ocr.available():
        if getattr(sys, "frozen", False):
            raise RuntimeError(f"moteur ou modèles absents ({ocr.models_dir()})")
        return "non disponible (modèles absents : python tools/fetch_ocr.py)"
    return f"lu « {ocr.self_test()} », modèles dans {ocr.models_dir()}"


def _checks() -> list[tuple[str, Callable[[], str]]]:
    return [("sherpa-onnx", _sherpa), ("pypdfium2", _pdfium), ("pdfminer", _pdfminer),
            ("num2words", _num2words), ("lameenc", _lameenc), ("ocr", _ocr)]


def _pronunciations() -> list[str]:
    """Dictionnaire de prononciation : chemin, entrées de l'utilisateur et livrées, lignes ignorées."""
    from voxpage.normalize import lexicon

    path = settings.pronunciations_path()
    entries, problems = lexicon.read_entries(path) if path.is_file() else ([], [])
    state = "" if path.is_file() else " (absent : créé au premier ajout)"
    lines = [
        f"prononciations={path}{state}",
        f"prononciations_utilisateur={len(entries)} entrée(s)",
        "prononciations_livrees="
        + ", ".join(f"{lang} {len(lexicon.shipped_entries(lang))}" for lang in lexicon.LANGUAGES),
    ]
    lines += [f"avertissement prononciations : {p}" for p in problems]
    return lines


def run() -> int:
    ok = True
    lines = [
        f"voxpage {__version__}",
        f"frozen={bool(getattr(sys, 'frozen', False))}",
        f"app_dir={settings.app_dir()}",
        f"voices_dir={settings.voices_dir()}",
    ]
    try:
        settings.save(settings.load())
        lines.append(f"settings={settings.settings_path()}")
    except OSError as exc:
        ok = False
        lines.append(f"ÉCHEC réglages : {exc}")
    lines += _pronunciations()
    for name, check in _checks():
        try:
            lines.append(f"ok {name} : {check()}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"ÉCHEC {name} : {type(exc).__name__} : {exc}")
    text = "\n".join(lines) + "\n"
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        try:
            stream.write(text)
            stream.flush()
        except (OSError, ValueError, UnicodeError):
            pass
    return 0 if ok else 1
