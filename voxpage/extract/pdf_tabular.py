"""Repérages prudents sur le flux de lignes : sommaires et zones tabulaires sans structure (issue #12).

Règle conservatrice (dans le doute, le flux n'est pas touché) et sans perte de texte :

- **Tableau ou graphique sans structure** : au moins 6 lignes consécutives très courtes, en majorité
  numériques et alignées en colonnes (valeurs d'un tableau sans filets, graduations et étiquettes d'un
  graphique) ; elles forment un bloc annoncé à l'auditeur plutôt que d'être mêlées au corps du texte.
"""

import re
from dataclasses import dataclass

from voxpage.extract.pdf_layout import Line

MIN_LOOSE = 6

_NUMERIC = re.compile(r"^[\s\d.,%+\-−–/€$°‰]+$")
_SHORT_LABEL_END = (".", ";", ":", "!", "?")


@dataclass
class LooseItem:
    """Zone tabulaire ou graphique que l'on ne sait pas structurer : lignes lues telles quelles."""

    page: int
    lines: list[Line]


def _text(line: Line, render) -> str:
    return render(line)[0].strip()


def _fragment(line: Line, text: str) -> str | None:
    """« num » pour une ligne numérique courte, « label » pour une étiquette courte, sinon None."""
    if line.region != 0 or not text:
        return None
    if len(text) <= 40 and _NUMERIC.match(text) and any(c.isdigit() for c in text):
        return "num"
    if len(text) <= 14 and len(text.split()) <= 2 and not text.endswith(_SHORT_LABEL_END):
        return "label"
    return None


def _aligned(lines: list[Line]) -> bool:
    for attr in ("x0", "x1"):
        xs = sorted(getattr(ln, attr) for ln in lines)
        if max(sum(1 for x in xs if abs(x - x0) <= 1.5) for x0 in xs) >= 3:
            return True
    return False


def find_loose(stream: list, render) -> list:
    """Regroupe en `LooseItem` les séries de lignes très courtes, majoritairement numériques, alignées."""
    out: list = []
    i = 0
    n = len(stream)
    while i < n:
        run: list[tuple[Line, str]] = []
        j = i
        while j < n and isinstance(stream[j], Line):
            ln = stream[j]
            kind = _fragment(ln, _text(ln, render))
            if kind is None or (run and ln.page != run[0][0].page):
                break
            run.append((ln, kind))
            j += 1
        a, b = 0, len(run)
        while a < b and run[a][1] != "num":  # les étiquettes aux extrémités restent dans le flux
            a += 1
        while b > a and run[b - 1][1] != "num":
            b -= 1
        core = run[a:b]
        nums = sum(1 for _, k in core if k == "num")
        enough = len(core) >= MIN_LOOSE and nums >= 4 and nums >= 0.6 * len(core)
        if enough and _aligned([ln for ln, _ in core]):
            out.extend(stream[i : i + a])
            out.append(LooseItem(core[0][0].page, [ln for ln, _ in core]))
            i += b
        else:
            out.append(stream[i])
            i += 1
    return out


def loose_pages(blocks) -> list[int]:
    """Pages (à partir de 1) portant des zones lues sans structure, dans l'ordre, sans doublon."""
    return sorted({b.page for b in blocks if b.kind == "table" and b.loose and b.page})

