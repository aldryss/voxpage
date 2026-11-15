"""Représentation d'un document extrait."""

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table", "footnote", "caption"]


@dataclass
class Block:
    kind: BlockKind
    text: str  # texte brut du document, non normalisé pour la voix
    level: int = 0  # niveau de titre (1 = plus haut) ; 0 sinon
    page: int | None = None  # page d'origine, à partir de 1


@dataclass
class Chapter:
    title: str  # "" si le document n'a pas de chapitres
    blocks: list[Block]


@dataclass
class Document:
    title: str
    author: str | None
    lang: str  # "fr" ou "en"
    chapters: list[Chapter]
    warnings: list[str] = field(default_factory=list)  # messages lisibles par l'utilisateur
