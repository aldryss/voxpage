"""Découpage en phrases et recoupage des phrases trop longues."""

import re

from . import en, fr

MAX_CHARS = 400

_UPPER_START = "A-ZÀ-ÖØ-Þ"
# fin de phrase candidate : ponctuation, fermants éventuels, espace
_END = re.compile(r"([.!?…]+)((?:\s?[\"»”’')\]])*)(\s+)")
_OPENERS = "\"«“‘'([—–-¿¡"
_DOTTED = re.compile(r"^(?:[^\W\d_]\.)+[^\W\d_]$")
_INITIALS_ONLY = re.compile(r"^[A-ZÀ-ÖØ-Þ]$")


def _rules(lang: str):
    return en if lang == "en" else fr


def _prev_token(text: str, end: int) -> str:
    """Mot juste avant la position `end` (sans le point final)."""
    start = end
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    token = text[start:end].lstrip("\"«“‘'([")
    return re.split(r"['’]", token)[-1] if re.search(r"['’]\w", token) else token


def _is_boundary(text: str, m: re.Match, lang: str) -> bool:
    rules = _rules(lang)
    nxt = text[m.end():m.end() + 1]
    if not nxt:
        return False
    punct = m.group(1)
    if nxt.islower():
        return False
    if not (nxt.isupper() or nxt.isdigit() or nxt in _OPENERS):
        return False
    if punct[0] in "!?":
        return True
    if punct.startswith("…") or len(punct) >= 2:  # points de suspension
        return nxt.isupper() or nxt in _OPENERS
    token = _prev_token(text, m.start())
    low = token.lower()
    if _INITIALS_ONLY.match(token):
        return False
    if _DOTTED.match(token) and low not in {"j.-c"}:
        return False
    if low in rules.CAN_END:
        return True
    if token.endswith("J.-C") or low == "j.-c":
        return True
    if low in rules.NO_BREAK:
        return False
    if low in {"av", "apr"}:
        return False
    return True


def split_sentences(text: str, lang: str = "fr") -> list[str]:
    """Découpe `text` en phrases ; dans le doute, ne coupe pas."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for m in _END.finditer(text):
        if _is_boundary(text, m, lang):
            end = m.start(3)
            sentences.append(text[start:end].strip())
            start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]


def split_long(sentence: str, limit: int = MAX_CHARS) -> list[str]:
    """Recoupe une phrase de plus de `limit` caractères à une virgule/point-virgule (sinon à un espace)."""
    sentence = sentence.strip()
    pieces: list[str] = []
    while len(sentence) > limit:
        window = sentence[: limit + 1]
        cut = -1
        for m in re.finditer(r"[,;:]\s", window):
            if m.end() - 1 <= limit and m.start() >= limit // 4:
                cut = m.end()
        if cut == -1:
            for m in re.finditer(r"[,;:]\s", window):
                if m.end() - 1 <= limit:
                    cut = m.end()
        if cut == -1:
            sp = window.rfind(" ")
            cut = sp + 1 if sp > 0 else limit
        piece, sentence = sentence[:cut].strip(), sentence[cut:].strip()
        if piece:
            pieces.append(piece)
    if sentence:
        pieces.append(sentence)
    return pieces
