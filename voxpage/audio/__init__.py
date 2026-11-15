"""Écriture audio en flux (issue #5)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

_TODO = "AudioWriter : voir l'issue #5"


@dataclass
class AudioOptions:
    format: Literal["mp3", "wav"] = "mp3"
    bitrate_kbps: int = 64  # voix mono : 64 kbit/s suffit
    split: Literal["single", "chapters"] = "single"


class AudioWriter:
    def __init__(self, output: Path, options: AudioOptions, title: str, author: str | None):
        raise NotImplementedError(_TODO)

    def __enter__(self) -> "AudioWriter":
        raise NotImplementedError(_TODO)

    def __exit__(self, *exc) -> None:
        raise NotImplementedError(_TODO)

    def start_chapter(self, title: str) -> None:
        raise NotImplementedError(_TODO)

    def write(self, samples: np.ndarray, sample_rate: int) -> None:
        raise NotImplementedError(_TODO)

    def write_silence(self, ms: int) -> None:
        raise NotImplementedError(_TODO)

    def close(self) -> list[Path]:
        raise NotImplementedError(_TODO)
