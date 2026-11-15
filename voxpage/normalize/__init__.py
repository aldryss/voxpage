"""Normalisation du texte pour la voix (issue #3)."""

from dataclasses import dataclass

from voxpage.document import Document


@dataclass
class Segment:
    text: str  # une phrase prête à être dite
    pause_after_ms: int


@dataclass
class SpeechChapter:
    title: str
    segments: list[Segment]


@dataclass
class NormalizeOptions:
    announce_headings: bool = True
    sentence_pause_ms: int = 250
    paragraph_pause_ms: int = 700
    heading_pause_ms: int = 1200


def normalize(doc: Document, options: NormalizeOptions) -> list[SpeechChapter]:
    raise NotImplementedError("normalize() : voir l'issue #3")
