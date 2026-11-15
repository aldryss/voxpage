"""Ligne de commande : `voxpage ENTREE [-o SORTIE] [options]`."""

import argparse
import copy
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from voxpage import __version__, settings
from voxpage.pipeline import ConversionError, convert, extract_text
from voxpage.progress import Cancelled, CancelToken

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_CANCELLED = 0, 1, 2, 130


def _out(stream_name: str, text: str) -> None:
    """Écrit sur stdout/stderr s'ils existent (exécutable fenêtré : ils valent None)."""
    stream = getattr(sys, stream_name, None)
    if stream is None:
        return
    try:
        stream.write(text)
        stream.flush()
    except (OSError, ValueError, UnicodeError):
        pass


def _err(text: str) -> None:
    _out("stderr", text)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voxpage",
        description="Convertit un document (PDF, texte) en fichier audio, entièrement en local.",
        epilog="Les options non précisées reprennent les réglages enregistrés par l'application.",
    )
    p.add_argument("entree", nargs="?", metavar="ENTREE", help="document à convertir")
    p.add_argument(
        "-o", "--sortie", metavar="SORTIE", help="fichier audio produit (défaut : à côté de l'entrée)"
    )
    p.add_argument("--voix", metavar="ID", help="identifiant de la voix (voir --liste-voix)")
    p.add_argument(
        "--locuteur", type=int, metavar="N", help="numéro du locuteur, pour les voix multi-locuteurs"
    )
    p.add_argument("--vitesse", type=float, metavar="V", help="vitesse de lecture, 0.5 à 2.0 (défaut : 1.0)")
    p.add_argument("--format", choices=("mp3", "wav"), help="format audio")
    p.add_argument("--debit", type=int, metavar="KBPS", help="débit MP3 en kbit/s (défaut : 64)")
    p.add_argument(
        "--decoupage",
        choices=("unique", "chapitres"),
        help="un seul fichier, ou un fichier par chapitre dans un dossier",
    )
    p.add_argument("--pages", metavar="PAGES", help='pages à lire, par exemple "1-10,15"')
    p.add_argument("--notes", choices=("ignorer", "texte", "fin"), help="notes de bas de page")
    p.add_argument(
        "--ocr", choices=("auto", "jamais", "toujours"), help="reconnaissance de texte des pages scannées"
    )
    p.add_argument("--sans-titres", action="store_true", help="ne pas annoncer les titres")
    p.add_argument(
        "--texte", metavar="FICHIER.txt", help="exporte le texte qui serait lu, au lieu de l'audio"
    )
    p.add_argument("--liste-voix", action="store_true", help="affiche les voix disponibles et quitte")
    p.add_argument("--diagnostic", action="store_true", help="vérifie l'installation et quitte")
    p.add_argument("--silencieux", action="store_true", help="n'affiche pas la progression")
    p.add_argument("--version", action="version", version=f"voxpage {__version__}")
    return p


class _ArgError(Exception):
    pass


def _apply_options(s: settings.Settings, a: argparse.Namespace) -> None:
    if a.voix is not None:
        s.voice_id = a.voix
    if a.locuteur is not None:
        if a.locuteur < 0:
            raise _ArgError("--locuteur doit être positif ou nul.")
        s.speaker = a.locuteur
    if a.vitesse is not None:
        if not 0.5 <= a.vitesse <= 2.0:
            raise _ArgError("--vitesse doit être comprise entre 0.5 et 2.0.")
        s.speed = a.vitesse
    if a.format is not None:
        s.audio.format = a.format
    if a.debit is not None:
        if not 8 <= a.debit <= 320:
            raise _ArgError("--debit doit être compris entre 8 et 320 kbit/s.")
        s.audio.bitrate_kbps = a.debit
    if a.decoupage is not None:
        s.audio.split = "single" if a.decoupage == "unique" else "chapters"
    if a.pages is not None:
        s.extract.pages = a.pages or None
    if a.notes is not None:
        s.extract.footnotes = {"ignorer": "skip", "texte": "inline", "fin": "end_of_chapter"}[a.notes]
    if a.ocr is not None:
        s.extract.ocr = {"auto": "auto", "jamais": "never", "toujours": "always"}[a.ocr]
    if a.sans_titres:
        s.normalize.announce_headings = False


