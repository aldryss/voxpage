"""Chaîne complète fichier -> audio (issue #6)."""

from dataclasses import dataclass, field
from pathlib import Path

from voxpage.audio import AudioError, AudioWriter
from voxpage.document import Document
from voxpage.extract import UnsupportedFormat, extractor_for
from voxpage.extract.base import ExtractError
from voxpage.normalize import SpeechChapter, normalize, spoken_title
from voxpage.normalize.lexicon import LexiconSource, LoadedLexicon
from voxpage.normalize.text import has_content
from voxpage.progress import Cancelled, CancelToken, ProgressCb
from voxpage.settings import Settings
from voxpage.tts.base import TtsEngine, Voice, default_voice

EXTRACT_SHARE = 0.10  # part de la progression consacrée à la lecture du document
_QUOTE_MAX = 80
_SILENT_MAX = 5  # passages muets cités nommément dans les avertissements


class ConversionError(Exception):
    """Erreur prévue de conversion ; le message est destiné à l'utilisateur (en français)."""


@dataclass
class ConvertResult:
    files: list[Path]
    duration_s: float
    warnings: list[str] = field(default_factory=list)


class _Progress:
    """Rapporte une progression monotone, bornée à [0, 1]."""

    def __init__(self, callback: ProgressCb | None) -> None:
        self._callback = callback
        self._last = 0.0

    def __call__(self, label: str, fraction: float) -> None:
        self._last = max(self._last, min(1.0, max(0.0, fraction)))
        if self._callback:
            self._callback(label, self._last)


def _read_document(
    input: Path, settings: Settings, report: _Progress, share: float, cancel: CancelToken | None
) -> Document:
    path = Path(input)
    if not path.is_file():
        raise ConversionError(f"Le fichier « {path} » est introuvable.")
    try:
        extractor = extractor_for(path)
    except UnsupportedFormat as exc:
        raise ConversionError(str(exc)) from exc
    report("Lecture du document", 0.0)
    try:
        doc = extractor.extract(
            path,
            settings.extract,
            lambda label, f: report(label or "Lecture du document", share * f),
            cancel,
        )
    except (Cancelled, ConversionError):
        raise
    except ExtractError as exc:  # message déjà rédigé pour l'utilisateur (il cite le fichier)
        message = str(exc).strip()
        raise ConversionError(message or f"Impossible de lire « {path.name} ».") from exc
    except OSError as exc:
        raise ConversionError(f"Impossible de lire « {path.name} » : {exc.strerror or exc}.") from exc
    except Exception as exc:
        message = str(exc).strip()
        raise ConversionError(
            f"Impossible de lire « {path.name} »" + (f" : {message}" if message else ".")
        ) from exc
    report("Lecture du document", share)
    return doc


def _load_lexicon(doc: Document, source: LexiconSource | None) -> LoadedLexicon:
    """Dictionnaire de prononciation de la langue du document (livré + utilisateur, ou celui demandé)."""
    lang = "en" if (doc.lang or "fr").lower().startswith("en") else "fr"
    return (source or LexiconSource()).load(lang)


def _speech(doc: Document, settings: Settings, lexicon: LoadedLexicon) -> list[SpeechChapter]:
    chapters = normalize(doc, settings.normalize, lexicon.lexicon)
    if not any(seg.text.strip() for ch in chapters for seg in ch.segments):
        raise ConversionError("Ce document ne contient aucun texte lisible.")
    return chapters


def _lang_of(code: str) -> str:
    return (code or "").lower().replace("-", "_").split("_")[0]


def _choose_voice(engine: TtsEngine, settings: Settings, doc: Document) -> tuple[Voice, list[str]]:
    voices = engine.list_voices()
    if not voices:
        raise ConversionError("Aucune voix n'est installée (dossier « voices » vide ou introuvable).")
    warnings: list[str] = []
    doc_lang = _lang_of(doc.lang)
    if settings.voice_id:
        voice = next((v for v in voices if v.id == settings.voice_id), None)
        if voice is None:
            raise ConversionError(
                f"La voix « {settings.voice_id} » est introuvable. Voix disponibles : "
                + ", ".join(v.id for v in voices)
                + "."
            )
        if doc_lang and _lang_of(voice.lang) != doc_lang:
            warnings.append(
                f"La voix « {voice.name} » ({voice.lang}) ne correspond pas à la langue du document "
                f"({doc.lang}) : la prononciation risque d'être mauvaise."
            )
    else:
        voice = default_voice(voices, doc_lang or "fr") or voices[0]
    if not 0 <= settings.speaker < max(1, len(voice.speakers)):
        raise ConversionError(f"Le locuteur {settings.speaker} n'existe pas pour la voix « {voice.name} ».")
    return voice, warnings


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _QUOTE_MAX else text[: _QUOTE_MAX - 1].rstrip() + "…"


