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


class TtsEngine(Protocol):
    def list_voices(self) -> list[Voice]: ...

    def synthesize(
        self, text: str, voice_id: str, speaker: int = 0, speed: float = 1.0
    ) -> tuple[np.ndarray, int]:
        """Retourne (int16 mono, fréquence)."""
        ...
