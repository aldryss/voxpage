"""Normalisation du texte pour la voix (issue #3).

`normalize()` transforme la structure d'un `Document` en phrases prêtes à être dites, avec leurs pauses.
Règle d'or : la fidélité. On ne réécrit que ce dont on est sûr ; dans le doute, le texte reste tel quel.
"""

import re
from dataclasses import dataclass

from voxpage.document import Block, Document

from . import text as _text
from .sentences import MAX_CHARS, split_long, split_sentences


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


# Pause entre deux morceaux d'une même phrase recoupée : une pause de virgule, plus courte qu'entre phrases.
_CHUNK_PAUSE_MS = 150
_FOOTNOTE_PREFIX = {"fr": "Note : ", "en": "Note: "}


def _lang(doc: Document) -> str:
    return "en" if (doc.lang or "fr").lower().startswith("en") else "fr"


def _pieces(text: str, lang: str) -> list[tuple[str, bool]]:
    """Texte brut d'une ligne/paragraphe -> [(morceau à dire, fin_de_phrase)]."""
    out: list[tuple[str, bool]] = []
    for sentence in split_sentences(text, lang):
        chunks = [c for c in split_long(_text.speak(sentence, lang), MAX_CHARS) if c.strip()]
        for i, chunk in enumerate(chunks):
            out.append((chunk, i == len(chunks) - 1))
    return out


def _block_segments(block: Block, lang: str, opts: NormalizeOptions) -> list[Segment]:
    raw = block.text or ""
    items = [raw] if block.kind != "paragraph" else _text.split_bullet_lines(raw)
    sentence_pause = opts.sentence_pause_ms
    block_pause = opts.heading_pause_ms if block.kind == "heading" else opts.paragraph_pause_ms
    pieces: list[tuple[str, int]] = []  # (texte, pause sauf pour le dernier)

    def add(text: str, kind: str, row_end_pause: int) -> None:
        text = _text.clean_block(text, kind)
        if kind in ("heading", "paragraph", "list_item", "caption", "footnote", "table"):
            text = _text.decaps(text, lang)
        got = _pieces(text, lang)
        for chunk, end in got:
            pieces.append((chunk, sentence_pause if end else min(_CHUNK_PAUSE_MS, sentence_pause)))
        if got:
            pieces[-1] = (pieces[-1][0], row_end_pause)

    if block.kind == "table":
        rows = [re.sub(r"\s*(?:\t|\|)\s*", ", ", row) for row in re.split(r"\n", raw)]
        rows = [re.sub(r"(?:,\s*)+$", "", re.sub(r"^(?:\s*,)+\s*", "", r)) for r in rows]
        for row in rows:
            if row.strip():
                add(row, "table", sentence_pause)
    else:
        for item in items:
            add(item, block.kind, sentence_pause if len(items) > 1 else block_pause)

    pieces = [(t, p) for t, p in pieces if _text.has_content(t)]
    if block.kind == "footnote" and pieces:
        pieces[0] = (_FOOTNOTE_PREFIX[lang] + pieces[0][0], pieces[0][1])
    if pieces:
        pieces[-1] = (pieces[-1][0], block_pause)
    return [Segment(t, p) for t, p in pieces]


def same_title(a: str, b: str) -> bool:
    """Même titre, à la casse et à la ponctuation près."""
    def key(s: str) -> str:
        return re.sub(r"\W+", " ", s.casefold()).strip()

    return bool(key(a)) and key(a) == key(b)


def spoken_title(title: str, lang: str, options: NormalizeOptions | None = None) -> list[str]:
    """Segments dits pour annoncer un titre de chapitre."""
    title = re.sub(r"\s+", " ", title or "").strip()
    lang = "en" if (lang or "fr").lower().startswith("en") else "fr"
    return [s.text for s in _block_segments(Block("heading", title), lang, options or NormalizeOptions())]


def normalize(doc: Document, options: NormalizeOptions) -> list[SpeechChapter]:
    lang = _lang(doc)
    result: list[SpeechChapter] = []
    for chapter in doc.chapters:
        segments: list[Segment] = []
        title = re.sub(r"\s+", " ", chapter.title or "").strip()
        blocks = [b for b in chapter.blocks if (b.text or "").strip()]
        # titre déjà présent en tête de chapitre (éventuellement après un surtitre) : on ne l'annonce pas
        leading = []
        for b in blocks:
            if b.kind != "heading":
                break
            leading.append(b)
        duplicate = any(same_title(title, b.text) for b in leading)
        if options.announce_headings and title and not duplicate:
            segments += _block_segments(Block("heading", title), lang, options)
        for block in blocks:
            if block.kind == "heading" and not options.announce_headings:
                continue
            segments += _block_segments(block, lang, options)
        result.append(SpeechChapter(title=title, segments=segments))
    return result
