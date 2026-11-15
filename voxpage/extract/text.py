"""Extracteur de fichiers texte brut."""

import re
from pathlib import Path

from voxpage.document import Block, Chapter, Document
from voxpage.extract.base import ExtractOptions
from voxpage.lang import detect_lang
from voxpage.progress import CancelToken, ProgressCb

_BLANK_LINES = re.compile(r"\n\s*\n")


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("cp1252", errors="replace")


class TextExtractor:
    extensions = (".txt",)

    def extract(
        self,
        path: Path,
        options: ExtractOptions,
        progress: ProgressCb | None = None,
        cancel: CancelToken | None = None,
    ) -> Document:
        if progress:
            progress("Lecture du fichier texte", 0.0)
        text = decode(Path(path).read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
        if cancel:
            cancel.raise_if_cancelled()
        blocks = []
        for chunk in _BLANK_LINES.split(text):
            paragraph = " ".join(chunk.split())
            if paragraph:
                blocks.append(Block("paragraph", paragraph))
        if progress:
            progress("Lecture du fichier texte", 1.0)
        lang = detect_lang(" ".join(b.text for b in blocks))
        return Document(Path(path).stem, None, lang, [Chapter("", blocks)], [])
