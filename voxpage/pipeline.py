"""Chaîne complète fichier -> audio (issue #6)."""

from dataclasses import dataclass, field
from pathlib import Path

from voxpage.progress import CancelToken, ProgressCb
from voxpage.settings import Settings


@dataclass
class ConvertResult:
    files: list[Path]
    duration_s: float
    warnings: list[str] = field(default_factory=list)


def convert(
    input: Path,
    output: Path,
    settings: Settings,
    progress: ProgressCb | None = None,
    cancel: CancelToken | None = None,
) -> ConvertResult:
    raise NotImplementedError("convert() : voir l'issue #6")


def extract_text(
    input: Path,
    settings: Settings,
    progress: ProgressCb | None = None,
    cancel: CancelToken | None = None,
) -> str:
    raise NotImplementedError("extract_text() : voir l'issue #6")
