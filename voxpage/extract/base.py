"""Contrat des extracteurs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from voxpage.document import Document
from voxpage.progress import CancelToken, ProgressCb


class UnsupportedFormat(Exception):
    """Aucun extracteur n'est enregistré pour ce format."""


class ExtractError(Exception):
    """Le document ne peut pas être lu (protégé, endommagé, vide…) ; le message s'adresse à l'utilisateur."""


@dataclass
class ExtractOptions:
    ocr: Literal["auto", "never", "always"] = "auto"
    footnotes: Literal["skip", "inline", "end_of_chapter"] = "skip"
    pages: str | None = None  # "1-10,15" ; None = tout


class Extractor(Protocol):
    extensions: tuple[str, ...]  # (".pdf",)

    def extract(
        self,
        path: Path,
        options: ExtractOptions,
        progress: ProgressCb | None = None,
        cancel: CancelToken | None = None,
    ) -> Document: ...