def default_output(input: Path, s: settings.Settings) -> Path:
    """Même nom que l'entrée, à côté, avec l'extension du format."""
    return Path(input).with_suffix("." + s.audio.format)


class _Reporter:
    def __init__(self) -> None:
        stream = getattr(sys, "stderr", None)
        self._tty = bool(stream is not None and hasattr(stream, "isatty") and stream.isatty())
        self._label = ""
        self._decade = -1
        self._open_line = False

    def __call__(self, label: str, fraction: float) -> None:
        pct = int(fraction * 100)
        if self._tty:
            _err(f"\r\x1b[K{label} — {pct} %")
            self._open_line = True
            return
        decade = pct // 10
        if label != self._label or decade != self._decade:
            self._label, self._decade = label, decade
            _err(f"{label} — {pct} %\n")

    def finish(self) -> None:
        if self._open_line:
            _err("\n")
            self._open_line = False


def _list_voices() -> int:
    from voxpage.tts.sherpa import get_engine

    voices = get_engine().list_voices()
    if not voices:
        _out("stdout", "Aucune voix installée.\n")
        return EXIT_OK
    for v in voices:
        extra = f" ({len(v.speakers)} locuteurs)" if len(v.speakers) > 1 else ""
        _out("stdout", f"{v.id}\t{v.lang}\t{v.name}{extra}\n")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse : 0 pour --help/--version, 2 sinon
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    if args.diagnostic:
        from voxpage import diagnostic

        return diagnostic.run()
    if args.liste_voix:
        try:
            return _list_voices()
        except Exception as exc:  # noqa: BLE001
            _err(f"Erreur : {exc}\n")
            return EXIT_ERROR
    if args.entree is None:
        _err(parser.format_usage() + "voxpage : erreur : indiquez le document à convertir.\n")
        return EXIT_USAGE

    s = copy.deepcopy(settings.load())
    try:
        _apply_options(s, args)
    except _ArgError as exc:
        _err(f"voxpage : erreur : {exc}\n")
        return EXIT_USAGE

    source = Path(args.entree)
    reporter = None if args.silencieux else _Reporter()
    cancel = CancelToken()
    previous = None
    try:
        previous = signal.signal(signal.SIGINT, lambda *_: cancel.cancel())
    except ValueError:  # hors du fil principal
        pass
    try:
        if args.texte is not None:
            text = extract_text(source, s, reporter, cancel)
            target = Path(args.texte)
            try:
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise ConversionError(f"Impossible d'écrire « {target} » : {exc.strerror or exc}.") from exc
            if reporter:
                reporter.finish()
            if not args.silencieux:
                _err(f"Texte enregistré : {target}\n")
            return EXIT_OK
        output = Path(args.sortie) if args.sortie else default_output(source, s)
        result = convert(source, output, s, reporter, cancel)
    except Cancelled:
        if reporter:
            reporter.finish()
        _err("Conversion annulée.\n")
        return EXIT_CANCELLED
    except KeyboardInterrupt:
        if reporter:
            reporter.finish()
        _err("Conversion annulée.\n")
        return EXIT_CANCELLED
    except ConversionError as exc:
        if reporter:
            reporter.finish()
        _err(f"Erreur : {exc}\n")
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        if reporter:
            reporter.finish()
        _err(f"Erreur inattendue : {exc}\n")
        return EXIT_ERROR
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)

    if reporter:
        reporter.finish()
    for w in result.warnings:
        _err(f"Avertissement : {w}\n")
    minutes, seconds = divmod(int(result.duration_s), 60)
    for f in result.files:
        _out("stdout", f"{f}\n")
    if not args.silencieux:
        _err(f"Terminé : {minutes} min {seconds:02d} s d'audio.\n")
    return EXIT_OK
