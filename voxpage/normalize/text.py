"""Nettoyage et réécriture d'une phrase pour la voix (tout est dans `speak`)."""

import re

from . import acronyms, en, fr, numbers

_SPACES = "    "
_UP = "A-ZÀ-ÖØ-Þ"
_BULLETS = "•▪◦●■□‣⁃·∙◆◇►▸➢✓✔"
_VOWELS = set("aeiouyàâäéèêëîïôöùûüÿœæAEIOUYÀÂÄÉÈÊËÎÏÔÖÙÛÜŸŒÆ")


def _rules(lang: str):
    return en if lang == "en" else fr


# --------------------------------------------------------------------------- nettoyage de bloc

_INVISIBLE = re.compile("[­​‌‍⁠﻿\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
_REF = re.compile(r"[ ]?\[\d{1,3}(?:\s?[,\-–]\s?\d{1,3})*\]")
_LINE_BULLET = re.compile(rf"(?:^|\n)[ \t]*[{re.escape(_BULLETS)}][ \t]*")


def split_bullet_lines(text: str) -> list[str]:
    """Un texte dont plusieurs lignes commencent par une puce devient plusieurs éléments."""
    if "\n" not in text or not re.search(rf"\n[ \t]*[{re.escape(_BULLETS)}]", text):
        return [text]
    parts = re.split(rf"(?:^|\n)[ \t]*[{re.escape(_BULLETS)}][ \t]*", text)
    return [p for p in parts if p.strip()] or [text]


def clean_block(text: str, kind: str = "paragraph") -> str:
    """Espaces, caractères invisibles, puces de début, appels de note « [12] »."""
    text = _INVISIBLE.sub("", text)
    text = text.replace(" ", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    text = _REF.sub("", text)
    # appel de note collé au mot (« distribués(3) », « TAAF)(1) ») : la note n'est pas lue, l'appel non plus
    text = re.sub(r"(?:(?<=[^\W\d_])|(?<=[)»”\"]))\(\d{1,2}\)(?=[\s.,;:)/]|$)", "", text)
    # points de conduite d'une table des matières (« Délibéré........ 5 ») : une simple pause
    text = re.sub(r"\s*(?:[.…·]\s?){4,}\s*", ", ", text).strip(" ,")
    # puces
    text = re.sub(rf"^[{re.escape(_BULLETS)}]\s*", "", text)
    if kind == "list_item":
        text = re.sub(r"^[-–—*]\s+", "", text)
        # numérotation « 1. », « 2) », « a) » : on la garde, sans que le point coupe la phrase
        text = re.sub(r"^\(?(\d{1,3})[.)]\s+(?=\S)", r"\1, ", text)
        text = re.sub(r"^\(?([a-z])\)\s+(?=\S)", r"\1, ", text)
    else:
        text = re.sub(rf"^(\d{{1,2}})\.\s+(?=[{_UP}])", r"\1, ", text)
    return text.strip()


# --------------------------------------------------------------------------- TOUT EN MAJUSCULES

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def decaps(text: str, lang: str) -> str:
    """Ramène un texte TOUT EN MAJUSCULES en casse normale (sigles et chiffres romains conservés)."""
    if not _is_all_caps(text):
        return text
    r = _rules(lang)
    short = r.SHORT_WORDS | {w.upper() for w in r.SHORT_WORDS}

    def rep(m: re.Match) -> str:
        t = m.group(0)
        if len(t) == 1:
            nxt = m.string[m.end():m.end() + 1]
            return t if (t in "IVX" and nxt not in ("'", "’")) else t.lower()
        if numbers.roman_to_int(t) is not None and len(t) >= 2:
            return t
        if not any(c in _VOWELS for c in t):
            return t
        if len(t) >= 5 or t.lower() in short:
            return t.lower()
        return t

    out = _WORD.sub(rep, text)
    # majuscule en début de texte et de phrase
    out = re.sub(r"^([^\w]*)([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), out)
    return re.sub(r"([.!?…]\s+[^\w]*)([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), out)


# --------------------------------------------------------------------------- URL et courriels

_URL = re.compile(r"(?:https?://|ftp://|www\.)[^\s<>\"«»]+", re.I)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TRAIL = ".,;:!?)]}'\"»”’"


def _spell(s: str, lang: str) -> str:
    sep = _rules(lang).URL_SEP
    parts = re.split(r"([./\-_?=&#~:@+%])", s)
    out = []
    for p in parts:
        if not p:
            continue
        if p in sep:
            out.append(sep[p])
        elif p.lower() == "www":
            out.append(_rules(lang).URL_WWW)
        else:
            out.append(p)
    return " ".join(out)


def urls_and_emails(text: str, lang: str) -> str:
    def url(m: re.Match) -> str:
        s = m.group(0)
        trail = ""
        while s and s[-1] in _TRAIL:
            trail = s[-1] + trail
            s = s[:-1]
        s = re.sub(r"^(?:https?|ftp)://", "", s, flags=re.I)
        return _spell(s, lang) + trail

    text = _URL.sub(url, text)
    return _EMAIL.sub(lambda m: _spell(m.group(0), lang), text)


# --------------------------------------------------------------------------- phrase complète

def _etc(text: str, lang: str) -> str:
    word = _rules(lang).ETC
    text = re.sub(r"\betc\.(?=\s*$)", f"{word}.", text)
    text = re.sub(r"\betc(?:\.\.\.|…)", f"{word}...", text)
    text = re.sub(r"\betc\.(?=\s*[)\"»”]*\s*$)", f"{word}.", text)
    return re.sub(r"\betc\.", word, text)


def _quotes(text: str) -> str:
    text = re.sub(r"«\s*", '"', text)
    text = re.sub(r"\s*»", '"', text)
    text = text.replace("“", '"').replace("”", '"').replace("„", '"')
    return text.replace("’", "'").replace("‘", "'")


_SPACED_SIGN = re.compile(
    r"(?:(?<=^)|(?<=[(;:])|(?<=[(;:] )|(?<=\bde )|(?<=\bà )|(?<=\bsoit )|(?<=\bet )|(?<=\bou ))([-−+]) (?=\d)"
)


def _spaced_sign(text: str, lang: str) -> str:
    """Signe séparé de son nombre (« (+ 5,7 %) », « inférieur de - 0,3 % », cellule « - 2,9 ») : il se dit.
    Jamais entre deux nombres (« 2010 - 2020 ») ni après un tiret de titre (« A - Une activité »)."""
    words = {"+": "plus"}
    minus = "moins" if lang == "fr" else "minus"
    return _SPACED_SIGN.sub(lambda m: words.get(m.group(1), minus) + " ", text)


def speak(sentence: str, lang: str) -> str:
    """Réécrit une phrase (ou un fragment) pour la synthèse vocale."""
    r = _rules(lang)
    t = sentence
    t = urls_and_emails(t, lang)
    t = numbers.merge_thousands(t, lang)
    t = numbers.phones(t, lang)
    t = numbers.dates(t, lang)
    t = numbers.times(t, lang)
    t = _etc(t, lang)
    for pat, rep in r.ABBREVIATIONS:
        t = pat.sub(rep, t)
    t = numbers.ranges(t, lang)
    if lang == "fr":
        # « loi n° 88-1028 » : numéro composé, entendu « 80.1028 » sans le tiret dit (aller-retour)
        t = re.sub(r"\b([Nn]uméros? )(\d+)-(\d+)\b", r"\1\2 tiret \3", t)
    t = numbers.fractions(t, lang)
    t = numbers.money(t, lang)
    t = numbers.percents(t, lang)
    t = numbers.enumeration_degree(t, lang)
    t = numbers.legal_item(t, lang)
    t = numbers.units(t, lang)
    t = numbers.ordinals(t, lang)
    t = numbers.romans(t, lang)
    t = acronyms.spell_acronyms(t, lang)
    t = _spaced_sign(t, lang)
    t = numbers.decimals(t, lang)
    for pat, rep in r.SYMBOLS:
        t = pat.sub(rep, t)
    t = _quotes(t)
    t = re.sub(f"[ {_SPACES}\t]+", " ", t)
    t = re.sub(r"\s+([,.)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t).strip()
    first = sentence.lstrip("\"«“([ ")[:1]
    if first.isupper() and t[:1].islower():
        t = t[0].upper() + t[1:]
    return t.strip()


def has_content(text: str) -> bool:
    """Faux si le segment ne contient que de la ponctuation / des espaces."""
    return any(c.isalnum() for c in text)
