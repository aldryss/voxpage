"""Dictionnaire de prononciation (issue #13) : « écrit = dit ».

Une entrée dit à la voix comment lire un mot, un nom propre, un sigle ou une expression :

    INRIA = inria
    EDF = eu dé effe
    Nguyen = nou-yène
    c.-à-d. = c'est-à-dire

Le « dit » est du texte ordinaire, lu tel quel par la voix : pas de phonétique à apprendre. Il n'est plus
retraité ensuite par les règles de sigles, de nombres ni de casse (il est remplacé par un repère opaque, rendu
à la fin de `speak`).

Deux sources sont fusionnées : le dictionnaire livré avec l'application (`data/prononciations-<langue>.txt`)
et celui de l'utilisateur (`prononciations.txt`, à côté de `settings.json`). L'utilisateur l'emporte ; une
entrée utilisateur au « dit » vide (`mot =`) annule l'entrée livrée correspondante.

Format du fichier (UTF-8, fait pour être édité à la main avec un lecteur d'écran) : une entrée par ligne,
`#` en début de ligne pour un commentaire, lignes vides ignorées, sections facultatives `[fr]` et `[en]`
(hors section, ou sous `[toutes]` : toutes les langues). Une ligne invalide est ignorée et signalée.

Correspondance : mot ou expression entiers seulement (jamais à l'intérieur d'un mot), une entrée qui contient
une majuscule est sensible à la casse, une entrée tout en minuscules ne l'est pas, la plus longue l'emporte,
le pluriel n'est pas deviné.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
USER_FILENAME = "prononciations.txt"
LANGUAGES = ("fr", "en")
_ALL_NAMES = {"toutes", "tous", "all", "*"}

# Formes élidées devant lesquelles une apostrophe est une frontière de mot (« l'INRIA », « d'EDF »).
_ELISIONS = {
    "fr": {"l", "d", "j", "m", "t", "s", "n", "c", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu", "presqu"},
    "en": set(),
}

# Repères : suites de quatre capitales mathématiques grasses (lettres, majuscules, étrangères aux règles de
# texte : ni sigle, ni nombre, ni mot ordinaire). Elles tiennent la place du « dit » jusqu'à `restore`.
_PH_BASE = 0x1D400
_PH_WIDTH = 4
_PH_RE = re.compile("[\U0001d400-\U0001d419]{4}")

TEMPLATE = """\
# Dictionnaire de prononciation de Voxpage.
# Une ligne par entrée : écrit = dit. Le « dit » est du texte ordinaire que la voix lira tel quel.
# Exemples :
#   INRIA = inria
#   EDF = eu dé effe
#   Nguyen = nou-yène
# Une entrée tout en minuscules ignore la casse ; avec une majuscule, la casse compte.
# « mot = » (rien après le signe égal) annule l'entrée livrée avec Voxpage pour ce mot.
# Sections facultatives : [fr] ou [en] limitent les entrées qui suivent à une langue ;
# [toutes] revient à toutes les langues. Les lignes qui commencent par # sont des commentaires.

"""


class LexiconError(ValueError):
    """Entrée refusée ; le message est destiné à l'utilisateur (en français)."""


@dataclass(frozen=True)
class Entry:
    written: str
    spoken: str
    lang: str = ""  # "" = toutes les langues
    line: int = 0  # numéro de ligne (à partir de 1) dans le fichier d'origine

    @property
    def key(self) -> str:
        return normalize_key(self.written)


@dataclass(frozen=True)
class Problem:
    line: int
    message: str

    def __str__(self) -> str:
        return f"ligne {self.line} ignorée : {self.message}"


def normalize_key(written: str) -> str:
    """Écrit ramené à une forme canonique : espaces simples, apostrophe droite."""
    return re.sub(r"\s+", " ", written.replace("’", "'")).strip()


def is_case_sensitive(key: str) -> bool:
    return any(c.isupper() for c in key)


# --------------------------------------------------------------------------- lecture


def parse(text: str) -> tuple[list[Entry], list[Problem]]:
    """Entrées et lignes invalides d'un texte. Tolérant : une ligne invalide n'arrête jamais la lecture."""
    entries: list[Entry] = []
    problems: list[Problem] = []
    section: str | None = ""  # None : section inconnue, ses entrées sont ignorées
    for number, raw in enumerate(text.lstrip("﻿").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().lower()
            if name in LANGUAGES:
                section = name
            elif name in _ALL_NAMES:
                section = ""
            else:
                section = None
                known = "[fr], [en], [toutes]"
                problems.append(Problem(number, f"section « {line} » inconnue (admises : {known})"))
            continue
        if "=" not in line:
            problems.append(Problem(number, f"signe « = » absent (attendu : écrit = dit) : « {line} »"))
            continue
        written, _, spoken = line.partition("=")
        written, spoken = written.strip(), spoken.strip()
        if not written:
            problems.append(Problem(number, "rien avant le signe « = »"))
            continue
        if section is None:
            continue
        entries.append(Entry(written, spoken, section, number))
    return entries, problems


def _decode(data: bytes) -> tuple[str, bool]:
    """(texte, ok) : UTF-8 (avec ou sans BOM) ; à défaut, ANSI (Bloc-notes ancien)."""
    try:
        return data.decode("utf-8-sig"), True
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), False


