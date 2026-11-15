"""Détection fr/en par mots-outils, sans dépendance."""

import re

_FR = frozenset(
    "le la les un une des du de et est en que qui dans pour pas sur au aux avec ce cette ces il elle "
    "ils elles nous vous je tu ne se son sa ses leur leurs mais ou où par plus comme été sont être "
    "fait cela ça très aussi tout tous".split()
)
_EN = frozenset(
    "the a an of and is are was were to in that it for not on with as this these those he she they we "
    "you i his her their but or by from at be been have has had which what there would will can all "
    "more also".split()
)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_lang(text: str) -> str:
    """Retourne "fr" ou "en" ; "fr" en cas d'égalité ou de texte vide."""
    fr = en = 0
    for word in _WORD.findall(text.lower()):
        if word in _FR:
            fr += 1
        if word in _EN:
            en += 1
    return "en" if en > fr else "fr"