def _synthesize(engine: TtsEngine, text: str, voice: Voice, settings: Settings):
    last: Exception | None = None
    for _ in range(2):  # une nouvelle tentative, puis erreur explicite
        try:
            return engine.synthesize(text, voice.id, settings.speaker, settings.speed)
        except Exception as exc:  # noqa: BLE001 - tout échec moteur est traité pareil
            last = exc
    detail = str(last).strip() or type(last).__name__
    raise ConversionError(
        f"La synthèse vocale a échoué sur le passage « {_quote(text)} » : {detail}"
    ) from last


def convert(
    input: Path,
    output: Path,
    settings: Settings,
    progress: ProgressCb | None = None,
    cancel: CancelToken | None = None,
    engine: TtsEngine | None = None,
    pronunciations: LexiconSource | None = None,
) -> ConvertResult:
    """`pronunciations` : origine du dictionnaire de prononciation (défaut : livré + utilisateur)."""
    report = _Progress(progress)
    doc = _read_document(input, settings, report, EXTRACT_SHARE, cancel)
    lexicon = _load_lexicon(doc, pronunciations)
    chapters = _speech(doc, settings, lexicon)
    if cancel:
        cancel.raise_if_cancelled()
    if engine is None:
        from voxpage.tts.sherpa import get_engine

        engine = get_engine()
    voice, warnings = _choose_voice(engine, settings, doc)
    warnings = [*doc.warnings, *lexicon.warnings(), *warnings]

    total_chars = sum(len(s.text) + 1 for ch in chapters for s in ch.segments) or 1
    done_chars = 0
    silent: list[str] = []  # passages porteurs de texte pour lesquels le moteur n'a produit aucun son
    try:
        writer = AudioWriter(Path(output), settings.audio, doc.title, doc.author)
    except AudioError as exc:
        raise ConversionError(str(exc)) from exc
    try:
        for index, chapter in enumerate(chapters, start=1):
            label = "Synthèse vocale"
            if len(chapters) > 1:
                label += f" — chapitre {index} sur {len(chapters)}"
            writer.start_chapter(chapter.title)
            for segment in chapter.segments:
                if cancel:
                    cancel.raise_if_cancelled()
                if segment.text.strip():
                    samples, rate = _synthesize(engine, segment.text, voice, settings)
                    if len(samples) == 0 and has_content(segment.text):
                        silent.append(segment.text)
                    writer.write(samples, rate)
                    writer.write_silence(segment.pause_after_ms)
                done_chars += len(segment.text) + 1
                report(label, EXTRACT_SHARE + (1 - EXTRACT_SHARE) * done_chars / total_chars)
        report("Finalisation du fichier audio", 0.99)
        files = writer.close()
    except BaseException as exc:
        writer.abort()
        if isinstance(exc, AudioError):
            raise ConversionError(str(exc)) from exc
        raise
    if not files:
        raise ConversionError("La synthèse n'a produit aucun son.")
    if silent:
        quoted = " ; ".join(f"« {_quote(t)} »" for t in silent[:_SILENT_MAX])
        more = f" (et {len(silent) - _SILENT_MAX} autre(s))" if len(silent) > _SILENT_MAX else ""
        warnings.append(
            f"{len(silent)} passage(s) n'ont produit aucun son et manquent dans l'audio : {quoted}{more}."
        )
    report("Terminé", 1.0)
    return ConvertResult(files=files, duration_s=writer.duration_s, warnings=warnings)


def extract_text(
    input: Path,
    settings: Settings,
    progress: ProgressCb | None = None,
    cancel: CancelToken | None = None,
    warnings: list[str] | None = None,
    pronunciations: LexiconSource | None = None,
) -> str:
    """Texte tel qu'il sera dit : un segment par ligne, chapitres séparés par leur titre.

    La ligne « == Titre == » tient lieu de l'annonce du titre quand celui-ci est dit en tête de chapitre
    (il n'est pas répété sur la ligne suivante). Les avertissements de lecture (OCR, pages ignorées…) sont
    ajoutés à `warnings` si on en fournit une liste."""
    report = _Progress(progress)
    doc = _read_document(input, settings, report, 0.9, cancel)
    lexicon = _load_lexicon(doc, pronunciations)
    if warnings is not None:
        warnings.extend(doc.warnings)
        warnings.extend(lexicon.warnings())
    report("Préparation du texte", 0.95)
    chapters = _speech(doc, settings, lexicon)
    parts = []
    for chapter in chapters:
        lines = [s.text for s in chapter.segments if s.text.strip()]
        if chapter.title:
            said = spoken_title(chapter.title, doc.lang, settings.normalize, lexicon.lexicon)
            if said and lines[: len(said)] == said:
                del lines[: len(said)]  # le titre est dit en tête de chapitre : la ligne « == … == » le porte
            lines.insert(0, f"== {chapter.title} ==")
        if lines:
            parts.append("\n".join(lines))
    report("Terminé", 1.0)
    return "\n\n".join(parts) + "\n"