def read_entries(path: Path) -> tuple[list[Entry], list[Problem]]:
    """Entrées d'un fichier ; fichier absent ou illisible : aucune entrée (et un signalement si illisible)."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [Problem(0, f"fichier illisible ({exc.strerror or exc})")]
    text, utf8 = _decode(data)
    entries, problems = parse(text)
    if not utf8:
        problems.insert(0, Problem(0, "fichier non UTF-8 : lu en ANSI, il sera enregistré en UTF-8"))
    return entries, problems


def shipped_path(lang: str) -> Path:
    return DATA_DIR / f"prononciations-{'en' if lang == 'en' else 'fr'}.txt"


def shipped_entries(lang: str) -> list[Entry]:
    return read_entries(shipped_path(lang))[0]


# --------------------------------------------------------------------------- dictionnaire appliqué


def _atoms(key: str) -> list[str]:
    """Un fragment d'expression régulière par caractère de l'écrit (casse ignorée si tout en minuscules)."""
    sensitive = is_case_sensitive(key)
    atoms = []
    for ch in key:
        if ch == " ":
            atoms.append(r"\s+")
        elif ch == "'":
            atoms.append("['’]")
        elif not sensitive and ch.lower() != ch.upper():
            atoms.append("[" + re.escape(ch.lower()) + re.escape(ch.upper()) + "]")
        else:
            atoms.append(re.escape(ch))
    return atoms


def _trie_pattern(keys: Iterable[str]) -> str:
    """Une seule alternative par début commun (arbre de préfixes) : la recherche reste rapide avec des
    centaines d'entrées, et le plus long écrit l'emporte (les suites sont essayées avant la fin du mot)."""
    root: dict = {}
    for key in keys:
        node = root
        for atom in _atoms(key):
            node = node.setdefault(atom, {})
        node[""] = {}  # fin d'une entrée

    def emit(node: dict) -> str:
        ends = "" in node
        branches = [atom + emit(child) for atom, child in node.items() if atom]
        if not branches:
            return ""
        body = "|".join(branches)
        return f"(?:{body})?" if ends else f"(?:{body})"

    return emit(root)


def _placeholder(index: int) -> str:
    digits = []
    for _ in range(_PH_WIDTH):
        index, rest = divmod(index, 26)
        digits.append(chr(_PH_BASE + rest))
    return "".join(reversed(digits))


def _index(placeholder: str) -> int:
    value = 0
    for ch in placeholder:
        value = value * 26 + (ord(ch) - _PH_BASE)
    return value


class Lexicon:
    """Dictionnaire fusionné pour une langue : `apply` pose des repères, `restore` les remplace par le dit."""

    def __init__(self, mapping: dict[str, str] | None = None, lang: str = "fr") -> None:
        self.lang = "en" if lang == "en" else "fr"
        self._exact: dict[str, str] = {}
        self._folded: dict[str, str] = {}
        for written, spoken in (mapping or {}).items():
            key = normalize_key(written)
            if not key or not spoken.strip():
                continue
            spoken = spoken.strip()
            if is_case_sensitive(key):
                self._exact[key] = spoken
            else:
                self._folded[key.lower()] = spoken
        self.entries = len(self._exact) + len(self._folded)
        self._spoken: list[str] = []
        self._ph: dict[str, str] = {}  # dit -> repère
        keys = [*self._exact, *self._folded]
        self._regex = re.compile(r"(?<!\w)" + _trie_pattern(keys) + r"(?!\w)") if keys else None

    def __len__(self) -> int:
        return self.entries

    def __bool__(self) -> bool:
        return self._regex is not None

    def lookup(self, text: str) -> str | None:
        """Dit associé à un écrit (même règle de casse que la correspondance), ou None."""
        key = normalize_key(text)
        return self._exact.get(key) or self._folded.get(key.lower())

    def _mark(self, spoken: str) -> str:
        ph = self._ph.get(spoken)
        if ph is None:
            ph = _placeholder(len(self._spoken))
            self._spoken.append(spoken)
            self._ph[spoken] = ph
        return ph

    def _elided_ok(self, text: str, start: int) -> bool:
        """Une apostrophe avant le mot n'est une frontière qu'après une élision (« l' », « d' »…)."""
        if start == 0 or text[start - 1] not in "'’":
            return True
        before = re.search(r"(\w+)$", text[max(0, start - 21) : start - 1])
        return before is None or before.group(1).lower() in _ELISIONS[self.lang]

    def apply(self, text: str) -> str:
        """Texte où chaque écrit connu est remplacé par un repère opaque (voir `restore`)."""
        if self._regex is None or not text:
            return text

        def one(m: re.Match) -> str:
            found = self.lookup(m.group(0))
            if found is None or not self._elided_ok(m.string, m.start()):
                return m.group(0)
            return self._mark(found)

        return self._regex.sub(one, text)

    def restore(self, text: str) -> str:
        """Remplace les repères par le « dit » (à faire en toute fin de normalisation)."""
        if not self._spoken or not text:
            return text

        def one(m: re.Match) -> str:
            i = _index(m.group(0))
            return self._spoken[i] if i < len(self._spoken) else m.group(0)

        return _PH_RE.sub(one, text)

    def say(self, text: str) -> str:
        """Application complète sur un texte isolé (outils, essais d'écoute)."""
        return self.restore(self.apply(text))


EMPTY = Lexicon()


def merge(*sources: Iterable[Entry], lang: str) -> dict[str, str]:
    """Fusionne des listes d'entrées, dans l'ordre : les dernières l'emportent ; un dit vide annule.
    Dans une même source, une entrée propre à la langue l'emporte sur une entrée « toutes langues »."""
    merged: dict[str, str] = {}
    for source in sources:
        wanted = [e for e in source if e.lang in ("", lang)]
        for e in sorted(wanted, key=lambda e: e.lang != ""):
            if e.spoken:
                merged[e.key] = e.spoken
            else:
                merged.pop(e.key, None)
    return merged


@dataclass
class LexiconSource:
    """D'où vient le dictionnaire d'une conversion."""

    user_path: Path | None = None  # None : fichier de l'utilisateur par défaut (à côté de settings.json)
    shipped: bool = True
    user: bool = True

    def resolved_path(self) -> Path | None:
        if not self.user:
            return None
        if self.user_path is not None:
            return Path(self.user_path)
        from voxpage import settings  # import tardif : settings dépend de ce paquet

        return settings.pronunciations_read_path()

    def load(self, lang: str) -> LoadedLexicon:
        lang = "en" if lang == "en" else "fr"
        shipped = shipped_entries(lang) if self.shipped else []
        path = self.resolved_path()
        user, problems = read_entries(path) if path is not None else ([], [])
        usable = [e for e in user if e.lang in ("", lang)]
        lex = Lexicon(merge(shipped, user, lang=lang), lang)
        return LoadedLexicon(lex, path, len(user), len(usable), len(shipped), problems)


@dataclass
class LoadedLexicon:
    lexicon: Lexicon
    user_path: Path | None
    user_entries: int  # entrées valides du fichier de l'utilisateur, toutes langues
    user_active: int  # dont celles qui valent pour la langue chargée
    shipped_entries: int
    problems: list[Problem] = field(default_factory=list)

    def warnings(self) -> list[str]:
        name = self.user_path.name if self.user_path else USER_FILENAME
        return [f"Dictionnaire de prononciation « {name} », {p}." for p in self.problems]


# --------------------------------------------------------------------------- écriture


class LexiconFile:
    """Fichier de l'utilisateur, modifié ligne à ligne : commentaires, sections et ordre sont conservés."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.newline = "\n"
        self.bom = False
        self.lines: list[str] = []
        self.exists = False
        self.reload()

    def reload(self) -> None:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            self.exists, self.lines, self.bom = False, TEMPLATE.splitlines(), False
            return
        self.exists = True
        self.bom = data.startswith(b"\xef\xbb\xbf")
        text, _ = _decode(data)
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.lines = text.splitlines()

    # -- lecture
    def parsed(self) -> tuple[list[Entry], list[Problem]]:
        return parse("\n".join(self.lines))

    @property
    def entries(self) -> list[Entry]:
        return self.parsed()[0]

    @property
    def problems(self) -> list[Problem]:
        return self.parsed()[1]

    # -- validation
    @staticmethod
    def check(written: str, spoken: str) -> str | None:
        """Message d'erreur en français si l'entrée est inacceptable, sinon None."""
        written, spoken = written.strip(), spoken.strip()
        if not written:
            return "Indiquez le mot ou le sigle à corriger (champ « Écrit »)."
        if any(c in written + spoken for c in "\r\n\t\x00"):
            return "L'écrit et le dit tiennent sur une seule ligne, sans tabulation."
        if "=" in written:
            return "Le signe « = » ne peut pas figurer dans le champ « Écrit »."
        if written.startswith("#"):
            return "Le champ « Écrit » ne peut pas commencer par « # » (ce serait un commentaire)."
        if written.startswith("[") and written.endswith("]"):
            return "Le champ « Écrit » ne peut pas être de la forme « [mot] » (ce serait une section)."
        return None

    def _locate(self, line: int) -> Entry:
        for e in self.entries:
            if e.line == line:
                return e
        raise LexiconError("Cette entrée n'existe plus dans le fichier.")

    def _duplicate(self, written: str, lang: str, ignore_line: int = 0) -> Entry | None:
        key = normalize_key(written)
        for e in self.entries:
            if e.line != ignore_line and e.key == key and e.lang == lang:
                return e
        return None

    @staticmethod
    def _text(written: str, spoken: str) -> str:
        return f"{written.strip()} = {spoken.strip()}".rstrip()

    # -- modification (en mémoire ; `save` écrit)
    def add(self, written: str, spoken: str, lang: str = "") -> Entry:
        problem = self.check(written, spoken)
        if problem:
            raise LexiconError(problem)
        if lang not in ("", *LANGUAGES):
            raise LexiconError("Langue inconnue.")
        twin = self._duplicate(written, lang)
        if twin:
            raise LexiconError(
                f"« {twin.written} » existe déjà (dit : « {twin.spoken} »). Utilisez « Modifier »."
            )
        self._insert(self._text(written, spoken), lang)
        return next(e for e in reversed(self.entries) if e.key == normalize_key(written) and e.lang == lang)

    def update(self, line: int, written: str, spoken: str, lang: str = "") -> Entry:
        problem = self.check(written, spoken)
        if problem:
            raise LexiconError(problem)
        current = self._locate(line)
        twin = self._duplicate(written, lang, ignore_line=line)
        if twin:
            raise LexiconError(f"« {twin.written} » existe déjà (dit : « {twin.spoken} »).")
        if current.lang == lang:
            self.lines[line - 1] = self._text(written, spoken)
        else:
            del self.lines[line - 1]
            self._insert(self._text(written, spoken), lang)
        return next(e for e in reversed(self.entries) if e.key == normalize_key(written) and e.lang == lang)

    def remove(self, line: int) -> None:
        self._locate(line)
        del self.lines[line - 1]
        self._drop_empty_sections()

    def _drop_empty_sections(self) -> None:
        """Retire une section laissée vide par une suppression (en-tête et lignes vides comprises)."""
        i = 0
        while i < len(self.lines):
            if re.fullmatch(r"\[[^\]]*\]", self.lines[i].strip()):
                j = i + 1
                while j < len(self.lines) and not self.lines[j].strip():
                    j += 1
                if j >= len(self.lines) or re.fullmatch(r"\[[^\]]*\]", self.lines[j].strip()):
                    start = i
                    while start > 0 and not self.lines[start - 1].strip():
                        start -= 1
                    del self.lines[start:j]
                    i = start
                    continue
            i += 1

    def _insert(self, text: str, lang: str) -> None:
        headers = [
            (i, ln.strip()) for i, ln in enumerate(self.lines) if re.fullmatch(r"\[[^\]]*\]", ln.strip())
        ]

        def section_of(name: str) -> str:
            return "toutes" if name == "" else name

        def region(wanted: str) -> tuple[int, int] | None:
            """(début, fin) des lignes d'une section ; fin exclue. Hors section : début 0."""
            if wanted == "":
                first = headers[0][0] if headers else len(self.lines)
                blanks_start = 0
                return blanks_start, first
            for n, (i, h) in enumerate(headers):
                title = h[1:-1].strip().lower()
                if title == wanted or (wanted == "" and title in _ALL_NAMES):
                    end = headers[n + 1][0] if n + 1 < len(headers) else len(self.lines)
                    return i + 1, end
            return None

        found = region(lang)
        if found is None:
            if self.lines and self.lines[-1].strip():
                self.lines.append("")
            self.lines += [f"[{section_of(lang)}]", text]
            return
        start, end = found
        last = start - 1
        for i in range(start, end):  # après la dernière entrée ; à défaut, après le dernier commentaire
            if self.lines[i].strip() and not self.lines[i].lstrip().startswith("#"):
                last = i
        if last < start:
            for i in range(start, end):
                if self.lines[i].strip():
                    last = i
        at = last + 1
        comment = 0 <= last and self.lines[last].lstrip().startswith("#")
        if comment and at < end and not self.lines[at].strip():
            at += 1  # après le commentaire d'en-tête et sa ligne vide
        self.lines.insert(at, text)
        if at == end and headers and lang == "":
            self.lines.insert(at + 1, "")  # juste avant une section : une ligne vide les sépare

    # -- écriture
    def render(self) -> bytes:
        text = self.newline.join(self.lines) + self.newline
        return (b"\xef\xbb\xbf" if self.bom else b"") + text.encode("utf-8")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_bytes(self.render())
        os.replace(tmp, self.path)
        self.exists = True
