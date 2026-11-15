"""Contrat des moteurs de synthèse (implémentation : issue #4)."""

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class Voice:
    id: str  # nom du dossier dans voices/, ex. "fr_FR-siwis-medium"
    name: str  # nom affiché
    lang: str  # "fr", "en"
    speakers: list[str] = field(default_factory=list)  # [] si mono-locuteur


# Voix retenue par langue quand aucun réglage n'est enregistré (voix la plus intelligible à l'aller-retour
# synthèse -> reconnaissance, docs/recette.md), puis première voix de la langue dans l'ordre alphabétique.
DEFAULT_VOICE_IDS = {"fr": "fr_FR-siwis-medium", "en": "en_GB-cori-medium"}


def _lang_code(code: str) -> str:
    return (code or "").lower().replace("-", "_").split("_")[0]


def default_voice(voices: list[Voice], lang: str = "fr") -> Voice | None:
    """Voix par défaut pour une langue : la voix préférée si elle est installée, sinon la première de la
    langue, sinon la première voix."""
    lang = _lang_code(lang) or "fr"
    preferred = DEFAULT_VOICE_IDS.get(lang)
    by_lang = [v for v in voices if _lang_code(v.lang) == lang]
    return next((v for v in by_lang if v.id == preferred), None) or (by_lang or voices or [None])[0]


class TtsEngine(Protocol):
    def list_voices(self) -> list[Voice]: ...

    def synthesize(
        self, text: str, voice_id: str, speaker: int = 0, speed: float = 1.0
    ) -> tuple[np.ndarray, int]:
        """Retourne (int16 mono, fréquence)."""
        ...
