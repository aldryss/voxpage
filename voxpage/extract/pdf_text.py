"""Nettoyage du texte extrait d'un PDF : caractères parasites, ligatures, césures de fin de ligne.

Règle de recollage des césures (fonction `keep_hyphen`), appliquée quand une ligne se termine par un
trait d'union collé à une lettre et que la suivante commence par un mot :

1. le mot suivant ne commence pas par une lettre minuscule (« Jean-/Pierre », « 1914-/1918 ») → on garde ;
2. la partie gauche contient déjà un trait d'union (« c'est-à-/dire », « arc-en-/ciel »), ou le mot de
   droite est lui-même suivi d'un trait d'union (« Île-/de-France ») → on garde ;
3. le document lui-même tranche : si la forme avec trait d'union apparaît ailleurs (hors fin de ligne)
   plus souvent que la forme soudée, on garde ; dans le cas inverse, on soude ;
4. éléments de composés connus (« peut-/être », « dit-/il », « après-/midi », « self-/evident ») ou
   préfixe terminé par la voyelle qui commence le mot suivant (« anti-/inflammatoire ») → on garde ;
5. sinon c'est une césure typographique : on soude (« transcrip-/tion » → « transcription »).

Un tiret conditionnel (U+00AD) en fin de ligne est toujours une césure : on soude.
"""

import re
import unicodedata
from collections import Counter

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u0132": "IJ",
    "\u0133": "ij",
}

# Puces des polices Symbol/Wingdings mal décodées (zone privée) : on les ramène à une puce standard.
PUA_BULLETS = {"\uf0b7", "\uf0a7", "\uf076", "\uf0d8", "\uf0fc", "\uf0a8", "\uf06e", "\uf0e0", "\uf02d"}

HYPHENS = "-\u2010\u2011"
SOFT_HYPHEN = "\u00ad"
_CID = re.compile(r"^\(cid:\d+\)$")
_SPACES = re.compile(r"[ \t]+")

# Seconds éléments de composés : mots courts qui suivent un trait d'union (« peut-être », « dit-il »).
_RIGHT_KEEP = frozenset(
    "t y en le la il on je tu ce ci là ils elle elles nous vous moi toi lui être dire même mêmes "
    "delà deçà dessus dessous dedans dehors".split()
)
# Premiers éléments de composés fréquents.
_LEFT_KEEP = frozenset(
    "après avant arrière au demi semi mi non quasi sous vice ex grand grands grande grandes arc chef "
    "porte garde nord sud franco anglo gréco judéo italo germano hispano afro self well half".split()
)
_VOWELS = "aeiouyàâäéèêëîïôöùûü"
_ELISION = re.compile(r"^(?:[a-zà-ÿ]{1,3}['’])", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")


def is_unknown_glyph(text: str) -> bool:
    """Glyphe sans correspondance Unicode (pdfminer renvoie « (cid:N) »)."""
    return bool(_CID.match(text))


def clean_char(ch: str) -> str:
    """Nettoie un caractère isolé ; renvoie "" s'il doit disparaître.

    Le tiret conditionnel est conservé ici : son sort dépend de sa position dans la ligne.
    """
    if not ch:
        return ""
    if len(ch) > 1:
        return "".join(clean_char(c) for c in ch)
    if ch in LIGATURES:
        return LIGATURES[ch]
    if ch in PUA_BULLETS:
        return "•"
    if ch == SOFT_HYPHEN:
        return ch
    cat = unicodedata.category(ch)
    if cat == "Zs" or ch in "\t\n\r\x0b\x0c":
        return " "
    if cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
        return ""
    return ch


def clean_text(text: str) -> str:
    """Nettoyage final d'un texte de bloc : tirets conditionnels restants, espaces, NFC."""
    text = "".join(clean_char(c) for c in text).replace(SOFT_HYPHEN, "")
    text = unicodedata.normalize("NFC", text)
    return _SPACES.sub(" ", text).strip()


class WordStats:
    """Fréquence des mots du document, pour trancher les césures ambiguës (règle 3)."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def add_line(self, line: str) -> None:
        words = _WORD.findall(unicodedata.normalize("NFC", line))
        if line.rstrip().endswith(tuple(HYPHENS + SOFT_HYPHEN)) and words:
            words = words[:-1]  # le dernier mot est coupé : il ne compte pas
        self.counts.update(w.lower() for w in words)

    def add_line_after_break(self, line: str) -> None:
        """Ligne qui suit une coupure : son premier mot est un fragment, on l'ignore."""
        words = _WORD.findall(unicodedata.normalize("NFC", line))
        self.counts.update(w.lower() for w in words[1:])


def _left_word(text: str) -> str:
    m = re.search(r"([^\W\d_]+(?:[-'’][^\W\d_]*)*)[" + HYPHENS + r"]$", text)
    return m.group(1) if m else ""


def _right_word(text: str) -> str:
    m = re.match(r"([^\W\d_]+)", text)
    return m.group(1) if m else ""


def keep_hyphen(left: str, right: str, stats: WordStats | None = None) -> bool:
    """Faut-il garder le trait d'union entre `left` (fin de ligne) et `right` (début de la suivante) ?

    `left` est le mot avant le trait d'union (sans lui), `right` le premier mot de la ligne suivante.
    """
    if not right or not right[0].islower():
        return True  # règle 1
    if not left:
        return True
    core = _ELISION.sub("", left)
    if any(h in core for h in HYPHENS):
        return True  # règle 2
    if stats is not None:
        hyph = stats.counts[f"{core}-{right}".lower()]
        joined = stats.counts[f"{core}{right}".lower()]
        if hyph > joined:
            return True  # règle 3
        if joined > hyph:
            return False
    low_left, low_right = core.lower(), right.lower()
    if low_right in _RIGHT_KEEP or low_left in _LEFT_KEEP:
        return True  # règle 4
    if low_left and low_left[-1] in _VOWELS and low_right[0] == low_left[-1]:
        return True  # « anti-inflammatoire », « micro-ondes »
    return False  # règle 5


def join_lines(prev: str, nxt: str, stats: WordStats | None = None) -> str:
    """Recolle deux lignes consécutives d'un même bloc."""
    prev = prev.rstrip()
    nxt = nxt.lstrip()
    if not prev:
        return nxt
    if not nxt:
        return prev
    if prev.endswith(SOFT_HYPHEN):
        return prev[:-1] + nxt
    if prev[-1] in HYPHENS and len(prev) >= 2 and not prev[-2].isspace() and not prev[-2].isalpha():
        return prev + nxt  # « 1914-/1918 » : trait d'union gardé, sans espace
    if prev[-1] in HYPHENS and len(prev) >= 2 and prev[-2].isalpha():
        left = _left_word(prev)
        right = _right_word(nxt)
        compound_goes_on = nxt[len(right) : len(right) + 1] in tuple(HYPHENS) and bool(right)
        if compound_goes_on or keep_hyphen(left, right, stats):  # « Île-/de-France »
            return prev[:-1] + "-" + nxt
        return prev[:-1] + nxt
    if prev[-1] in "/" and re.search(r"(?:https?://|www\.)\S*$", prev):
        return prev + nxt  # adresse web coupée en fin de ligne
    return prev + " " + nxt


def ends_with_break_hyphen(text: str) -> bool:
    text = text.rstrip()
    return bool(text) and (
        text[-1] == SOFT_HYPHEN or (text[-1] in HYPHENS and len(text) > 1 and text[-2].isalpha())
    )
