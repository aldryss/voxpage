"""Logique de l'interface, sans dépendance à wx (testable partout)."""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SPEED_MIN = 0.5
SPEED_MAX = 2.0
SLIDER_MIN = 5  # dixièmes
SLIDER_MAX = 20

FORMATS = (("mp3", "MP3"), ("wav", "WAV"))
SPLITS = (("single", "Un seul fichier"), ("chapters", "Un fichier par chapitre"))
FOOTNOTES = (
    ("skip", "Ignorer"),
    ("inline", "Lire dans le texte"),
    ("end_of_chapter", "Lire en fin de chapitre"),
)
OCR_MODES = (("auto", "Automatique"), ("never", "Jamais"), ("always", "Toujours"))

# Libellés avec accélérateur (&). Clé = identifiant du contrôle. Le nom accessible est le libellé
# sans « & » ni « : » final.
LABELS = {
    "input": "&Fichier à convertir",
    "browse": "Parcour&ir…",
    "output": "Fichier de &sortie",
    "output_btn": "C&hoisir la sortie…",
    "voice": "&Voix",
    "speaker": "&Locuteur",
    "speed": "Vi&tesse",
    "format": "For&mat",
    "split": "&Découpage",
    "footnotes": "&Notes de bas de page",
    "ocr": "Reconnaissance de texte (&OCR)",
    "preview": "Éco&uter un extrait",
    "convert": "&Convertir",
    "cancel": "&Annuler",
    "export": "E&xporter le texte…",
    "pron": "&Prononciations…",
    "open_folder": "Ouvrir le dossi&er",
    "status": "&Résultat",
}

SHORTCUTS_HELP = (
    "Raccourcis clavier\n\n"
    "Ctrl+O : choisir le fichier à convertir\n"
    "Ctrl+Entrée : lancer la conversion\n"
    "Échap : annuler la conversion en cours\n"
    "F1 : afficher cette aide\n"
    "Tab et Maj+Tab : passer d'un contrôle à l'autre\n"
    "Alt + lettre soulignée : aller directement au contrôle correspondant\n\n"
    "Vous pouvez aussi glisser un fichier sur la fenêtre.\n"
    "« Prononciations » ouvre le dictionnaire où l'on précise comment lire un mot, un nom ou un sigle.\n"
    "« Exporter le texte » enregistre le texte qui sera lu, pour le vérifier avant de convertir."
)


def plain_label(label: str) -> str:
    """Libellé sans accélérateur ni deux-points final (nom accessible)."""
    return label.replace("&", "").rstrip(" :")


def accelerator(label: str) -> str | None:
    m = re.search(r"&(.)", label)
    return m.group(1).lower() if m else None


def duplicate_accelerators(labels: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for label in labels:
        key = accelerator(label)
        if key is None:
            continue
        if key in seen and key not in dup:
            dup.append(key)
        seen.add(key)
    return dup


def build_file_filter(extensions: Iterable[str]) -> str:
    """Filtre de boîte de dialogue wx : « Documents (*.pdf;*.txt)|*.pdf;*.txt|Tous (*.*)|*.* »."""
    exts = sorted({"*." + e.lstrip(".").lower() for e in extensions if e.strip(". ")})
    parts = []
    if exts:
        pattern = ";".join(exts)
        parts.append(f"Documents pris en charge ({pattern})|{pattern}")
    parts.append("Tous les fichiers (*.*)|*.*")
    return "|".join(parts)


def suggest_output(input_path: Path, fmt: str, split: str, directory: Path | None = None) -> Path:
    """Sortie proposée à côté de l'entrée : `nom.mp3`, ou dossier `nom` (un fichier par chapitre)."""
    input_path = Path(input_path)
    base = Path(directory) if directory else input_path.parent
    if split == "chapters":
        candidate = base / input_path.stem
        if candidate == input_path:
            candidate = base / f"{input_path.stem} (audio)"
        return candidate
    return base / f"{input_path.stem}.{fmt}"


def format_speed(speed: float) -> str:
    return f"{speed:.1f}".replace(".", ",")


def speed_label(speed: float) -> str:
    return f"Vitesse : {format_speed(speed)}"


def slider_to_speed(value: int) -> float:
    return round(min(max(value, SLIDER_MIN), SLIDER_MAX) / 10, 1)


def speed_to_slider(speed: float) -> int:
    return min(max(round(speed * 10), SLIDER_MIN), SLIDER_MAX)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n < 2 else many}"


