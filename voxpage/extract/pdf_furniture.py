"""En-têtes, pieds de page et numéros de page.

Seuls les fragments des trois lignes les plus hautes et des trois plus basses de chaque page, situées dans
la marge (15 % de la hauteur de la page, ou du cadre habituel du texte si la page est plus grande que la
surface imprimée), sont candidats. Un candidat est supprimé si :

- c'est un numéro de page (« 12 », « - 12 - », « Page 12 », « 12 / 40 », chiffres romains) dont l'écart
  avec le rang de la page est le même sur au moins deux pages (ou, si une seule page est analysée, égal
  à son rang) ;
- ou son texte (chiffres neutralisés) revient dans la même marge sur au moins deux pages, dans une police
  pas plus grande que le corps du texte, et il est séparé du corps par un blanc net.

La suppression part du bord de la page et s'arrête à la première ligne non reconnue ; le blanc net est
exigé entre la dernière ligne retirée et le corps du texte (sinon seuls les numéros de page partent).
"""

import re
from collections import defaultdict

from voxpage.extract.pdf_layout import Frag, PageData, _rows_of

ZONE = 0.15
MAX_ROWS = 3
_PAGE_NUM = re.compile(
    r"^(?:page|p\.)?\s*[-–—(\[]?\s*(\d{1,4}|[ivxlcdm]{1,7})\s*[-–—)\]]?"
    r"(?:\s*(?:/|sur|of|de)\s*\d{1,4})?$",
    re.IGNORECASE,
)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman(s: str) -> int | None:
    s = s.lower()
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN[ch]
        if i + 1 < len(s) and _ROMAN[s[i + 1]] > v:
            total -= v
        else:
            total += v
    return total if total > 0 else None


def page_number_value(text: str) -> tuple[str, int] | None:
    m = _PAGE_NUM.match(text.strip())
    if not m:
        return None
    tok = m.group(1)
    if tok.isdigit():
        return "arabic", int(tok)
    value = _roman(tok)
    return ("roman", value) if value else None


def _key(text: str) -> str:
    text = re.sub(r"\d+", "#", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def _zone_rows(
    page: PageData, frags: list[Frag], frame: tuple[float, float] | None = None
) -> tuple[list[list[Frag]], list[list[Frag]], list[list[Frag]]]:
    rows = _rows_of(frags)
    rows.sort(key=lambda r: min(f.top for f in r))
    top_limit, bottom_limit = page.height * ZONE, page.height * (1 - ZONE)
    if frame is not None:
        # page plus grande que la surface imprimée (livre au format A5 centré sur une page A4) : les
        # marges se mesurent aussi depuis le cadre habituel du texte
        f_top, f_bottom = frame
        top_limit = max(top_limit, f_top + ZONE * (f_bottom - f_top))
        bottom_limit = min(bottom_limit, f_bottom - ZONE * (f_bottom - f_top))
    top = [r for r in rows[:MAX_ROWS] if max(f.bottom for f in r) <= top_limit]
    bottom = [r for r in rows[-MAX_ROWS:][::-1] if min(f.top for f in r) >= bottom_limit]
    return rows, top, bottom


def _text_frame(pages: list[PageData]) -> tuple[float, float] | None:
    """Cadre habituel du texte (médianes des hauts et bas de texte des pages), s'il y a assez de pages."""
    tops = sorted(min(f.top for f in p.frags) for p in pages if p.frags)
    bottoms = sorted(max(f.bottom for f in p.frags) for p in pages if p.frags)
    if len(tops) < 2:
        return None
    return tops[len(tops) // 2], bottoms[len(bottoms) // 2]


def detect_furniture(pages: list[PageData], body_size: float) -> set[int]:
    """Renvoie les `id()` des fragments à retirer."""
    counts: dict[tuple[str, str], set[int]] = defaultdict(set)
    offsets: dict[tuple[str, int], set[int]] = defaultdict(set)
    layout = {}
    frame = _text_frame(pages)
    for page in pages:
        rows, top, bottom = _zone_rows(page, page.frags, frame)
        layout[page.index] = (rows, top, bottom)
        for zone, zrows in (("top", top), ("bottom", bottom)):
            for row in zrows:
                for f in row:
                    counts[(zone, _key(f.text))].add(page.index)
                    num = page_number_value(f.text)
                    if num:
                        offsets[(num[0], num[1] - page.index)].add(page.index)

    single = len(pages) == 1

    def is_number(f: Frag, page: PageData) -> bool:
        num = page_number_value(f.text)
        if not num:
            return False
        if single:
            return num[1] == page.index + 1
        return len(offsets[(num[0], num[1] - page.index)]) >= 2

    def is_repeated(f: Frag, zone: str) -> bool:
        return len(counts[(zone, _key(f.text))]) >= 2 and f.size <= 1.1 * body_size and bool(f.text.strip())

    def gap_between(outer: list[Frag], inner: list[Frag] | None, zone: str) -> float:
        if inner is None:
            return float("inf")
        if zone == "top":
            return min(f.top for f in inner) - max(f.bottom for f in outer)
        return min(f.top for f in outer) - max(f.bottom for f in inner)

    removed: set[int] = set()
    for page in pages:
        rows, top, bottom = layout[page.index]
        for zone, zrows in (("top", top), ("bottom", bottom)):
            # lignes consécutives depuis le bord, entièrement reconnues (numéro ou texte répété)
            block: list[list[Frag]] = []
            partial: list[Frag] = []
            for row in zrows:
                pos = rows.index(row)
                if block and abs(rows.index(block[-1]) - pos) != 1:
                    break
                known = [f for f in row if is_number(f, page) or is_repeated(f, zone)]
                if len(known) == len(row):
                    block.append(row)
                    continue
                if not block:
                    # ligne du bord mêlant numéro de page et autre chose : seul le numéro part
                    partial = [f for f in row if is_number(f, page)]
                break
            if block:
                pos = rows.index(block[-1])
                nb = pos + 1 if zone == "top" else pos - 1
                inner = rows[nb] if 0 <= nb < len(rows) else None
                if gap_between(block[-1], inner, zone) >= 0.4 * body_size:
                    for row in block:
                        removed.update(map(id, row))
                else:
                    # pas de blanc net avec le corps du texte : seuls les numéros de page sont sûrs
                    for row in block:
                        removed.update(id(f) for f in row if is_number(f, page))
            removed.update(map(id, partial))
    return removed
