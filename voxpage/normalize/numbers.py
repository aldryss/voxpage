"""Nombres, dates, heures, monnaies, unités : réécriture sûre pour la voix.

Chaque fonction prend (texte, langue) et ne réécrit que les motifs sans ambiguïté.
"""

import re
from calendar import monthrange

from num2words import num2words

from . import en, fr

_SPACES = "    "
_UP = "A-ZÀ-ÖØ-Þ"


def _rules(lang: str):
    return en if lang == "en" else fr


def _w(n: int, lang: str) -> str:
    return num2words(n, lang=lang)


# --------------------------------------------------------------------------- chiffres romains

_ROMAN_RE = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int | None:
    """Valeur d'un chiffre romain MAJUSCULE canonique, sinon None."""
    if not s or not _ROMAN_RE.match(s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = _ROMAN_VAL[c]
        if i + 1 < len(s) and _ROMAN_VAL[s[i + 1]] > v:
            total -= v
        else:
            total += v
    return total


def ordinal_words(n: int, lang: str, feminine: bool = False, plural: bool = False) -> str:
    if lang == "en":
        return num2words(n, lang="en", to="ordinal")
    if n == 1:
        w = "première" if feminine else "premier"
    else:
        w = num2words(n, lang="fr", to="ordinal").replace("vingtsième", "vingtième")
    return w + ("s" if plural else "")


# --------------------------------------------------------------------------- milliers

_S = f"[ {_SPACES}]"
_THOUSANDS_MULTI = re.compile(rf"(?<![\d.,])([1-9]\d{{0,2}})((?:{_S}\d{{3}}){{2,}})(?!\d)")
_THOUSANDS_FIN = re.compile(rf"(?<![\d.,])([1-9]\d{{0,2}})([{_SPACES}]\d{{3}})(?!\d)")
_THOUSANDS_PLAIN = re.compile(r"(?<![\d.,])([1-9]\d{0,2}) (\d{3})(?![\d/:\-]|[.,]\d)")
# devant un tel nombre, « 12 345 » est probablement deux nombres distincts : on n'y touche pas
_NOT_AMOUNT_BEFORE = re.compile(
    r"(?:\b(?:pages?|pp?\.|chapitres?|chap\.|n°|nº|numéros?|numbers?|no\.|art\.|articles?|§|"
    r"figures?|fig\.|tableaux?|tables?|notes?|lignes?|lines?|versets?|rooms?|salles?)\s|\d\s|(?<!\d)\d{1,3},\s|"
    r"[\d,]\s?[-–]\s?)$",
    re.I,
)
_THOUSANDS_DOT = re.compile(r"(?<![\d.,])([1-9]\d{0,2})((?:\.\d{3}){2,})(?![\d]|\.\d)")
_THOUSANDS_COMMA = re.compile(r"(?<![\d.,])([1-9]\d{0,2})((?:,\d{3})+)(?![\d]|,\d)")


def merge_thousands(text: str, lang: str) -> str:
    def join(m: re.Match) -> str:
        return m.group(1) + re.sub(r"\D", "", m.group(2))

    text = _THOUSANDS_MULTI.sub(join, text)
    text = _THOUSANDS_FIN.sub(join, text)
    text = _THOUSANDS_PLAIN.sub(
        lambda m: m.group(0)
        if _NOT_AMOUNT_BEFORE.search(text[max(0, m.start() - 14):m.start()])
        else m.group(1) + m.group(2),
        text,
    )
    if lang == "fr":
        text = _THOUSANDS_DOT.sub(join, text)
    else:
        text = _THOUSANDS_COMMA.sub(join, text)
    return text


# --------------------------------------------------------------------------- téléphone (France)

_PHONE = re.compile(
    r"(?<![\d.,/+-])(\+33\s?\(?0?\)?\s?|0033\s?|0)([1-9])((?:[ .\-" + _SPACES + r"]?\d{2}){4})(?!\d)"
)


def _pair(two: str, lang: str) -> str:
    if two[0] == "0":
        return f"{_w(0, lang)} {_w(int(two[1]), lang)}"
    return _w(int(two), lang)


def phones(text: str, lang: str) -> str:
    if lang != "fr":
        return text

    def rep(m: re.Match) -> str:
        pairs = [_pair(p, lang) for p in re.findall(r"\d{2}", re.sub(r"\D", "", m.group(3)))]
        if m.group(1) == "0":
            return ", ".join([_pair("0" + m.group(2), lang)] + pairs)
        return ", ".join(["plus trente-trois", _w(int(m.group(2)), lang)] + pairs)

    return _PHONE.sub(rep, text)


# --------------------------------------------------------------------------- dates

_DATE_NUM = re.compile(
    r"(?<![\d/.\-])(0?[1-9]|[12]\d|3[01])([/.\-])(0?[1-9]|[12]\d|3[01])\2((?:1\d|2\d)\d\d)(?![\d/\-]|\.\d|\w)"
)
_DATE_ISO = re.compile(r"(?<![\d\-])((?:1\d|2\d)\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?![\d\-]|\w)")


def _valid(day: int, month: int, year: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= monthrange(year, month)[1]


def dates(text: str, lang: str) -> str:
    months = _rules(lang).MONTHS

    def fr_fmt(day: int, month: int, year: int) -> str:
        d = "premier" if day == 1 else str(day)
        return f"{d} {months[month - 1]} {year}"

    def en_fmt(day: int, month: int, year: int) -> str:
        return f"{months[month - 1]} {day}, {year}"

    def num(m: re.Match) -> str:
        a, b, year = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if lang == "fr":
            day, month = a, b
            return fr_fmt(day, month, year) if _valid(day, month, year) else m.group(0)
        # anglais : jour/mois ambigu, on ne lit que les cas sans ambiguïté
        if a > 12 and _valid(a, b, year):
            return f"{a} {months[b - 1]} {year}"
        if b > 12 and 1 <= a <= 12 and _valid(b, a, year):
            return en_fmt(b, a, year)
        return m.group(0)

    def iso(m: re.Match) -> str:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not _valid(day, month, year):
            return m.group(0)
        return fr_fmt(day, month, year) if lang == "fr" else en_fmt(day, month, year)

    return _DATE_ISO.sub(iso, _DATE_NUM.sub(num, text))


# --------------------------------------------------------------------------- heures (français)

_TIME_H = re.compile(rf"(?<![\w:.,/\-])([01]?\d|2[0-3])[ {_SPACES}]?h(?:[ {_SPACES}]?([0-5]\d))?(?![\w/])")
_TIME_COLON_CTX = re.compile(
    r"\b(à|vers|dès|de|depuis|jusqu['’]à|avant|après|entre|et|jusqu['’]à)\s(0?\d|1\d|2[0-3]):([0-5]\d)(?![\d:])"
)
_TIME_COLON_ZERO = re.compile(r"(?<![\d:])(0\d):([0-5]\d)(?![\d:])")


def _hm(h: int, m: str | None) -> str:
    s = f"{h} {'heure' if h in (0, 1) else 'heures'}"
    if m and int(m) != 0:
        s += f" {int(m)}"
    return s


def times(text: str, lang: str) -> str:
    if lang != "fr":
        return text
    text = _TIME_COLON_CTX.sub(lambda m: f"{m.group(1)} {_hm(int(m.group(2)), m.group(3))}", text)
    text = _TIME_COLON_ZERO.sub(lambda m: _hm(int(m.group(1)), m.group(2)), text)
    return _TIME_H.sub(lambda m: _hm(int(m.group(1)), m.group(2)), text)


# --------------------------------------------------------------------------- plages

_RANGE = re.compile(r"(?<![\w.,/+\-–])(\d{1,3})\s?[-–]\s?(\d{1,3})(?![\w.,/]?\d|[\-–]\d)")


def ranges(text: str, lang: str) -> str:
    r = _rules(lang)
    after = re.compile(rf"\s?(?:{r.RANGE_AFTER}|{_unit_alt(lang)}|[€$£])(?![\w])", re.I)
    before = re.compile(rf"\b(?:{r.RANGE_BEFORE})\s$", re.I)

    def rep(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        if a != str(int(a)) or b != str(int(b)) or int(a) >= int(b):
            return m.group(0)
        pre = text[max(0, m.start() - 16):m.start()]
        post = text[m.end():m.end() + 16]
        if before.search(pre) or after.match(post):
            return f"{a} {r.RANGE_WORD} {b}"
        return m.group(0)

    return _RANGE.sub(rep, text)


# --------------------------------------------------------------------------- fractions

def fractions(text: str, lang: str) -> str:
    r = _rules(lang)
    for ch, word in r.FRACTION_CHARS.items():
        text = text.replace(ch, f" {word} ") if ch in text else text
    pat = re.compile(r"(?<![\w/.,])([1-3])/([2-4])(?![\w/.,]?\d)")
    after = re.compile(r.FRACTION_AFTER)
    half_after = re.compile(r"(?=\s(?:des|du|de la|de l['’])\b)") if lang == "fr" else after
    before = re.compile(rf"{r.FRACTION_BEFORE}$")

    def rep(m: re.Match) -> str:
        key = (int(m.group(1)), int(m.group(2)))
        if key not in r.FRACTIONS:
            return m.group(0)
        ctx_after = bool(after.match(text, m.end()))
        ctx_before = bool(before.search(text[max(0, m.start() - 14):m.start()]))
        if not (ctx_after or ctx_before):
            return m.group(0)
        plain, partitive = r.FRACTIONS[key]
        if key == (1, 2) and lang == "fr":
            # « 1/2 de litre » reste tel quel ; « 1/2 des élèves » = la moitié des élèves
            return partitive if half_after.match(text, m.end()) else m.group(0)
        return plain

    return pat.sub(rep, text)


# --------------------------------------------------------------------------- unités, monnaies, pourcentages

def _unit_alt(lang: str) -> str:
    units = sorted(_rules(lang).UNITS, key=len, reverse=True)
    return "|".join(re.escape(u) for u in units)


def _singular(value: str, lang: str) -> bool:
    v = float(value.replace(",", "."))
    return abs(v) < 2 if lang == "fr" else v == 1


def _pick(pair: tuple[str, str], value: str, lang: str) -> str:
    return pair[0] if _singular(value, lang) else pair[1]


def percents(text: str, lang: str) -> str:
    word = _rules(lang).PERCENT
    text = re.sub(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s?%", lambda m: f"{m.group(1)} {word}", text)
    mille = "pour mille" if lang == "fr" else "per mille"
    return re.sub(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s?‰", lambda m: f"{m.group(1)} {mille}", text)


def money(text: str, lang: str) -> str:
    r = _rules(lang)
    cur = r.CURRENCIES
    sym = "".join(re.escape(s) for s in cur)

    # « 1,5 M€ », « 12 k€ » (français)
    if lang == "fr":
        def big(m: re.Match) -> str:
            val, suffix = m.group(1), m.group(2)
            if suffix == "k€":
                return f"{val} mille euros"
            one, many = r.CURRENCY_BIG[suffix]
            return f"{val} {one if _singular(val, lang) else many}"

        text = re.sub(r"(?<![\w.,])(\d+(?:,\d+)?)\s?(k€|M€|Md€)", big, text)
        text = re.sub(
            r"(?<![\w.,])(\d+(?:,\d+)?)\s(millions?|milliards?)\s?€",
            lambda m: f"{m.group(1)} {m.group(2)} d'euros", text)
    else:
        text = re.sub(
            rf"([{sym}])\s?(\d+(?:\.\d+)?)\s?(thousand|million|billion|trillion)\b",
            lambda m: f"{m.group(2)} {m.group(3)} {cur[m.group(1)][1]}", text)

    def amount(value: str, cents: str | None, symbol: str) -> str:
        one, many = cur[symbol]
        unit = one if int(value) in (0, 1) else many
        out = f"{value} {unit}"
        if cents is not None:
            c = int(cents) * (10 if len(cents) == 1 else 1)
            if c:
                out += f" {c}"
        return out

    suffix = re.compile(rf"(?<![\w.,])(\d+)(?:[,.](\d{{1,2}}))?(?![\d]|[.,]\d)\s?([{sym}])")
    prefix = re.compile(rf"([{sym}])\s?(\d+)(?:[,.](\d{{1,2}}))?(?![\d]|[.,]\d)")
    text = suffix.sub(lambda m: amount(m.group(1), m.group(2), m.group(3)), text)
    text = prefix.sub(lambda m: amount(m.group(2), m.group(3), m.group(1)), text)
    # « 12 EUR »
    return re.sub(r"(?<![\w.,])(\d+)\s?EUR\b", lambda m: amount(m.group(1), None, "€"), text)


_ENUM_DEGREE = re.compile(
    r"^(\s*)(\d{1,2})\s?°(?=\s+(?!(?:à|au|aux|de|du|des|d|en|sous|sur|dans|environ|le|la|les|et|nord|sud|est|"
    r"ouest|[NSEOCF]|Celsius|Fahrenheit)\b)[^\W\d_])"
)


def enumeration_degree(text: str, lang: str) -> str:
    """« 1° ont en France… » en tête de phrase (textes juridiques et administratifs) : énumération
    « premièrement, deuxièmement… », pas un angle ni une température."""
    if lang != "fr":
        return text

    def rep(m: re.Match) -> str:
        n = int(m.group(2))
        if n == 0:
            return m.group(0)
        word = "premier" if n == 1 else ordinal_words(n, lang)
        adverb = "premièrement" if n == 1 else word + "ment"
        return f"{m.group(1)}{adverb},"

    return _ENUM_DEGREE.sub(rep, text)


def units(text: str, lang: str) -> str:
    r = _rules(lang)
    table = r.UNITS
    alt = _unit_alt(lang)
    num = r"-?\d+(?:[.,]\d+)?"

    minus = "moins" if lang == "fr" else "minus"

    # températures
    def temp(m: re.Match) -> str:
        scale = r.CELSIUS if m.group(2) == "C" else r.FAHRENHEIT
        return f"{m.group(1)} {_pick(r.DEGREES, m.group(1), lang)} {scale}"

    text = re.sub(rf"(?<![\w.,])({num})\s?°\s?([CF])(?!\w)", temp, text)
    text = re.sub(r"(?<![\w.,])[-−](?=\d+(?:[.,]\d+)? (?:degrés?|degrees?) )", f"{minus} ", text)
    text = re.sub(
        rf"(?<![\w.,])({num})\s?°(?![\w°])",
        lambda m: f"{m.group(1)} {_pick(r.DEGREES, m.group(1), lang)}", text)

    def unit(m: re.Match) -> str:
        return f"{m.group(1)} {_pick(table[m.group(2)], m.group(1), lang)}"

    return re.sub(rf"(?<![\w.,])({num})[ {_SPACES}]?({alt})(?![\w'’²³/°])", unit, text)


# --------------------------------------------------------------------------- décimales

def _frac_words(frac: str, lang: str) -> str:
    zeros = len(frac) - len(frac.lstrip("0"))
    rest = frac.lstrip("0")
    if lang == "en" or len(frac) > 3:
        return " ".join(_w(int(d), lang) for d in frac)
    parts = [_w(0, lang)] * zeros
    if rest:
        parts.append(_w(int(rest), lang))
    return " ".join(parts)


_DEC_FR = re.compile(r"(?<![\w.,/+\-−])([-−+]?)(\d+),(\d+)(?![\w]|[,.]\d)")
_DEC_EN = re.compile(r"(?<![\w.,/+\-−])([-−+]?)(\d+)\.(\d+)(?![\w]|[,.]\d)")


def decimals(text: str, lang: str) -> str:
    pat = _DEC_FR if lang == "fr" else _DEC_EN
    point = "virgule" if lang == "fr" else "point"
    minus = "moins" if lang == "fr" else "minus"

    plus = "plus"

    def rep(m: re.Match) -> str:
        sign = {"": "", "+": f"{plus} "}.get(m.group(1), f"{minus} ")
        return f"{sign}{_w(int(m.group(2)), lang)} {point} {_frac_words(m.group(3), lang)}"

    return pat.sub(rep, text)


# --------------------------------------------------------------------------- ordinaux et romains

_ORD_SUFFIX = r"(?:er|ers|re|res|ère|ères|ere|eres|e|es|ème|èmes|eme|emes|ᵉ)"
_ORD_DIGIT = re.compile(rf"(?<![\w.,/])(\d+)({_ORD_SUFFIX})(?![\w])")


_YEAR_LETTER_AFTER = re.compile(r"\s*(?:[.,;:)\]]|$)")


def ordinals(text: str, lang: str) -> str:
    if lang != "fr":
        return text

    def rep(m: re.Match) -> str:
        n, suf = int(m.group(1)), m.group(2)
        if n == 0:
            return m.group(0)
        if suf in ("er", "ers", "re", "res", "ère", "ères", "ere", "eres"):
            if n != 1:
                return m.group(0)
            fem = suf[0] == "r" and suf.startswith(("re", "ère", "ere"))
            return ordinal_words(1, lang, feminine=fem, plural=suf.endswith("s"))
        if n == 1:
            return m.group(0)  # « 1e » : ambigu
        if suf == "e" and 1000 <= n <= 2999 and _YEAR_LETTER_AFTER.match(m.string, m.end()):
            return m.group(0)  # « janvier 2025e. » : année suivie d'une lettre de référence (2025a, 2025b…)
        return ordinal_words(n, lang, plural=suf.endswith("s"))

    return _ORD_DIGIT.sub(rep, text)


def romans(text: str, lang: str) -> str:
    r = _rules(lang)
    en_ = lang == "en"

    def cardinal(n: int) -> str:
        return _w(n, lang)

    # mot-clé + romain : « chapitre IV », « tome II »
    single = "VX" if en_ else "IVX"
    kw = re.compile(rf"\b((?i:{r.ROMAN_KEYWORDS}))(\s+)([IVXLC]+)(?![\w])")

    def kw_rep(m: re.Match) -> str:
        val = roman_to_int(m.group(3))
        if val is None or val > 99 or (len(m.group(3)) == 1 and m.group(3) not in single):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{cardinal(val)}"

    text = kw.sub(kw_rep, text)

    # souverains et papes : « Louis XIV », « Charles V »
    names = re.compile(rf"\b({r.KING_NAMES})(\s+)([IVXLC]+)(?![\w])(?!\.\s+[{_UP}])")

    def king_rep(m: re.Match) -> str:
        val = roman_to_int(m.group(3))
        if val is None or val > 39 or (len(m.group(3)) == 1 and m.group(3) not in "VX"):
            return m.group(0)
        if en_:
            return f"{m.group(1)} the {ordinal_words(val, lang)}"
        return f"{m.group(1)} {'premier' if val == 1 else cardinal(val)}"

    text = names.sub(king_rep, text)

    if en_:
        return text

    # « Ier »
    text = re.sub(r"(?<![\w])Ier(?![\w])", "premier", text)

    # siècles et assimilés : « XIXe siècle », « Ve République »
    suf = r"(?:e|ème|ᵉ|es|èmes)"
    multi = re.compile(rf"(?<![\w])([IVXLC]{{2,}})({suf})(?![\w])")
    keyed = re.compile(rf"(?<![\w])([IVXLC])({suf})(\s+(?:{r.ROMAN_ORDINAL_KEYWORDS}))(?![\w])")

    def multi_rep(m: re.Match) -> str:
        val = roman_to_int(m.group(1))
        if val is None or val > 39:
            return m.group(0)
        return ordinal_words(val, lang, plural=m.group(2).endswith("s"))

    def keyed_rep(m: re.Match) -> str:
        val = roman_to_int(m.group(1))
        if val is None or val > 39:
            return m.group(0)
        return ordinal_words(val, lang, plural=m.group(2).endswith("s")) + m.group(3)

    text = keyed.sub(keyed_rep, text)
    return multi.sub(multi_rep, text)