def format_duration(seconds: float) -> str:
    """Durée lisible à voix haute : « 1 heure 2 minutes 5 secondes »."""
    total = max(0, round(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    parts = []
    if h:
        parts.append(_plural(h, "heure", "heures"))
    if m:
        parts.append(_plural(m, "minute", "minutes"))
    if s or not parts:
        parts.append(_plural(s, "seconde", "secondes"))
    return " ".join(parts)


@dataclass
class Update:
    percent: int
    message: str | None  # None : ne pas toucher à la ligne d'état
    percent_changed: bool


class ProgressThrottle:
    """Limite les annonces : changement d'étape ou nouveau palier de 10 %."""

    def __init__(self, step_percent: int = 10) -> None:
        self.step_percent = step_percent
        self._step: str | None = None
        self._bucket = -1
        self._percent = -1

    def feed(self, step: str, fraction: float) -> Update:
        percent = min(100, max(0, int(fraction * 100)))
        bucket = percent // self.step_percent
        announce = step != self._step or bucket > self._bucket
        changed = percent != self._percent
        self._step, self._bucket, self._percent = step, max(bucket, self._bucket), percent
        message = f"{step} : {percent} %" if announce else None
        return Update(percent, message, changed)


class UiState(enum.Enum):
    IDLE = "idle"
    CONVERTING = "converting"
    EXPORTING = "exporting"
    SYNTH = "synth"


SETTINGS_KEYS = ("input", "browse", "output", "output_btn", "voice", "speaker", "speed", "format",
                 "split", "footnotes", "ocr")
ALL_KEYS = (*SETTINGS_KEYS, "preview", "convert", "cancel", "export", "pron", "open_folder")


def ui_flags(state: UiState, has_input: bool, has_voice: bool, multi_speaker: bool,
             has_result: bool, playing: bool = False) -> dict[str, bool]:
    """Quels contrôles sont actifs, selon l'état."""
    idle = state is UiState.IDLE
    flags = dict.fromkeys(ALL_KEYS, idle)
    flags["speaker"] = idle and multi_speaker
    flags["voice"] = idle and has_voice
    flags["convert"] = idle and has_input and has_voice
    flags["export"] = idle and has_input
    flags["preview"] = (idle and has_voice) or playing
    flags["cancel"] = state in (UiState.CONVERTING, UiState.EXPORTING)
    flags["open_folder"] = idle and has_result
    return flags


def sample_sentence(lang: str) -> str:
    if lang == "en":
        return "Hello, this is a sample of the selected voice."
    return "Bonjour, ceci est un exemple de la voix sélectionnée."


def describe_error(exc: BaseException) -> str:
    """Message d'erreur en français, jamais une trace Python."""
    if isinstance(exc, NotImplementedError):
        return "Cette fonction n'est pas encore disponible dans cette version."
    if isinstance(exc, FileNotFoundError):
        return f"Fichier introuvable : « {exc.filename or exc} »."
    if isinstance(exc, PermissionError):
        return f"Accès refusé : « {exc.filename or exc} ». Choisissez un autre emplacement."
    if isinstance(exc, MemoryError):
        return "La mémoire disponible est insuffisante pour traiter ce document."
    if isinstance(exc, OSError):
        detail = exc.strerror or str(exc)
        return f"Erreur de lecture ou d'écriture : {detail}"
    if type(exc).__module__.startswith("voxpage") and str(exc):
        return str(exc)  # nos exceptions portent déjà un message en français
    name = type(exc).__name__
    return f"Une erreur inattendue s'est produite ({name}). Réessayez ou essayez un autre fichier."


def result_message(files: list[Path], duration_s: float, warnings: list[str]) -> str:
    lines = ["Conversion terminée.", f"Durée de l'audio : {format_duration(duration_s)}."]
    if not files:
        lines.append("Aucun son n'a été produit : le document ne contient pas de texte à lire.")
    else:
        lines.append(_plural(len(files), "fichier produit", "fichiers produits") + ".")
        lines.append(f"Dossier : {files[0].parent}")
    if warnings:
        lines.append(_plural(len(warnings), "avertissement", "avertissements") + " :")
        lines.extend(f"- {w}" for w in warnings)
    return "\n".join(lines)
