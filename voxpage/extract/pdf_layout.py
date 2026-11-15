"""Géométrie d'une page PDF : caractères → fragments de ligne → régions → ordre de lecture.

Coordonnées « de haut en bas » : `top` < `bottom`, l'origine est le coin supérieur gauche de la page.
"""

import functools
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar, LTContainer, LTCurve, LTFigure, LTImage, LTLine, LTRect

from voxpage.extract.pdf_text import clean_char, is_unknown_glyph

_BOLD = re.compile(r"bold|black|heavy|semibold|demibold|demi|extrabold|ultrabold|[-,]bd\b", re.IGNORECASE)
_ITALIC = re.compile(r"italic|oblique|[-,]it\b", re.IGNORECASE)
LIST_MARKER = re.compile(
    r"^(?:[•◦▪▫‣⁃●○■□►▶➢➤✓✔∙·*–—-]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[ivxlcIVXLC]{1,5}[.)])$"
)
_LIST_GLYPHS = "•◦▪▫‣⁃●○■□►▶➢➤✓✔∙·"


@functools.lru_cache(maxsize=256)
def font_style(fontname: str) -> tuple[bool, bool]:
    """(gras, italique) d'après le nom de la police."""
    return bool(_BOLD.search(fontname)), bool(_ITALIC.search(fontname))


@dataclass
class Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    size: float
    bold: bool
    italic: bool
    order: int
    is_space: bool = False

    def __post_init__(self) -> None:
        self.is_space = self.text.isspace()


@dataclass
class Span:
    text: str
    role: str = ""  # "sup" (exposant), "sub" (indice) ou ""


@dataclass
class Frag:
    """Morceau de ligne d'un seul tenant (pas de grand blanc horizontal à l'intérieur)."""

    spans: list[Span]
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    size: float
    bold: bool
    italic: bool
    page: int = 0

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.x0, self.top, self.x1, self.bottom


@dataclass
class Line:
    """Ligne de texte en ordre de lecture, prête pour l'assemblage des paragraphes."""

    spans: list[Span]
    x0: float
    x1: float
    top: float
    bottom: float
    baseline: float
    size: float
    bold: bool
    italic: bool
    page: int
    col_x0: float
    col_x1: float
    region: int = 0  # 0 : corps de page ; sinon identifiant d'encadré

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class Seg:
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def horizontal(self) -> bool:
        return (self.bottom - self.top) <= (self.x1 - self.x0)


@dataclass
class Region:
    kind: str  # "box" ou "table"
    x0: float
    top: float
    x1: float
    bottom: float
    xs: list[float] = field(default_factory=list)  # filets verticaux (tableau quadrillé)
    ys: list[float] = field(default_factory=list)  # filets horizontaux
    frags: list[Frag] = field(default_factory=list)
    children: list["Region"] = field(default_factory=list)
    ident: int = 0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.x0, self.top, self.x1, self.bottom

    def contains(self, x: float, y: float, tol: float = 1.0) -> bool:
        return self.x0 - tol <= x <= self.x1 + tol and self.top - tol <= y <= self.bottom + tol


@dataclass
class TableItem:
    page: int
    rows: list[list[list[Line]]]  # lignes → cellules → lignes de texte de la cellule
    top: float


@dataclass
class PageData:
    index: int  # à partir de 0
    width: float
    height: float
    frags: list[Frag]
    segs: list[Seg]
    fills: list[Seg]  # rectangles pleins sans contour (fonds d'encadrés)
    image_area: float = 0.0
    n_chars: int = 0
    n_alnum: int = 0
    n_unknown: int = 0
    n_rotated: int = 0
    footnotes: list[Line] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------------------
# Lecture des objets pdfminer


class Aggregator(PDFPageAggregator):
    """Agrégateur pdfminer qui note la ligne de base réelle de chaque caractère (décalage vertical
    `Ts` compris) : c'est ce qui permet de reconnaître les exposants (appels de note, « XIXe »)."""

    _render_mode = 0

    def render_string(self, textstate, seq, ncs, graphicstate):  # noqa: D102
        self._render_mode = getattr(textstate, "render", 0) or 0
        super().render_string(textstate, seq, ncs, graphicstate)

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):  # noqa: D102
        adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        item = self.cur_item._objs[-1]
        a, b, c, d, e, f = matrix
        item.vox_baseline = b * 0 + d * rise + f
        item.vox_invisible = self._render_mode in (3, 7)  # ni remplissage ni contour
        return adv


def read_page(ltpage, index: int) -> PageData:
    x_min, y_min, x_max, y_max = ltpage.bbox
    width, height = x_max - x_min, y_max - y_min
    chars: list[Char] = []
    segs: list[Seg] = []
    fills: list[Seg] = []
    stats = {"unknown": 0, "rotated": 0, "image": 0.0}

    def td(y: float) -> float:
        return y_max - y

    def walk(obj, clip=None) -> None:
        if isinstance(obj, LTChar):
            if clip is not None:
                cx, cy = (obj.x0 + obj.x1) / 2, (obj.y0 + obj.y1) / 2
                if not (clip[0] - 0.5 <= cx <= clip[2] + 0.5 and clip[1] - 0.5 <= cy <= clip[3] + 0.5):
                    return  # hors du cadre de son objet de formulaire : masqué à l'affichage
            add_char(obj)
        elif isinstance(obj, LTImage):
            w = max(0.0, min(obj.x1, x_max) - max(obj.x0, x_min))
            h = max(0.0, min(obj.y1, y_max) - max(obj.y0, y_min))
            stats["image"] += w * h
        elif isinstance(obj, LTRect | LTLine | LTCurve):
            add_graphic(obj)
            if isinstance(obj, LTContainer):
                for child in obj:
                    walk(child)
        elif isinstance(obj, LTFigure):
            box = obj.bbox
            if clip is not None:
                box = (max(box[0], clip[0]), max(box[1], clip[1]), min(box[2], clip[2]), min(box[3], clip[3]))
            for child in obj:
                walk(child, box)
        elif isinstance(obj, LTContainer):
            for child in obj:
                walk(child, clip)

    def add_char(c: LTChar) -> None:
        raw = c.get_text()
        if is_unknown_glyph(raw):
            stats["unknown"] += 1
            return
        a, b, cc, d, _e, f = c.matrix
        if abs(b) > 0.01 * abs(a) + 1e-6 or abs(cc) > 0.01 * abs(d) + 1e-6 or a <= 0 or d <= 0:
            if raw.strip():
                stats["rotated"] += 1
            return
        if c.x1 < x_min or c.x0 > x_max or c.y1 < y_min or c.y0 > y_max:
            return  # hors de la page visible
        text = clean_char(raw)
        if not text:
            if raw.strip():
                stats["unknown"] += 1
            return
        size = c.size if c.size > 0 else (c.y1 - c.y0)
        top, bottom = td(c.y1), td(c.y0)
        baseline = td(getattr(c, "vox_baseline", f))
        if not (top - 0.5 * size <= baseline <= bottom + 0.5 * size):
            baseline = bottom - 0.2 * size
        style = font_style(c.fontname or "")
        chars.append(Char(text, c.x0, c.x1, top, bottom, baseline, size, style[0], style[1], len(chars)))

    def add_graphic(g) -> None:
        w, h = g.x1 - g.x0, g.y1 - g.y0
        stroke = getattr(g, "stroke", True)
        fill = getattr(g, "fill", False)
        thin = w <= 2.0 and h >= 3.0 or h <= 2.0 and w >= 3.0
        if thin or (stroke and not fill):
            color = g.stroking_color if stroke and not (fill and thin) else g.non_stroking_color
            if _is_light(color):
                return  # filet presque blanc : invisible sur la page, il ne structure rien
        if thin:
            segs.append(Seg(g.x0, td(g.y1), g.x1, td(g.y0)))  # filet (même dessiné par un rectangle plein)
        elif isinstance(g, LTRect) and w > 2.0 and h > 2.0:
            if stroke:
                x0, x1, t, bt = g.x0, g.x1, td(g.y1), td(g.y0)
                segs.extend([Seg(x0, t, x1, t), Seg(x0, bt, x1, bt), Seg(x0, t, x0, bt), Seg(x1, t, x1, bt)])
            elif fill:
                fills.append(Seg(g.x0, td(g.y1), g.x1, td(g.y0)))
        elif isinstance(g, LTCurve) and fill and not stroke and w > 40 and h > 10:
            fills.append(Seg(g.x0, td(g.y1), g.x1, td(g.y0)))  # fond d'encadré (coins arrondis…)
        elif isinstance(g, LTCurve) and stroke and getattr(g, "pts", None):
            pts = g.pts
            for (xa, ya), (xb, yb) in zip(pts, pts[1:], strict=False):
                if abs(ya - yb) <= 1.0 and abs(xa - xb) >= 3 or abs(xa - xb) <= 1.0 and abs(ya - yb) >= 3:
                    segs.append(Seg(min(xa, xb), td(max(ya, yb)), max(xa, xb), td(min(ya, yb))))

    for obj in ltpage:
        walk(obj)

    visible = [c for c in chars if not c.is_space]
    page = PageData(index, width, height, [], segs, fills, stats["image"])
    page.n_chars = len(visible)
    page.n_alnum = sum(1 for c in visible for ch in c.text if ch.isalnum())
    page.n_unknown = stats["unknown"]
    page.n_rotated = stats["rotated"]
    vsegs = [s for s in segs if not s.horizontal]
    page.frags = build_frags(_drop_microtext(chars), vsegs, index)
    return page


MICRO_SIZE = 3.0  # points : en dessous, un texte n'est lisible par personne à l'impression


def _drop_microtext(chars: list[Char]) -> list[Char]:
    """Retire les suites d'au moins trois caractères microscopiques de même taille (libellé dessiné dans une
    icône, mention en filigrane) : invisibles à l'œil, ils s'intercaleraient lettre à lettre dans le texte
    voisin (« l'eSaTOPu »). Un caractère isolé de petite taille (corps mal déclaré, exposant) est gardé."""
    out: list[Char] = []
    run: list[Char] = []

    def close() -> None:
        if len(run) < 3:
            out.extend(run)
        run.clear()

    for c in chars:
        tiny = 0 < c.size < MICRO_SIZE
        if tiny and (not run or abs(run[0].size - c.size) < 0.15):
            run.append(c)
            continue
        close()
        if tiny:
            run.append(c)
        else:
            out.append(c)
    close()
    return out


def _is_light(color) -> bool:
    """Couleur très claire (blanc, gris très pâle) ; fonds de couleur pastel exclus des filets visibles."""
    if color is None:
        return False
    try:
        values = list(color) if isinstance(color, list | tuple) else [color]
        values = [float(v) for v in values]
    except (TypeError, ValueError):
        return False
    if len(values) == 1:
        return values[0] > 0.85
    if len(values) == 3:
        return 0.3 * values[0] + 0.59 * values[1] + 0.11 * values[2] > 0.85
    if len(values) == 4:  # CMJN
        return max(values) < 0.15
    return False


# ---------------------------------------------------------------------------------------------------------
# Caractères → fragments


@dataclass
class _Row:
    top: float
    bottom: float
    size: float
    baseline: float
    chars: list[Char] = field(default_factory=list)


def _dedupe(chars: list[Char]) -> list[Char]:
    """Supprime les caractères imprimés deux fois au même endroit (faux gras)."""
    seen: dict[tuple[str, int, int], list[Char]] = {}
    out = []
    for c in chars:
        if c.is_space:
            out.append(c)
            continue
        kx, ky = int(c.x0), int(c.baseline)
        dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in seen.get((c.text, kx + dx, ky + dy), ()):
                    if (
                        abs(o.x0 - c.x0) < 0.25 * max(c.x1 - c.x0, 1.0)
                        and abs(o.baseline - c.baseline) < 0.2 * c.size
                    ):
                        dup = True
        if not dup:
            seen.setdefault((c.text, kx, ky), []).append(c)
            out.append(c)
    return out


def _assign_rows(chars: list[Char]) -> list[_Row]:
    rows: list[_Row] = []
    buckets: dict[int, list[_Row]] = {}
    step = 4.0
    for c in sorted(chars, key=lambda c: (-round(c.size, 1), c.top, c.order)):
        cy = (c.top + c.bottom) / 2
        best, best_d = None, 0.0
        for r in buckets.get(int(cy // step), ()):
            if r.top <= cy <= r.bottom and c.size >= 0.45 * r.size:
                d = abs(c.baseline - r.baseline)
                if best is None or d < best_d:
                    best, best_d = r, d
        if best is None:
            best = _Row(c.top, c.bottom, c.size, c.baseline)
            rows.append(best)
            for k in range(int(best.top // step), int(best.bottom // step) + 1):
                buckets.setdefault(k, []).append(best)
        best.chars.append(c)
    return _attach_raised(rows)


def _raised_next_to(cluster: list[Char], rc: Char) -> bool:
    """Le petit groupe `cluster` est-il un exposant collé au caractère `rc` ?"""
    x0, x1 = cluster[0].x0, cluster[-1].x1
    size = max(c.size for c in cluster)
    bottom = max(c.bottom for c in cluster)
    base = max(c.baseline for c in cluster)
    near = rc.x1 - 1 <= x0 <= rc.x1 + 0.3 * rc.size or rc.x0 - 0.3 * rc.size <= x1 <= rc.x0 + 1
    return (
        near
        and 0.3 * rc.size <= size <= 0.85 * rc.size
        and rc.top <= bottom <= rc.baseline + 0.1 * rc.size
        and base <= rc.baseline - 0.2 * rc.size
    )


def _attach_raised(rows: list[_Row]) -> list[_Row]:
    """Exposant très surélevé (« 1er » dans une petite police) : son centre sort de la ligne et il forme
    une ligne à lui seul. Un tel groupe de quatre caractères au plus, plus petit que la ligne du dessous,
    dont le pied tombe dans cette ligne et qui touche un de ses caractères, lui est rattaché."""
    keep: list[_Row] = []
    for row in rows:
        clusters: list[list[Char]] = []
        for c in sorted(row.chars, key=lambda c: c.x0):
            if clusters and c.x0 - clusters[-1][-1].x1 <= 0.5 * c.size:
                clusters[-1].append(c)
            else:
                clusters.append([c])
        rest: list[Char] = []
        for cl in clusters:
            target = None
            if sum(len(c.text) for c in cl) <= 4:
                for r in rows:
                    if r is not row and any(_raised_next_to(cl, rc) for rc in r.chars):
                        target = r
                        break
            if target is not None:
                target.chars.extend(cl)
            else:
                rest.extend(cl)
        if rest:
            row.chars = rest
            keep.append(row)
    return keep


def build_frags(chars: list[Char], vsegs: list[Seg], page: int) -> list[Frag]:
    chars = _dedupe(chars)
    solid = [c for c in chars if not c.is_space]
    spaces = [c for c in chars if c.is_space]
    rows = _assign_rows(solid)
    # rattache les glyphes d'espace aux lignes
    for sp in spaces:
        cy = (sp.top + sp.bottom) / 2
        for r in rows:
            if r.top <= cy <= r.bottom and abs(sp.baseline - r.baseline) < 0.4 * r.size:
                r.chars.append(sp)
                break
    frags: list[Frag] = []
    for r in rows:
        for layer in _layers(r):
            frags.extend(_split_row(layer, vsegs, page))
    return _merge_small(frags)


def _layers(row: _Row) -> list[_Row]:
    """Deux textes imprimés l'un sur l'autre (calque masqué, texte écrasé) produiraient un mélange de
    lettres une fois triés par abscisse. On sépare la ligne en « couches » : suites de caractères consécutifs
    dans le flux, qui ne se chevauchent pas entre elles."""
    chars = sorted(row.chars, key=lambda c: c.order)
    runs: list[list[Char]] = []
    for c in chars:
        if runs:
            last = runs[-1][-1]
            if (
                c.order == last.order + 1
                and c.x0 >= last.x0 - 0.5
                and abs(c.size - last.size) < 0.3 * last.size
            ):
                runs[-1].append(c)
                continue
        runs.append([c])
    solid_runs = [r for r in runs if sum(1 for c in r if not c.is_space) >= 3]
    if len(solid_runs) < 2:
        return [row]

    def span(run: list[Char]) -> tuple[float, float]:
        return min(c.x0 for c in run), max(c.x1 for c in run)

    def collide(a: list[Char], b: list[Char]) -> bool:
        (a0, a1), (b0, b1) = span(a), span(b)
        inter = min(a1, b1) - max(a0, b0)
        if inter <= 0.5 * min(a1 - a0, b1 - b0):
            return False
        hits = sum(
            1
            for c in b
            if not c.is_space and any(d.x0 < (c.x0 + c.x1) / 2 < d.x1 for d in a if not d.is_space)
        )
        return hits >= 3

    if not any(collide(a, b) for i, a in enumerate(solid_runs) for b in solid_runs[i + 1 :]):
        return [row]
    layers: list[list[list[Char]]] = []
    for run in sorted(runs, key=len, reverse=True):
        for layer in layers:
            if not any(collide(other, run) or collide(run, other) for other in layer):
                layer.append(run)
                break
        else:
            layers.append([run])
    return [
        _Row(row.top, row.bottom, row.size, row.baseline, [c for run in layer for c in run])
        for layer in layers
    ]


def _crosses_rule(x_a: float, x_b: float, y: float, vsegs: list[Seg]) -> bool:
    return any(x_a - 0.5 <= s.x0 <= x_b + 0.5 and s.top - 1 <= y <= s.bottom + 1 for s in vsegs)


def _split_row(row: _Row, vsegs: list[Seg], page: int) -> list[Frag]:
    cs = sorted(row.chars, key=lambda c: (round(c.x0, 2), c.order))
    groups: list[list[Char]] = []
    cur: list[Char] = []
    extent = None
    pending_space: Char | None = None
    for c in cs:
        if c.is_space:
            if cur:
                pending_space = c
                cur.append(c)
            continue
        if cur and extent is not None:
            gap = c.x0 - extent
            size = max(c.size, row.size * 0.8)
            # un glyphe d'espace ne fait le pont que s'il comble vraiment le blanc (les espaces de fin de
            # ligne, fréquents, ne doivent pas souder deux colonnes)
            bridged = pending_space is not None and gap < 2.5 * size and c.x0 - pending_space.x1 < 0.8 * size
            marker = (
                len(cur) <= 6
                and bool(LIST_MARKER.match("".join(x.text for x in cur).strip()))
                and gap < 4 * size
            )
            split = gap > 1.0 * size and not bridged and not marker
            if gap > 0.5 and _crosses_rule(extent, c.x0, row.baseline, vsegs):
                split = True
            if split:
                groups.append(cur)
                cur = []
        cur.append(c)
        extent = c.x1 if extent is None or not cur[:-1] else max(extent, c.x1)
        pending_space = None
    if cur:
        groups.append(cur)
    # interlettrage typique de toute la ligne, pour les morceaux trop courts pour l'estimer seuls
    gaps = []
    for a, b in zip(cs, cs[1:], strict=False):
        if not a.is_space and not b.is_space and b.x0 - a.x1 < 1.0 * row.size:
            gaps.append(b.x0 - a.x1)
    letter_gap = statistics.median(gaps) if len(gaps) >= 4 else None
    return [f for g in groups if (f := make_frag(g, page, letter_gap)) is not None]


def make_frag(chars: list[Char], page: int, letter_gap: float | None = None) -> Frag | None:
    while chars and chars[-1].is_space:
        chars = chars[:-1]
    solid = [c for c in chars if not c.is_space]
    if not solid:
        return None
    weight: Counter[float] = Counter()
    for c in solid:
        weight[round(c.size, 1)] += len(c.text)
    size = max(weight.items(), key=lambda kv: (kv[1], kv[0]))[0]
    main = [c for c in solid if abs(c.size - size) <= 0.12 * size] or solid
    baseline = statistics.median(c.baseline for c in main)

    def role(c: Char) -> str:
        if c.size <= 0.85 * size:
            if baseline - c.baseline >= 0.2 * size:
                return "sup"
            if c.baseline - baseline >= 0.1 * size:
                return "sub"
        elif baseline - c.baseline >= 0.3 * size:
            return "sup"
        return ""

    # seuil d'espace adapté à l'interlettrage de la ligne (texte éclaté ou serré)
    gaps = []
    prev = None
    for c in chars:
        if c.is_space:
            prev = None
            continue
        if prev is not None:
            gaps.append(c.x0 - prev.x1)
        prev = c
    if len(gaps) >= 4:
        med = statistics.median(gaps)
    else:
        med = letter_gap if letter_gap is not None else 0.0
    threshold = max(0.13 * size, med + 0.12 * size)

    spans: list[Span] = []
    prev = None
    space_pending = False
    for c in chars:
        if c.is_space:
            # un glyphe d'espace imprimé par-dessus la lettre précédente (fréquent) ne sépare rien
            if prev is not None and (c.x0 + c.x1) / 2 >= prev.x1 - 0.15 * size:
                space_pending = True
            continue
        if prev is not None:
            gap = c.x0 - prev.x1
            if space_pending or gap > threshold:
                if spans:
                    spans[-1].text += " "
        r = role(c)
        if spans and spans[-1].role == r:
            spans[-1].text += c.text
        else:
            spans.append(Span(c.text, r))
        prev = c
        space_pending = False
    bold = sum(len(c.text) for c in solid if c.bold) * 2 > sum(len(c.text) for c in solid)
    italic = sum(len(c.text) for c in solid if c.italic) * 2 > sum(len(c.text) for c in solid)
    return Frag(
        spans,
        min(c.x0 for c in solid),
        max(c.x1 for c in solid),
        min(c.top for c in main),
        max(c.bottom for c in main),
        baseline,
        size,
        bold,
        italic,
        page,
    )


def _merge_small(frags: list[Frag]) -> list[Frag]:
    """Rattache un exposant isolé (appel de note très surélevé) au fragment voisin."""
    out = list(frags)
    changed = True
    while changed:
        changed = False
        for f in out:
            if len(f.text.strip()) > 4:
                continue
            cy = (f.top + f.bottom) / 2
            for g in out:
                if g is f or g.size < f.size / 0.85:
                    continue
                if not (g.top - 0.6 * g.size <= cy <= g.bottom):
                    continue
                if -1.0 <= f.x0 - g.x1 <= 0.5 * g.size:
                    g.spans = g.spans + [
                        Span(f.text.strip(), "sup" if cy < g.baseline - 0.3 * g.size else "sub")
                    ]
                elif -1.0 <= g.x0 - f.x1 <= 0.5 * g.size:
                    g.spans = [
                        Span(f.text.strip(), "sup" if cy < g.baseline - 0.3 * g.size else "sub")
                    ] + g.spans
                else:
                    continue
                g.x0, g.x1 = min(g.x0, f.x0), max(g.x1, f.x1)
                out.remove(f)
                changed = True
                break
            if changed:
                break
    return out


# ---------------------------------------------------------------------------------------------------------
# Régions : tableaux et encadrés


def _cluster(values: list[float], tol: float = 2.0) -> list[float]:
    out: list[list[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


def _touch(a: Seg, b: Seg, tol: float = 2.5) -> bool:
    return a.x0 - tol <= b.x1 and b.x0 - tol <= a.x1 and a.top - tol <= b.bottom and b.top - tol <= a.bottom


def detect_regions(page: PageData, frags: list[Frag], body_size: float) -> list[Region]:
    segs = page.segs
    n = len(segs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _touch(segs[i], segs[j]):
                parent[find(i)] = find(j)
    comps: dict[int, list[Seg]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(segs[i])

    page_area = page.width * page.height
    regions: list[Region] = []
    loose_h: list[Seg] = []
    for comp in comps.values():
        hs = [s for s in comp if s.horizontal]
        vs = [s for s in comp if not s.horizontal]
        if not vs:
            loose_h.extend(hs)
            continue
        if not hs:
            continue
        x0, x1 = min(s.x0 for s in comp), max(s.x1 for s in comp)
        top, bottom = min(s.top for s in comp), max(s.bottom for s in comp)
        if (x1 - x0) * (bottom - top) >= 0.85 * page_area:
            continue  # cadre de page
        ys = _cluster([(s.top + s.bottom) / 2 for s in hs])
        xs = _cluster([(s.x0 + s.x1) / 2 for s in vs])
        if len(xs) >= 3 and len(ys) >= 2:
            regions.append(Region("table", x0, top, x1, bottom, xs, ys))
        elif len(xs) >= 2 and len(ys) >= 2:
            regions.append(Region("box", x0, top, x1, bottom))

    regions.extend(_rule_tables(loose_h, frags))
    for fl in page.fills:
        area = (fl.x1 - fl.x0) * (fl.bottom - fl.top)
        if area < 0.85 * page_area and fl.bottom - fl.top > 2.5 * body_size:
            if not any(_inside(fl, r) or _inside(r, fl) for r in regions):
                regions.append(Region("box", fl.x0, fl.top, fl.x1, fl.bottom))

    # arbre d'inclusion, affectation des fragments à la région la plus intérieure
    regions.sort(key=lambda r: (r.x1 - r.x0) * (r.bottom - r.top), reverse=True)
    roots: list[Region] = []
    for r in regions:
        host = None
        for cand in _walk(roots):
            if _inside(r, cand):
                host = cand
        (host.children if host else roots).append(r)
    for f in frags:
        cx, cy = (f.x0 + f.x1) / 2, (f.top + f.bottom) / 2
        host = None
        for cand in _walk(roots):
            if cand.contains(cx, cy):
                host = cand
        if host:
            host.frags.append(f)
    for i, r in enumerate(_walk(roots), start=1):
        r.ident = page.index * 1000 + i
    roots = _prune(roots)
    return roots


def _prune(regions: list[Region]) -> list[Region]:
    out = []
    for r in regions:
        r.children = _prune(r.children)
        if r.frags or r.children:
            out.append(r)
    return out


def _walk(regions: list[Region]):
    for r in regions:
        yield r
        yield from _walk(r.children)


def _inside(a, b, tol: float = 2.0) -> bool:
    return a.x0 >= b.x0 - tol and a.x1 <= b.x1 + tol and a.top >= b.top - tol and a.bottom <= b.bottom + tol


def _rule_tables(hs: list[Seg], frags: list[Frag]) -> list[Region]:
    """Tableaux sans filets verticaux : filets horizontaux de même largeur, consécutifs, encadrant des
    lignes de plusieurs cellules courtes. Une bande de texte suivi (prose en colonnes) arrête le tableau :
    un filet de pied de page de même largeur ne doit pas l'étendre jusqu'en bas de page."""
    out: list[Region] = []
    hs = sorted((s for s in hs if s.x1 - s.x0 >= 50), key=lambda s: s.top)
    # filets doublés (même position) : un seul
    uniq: list[Seg] = []
    for s in hs:
        if not any(abs(s.top - u.top) < 1 and abs(s.x0 - u.x0) < 2 and abs(s.x1 - u.x1) < 2 for u in uniq):
            uniq.append(s)
    hs = uniq

    def band(x0: float, x1: float, top: float, bottom: float) -> list[Frag]:
        return [
            f for f in frags if x0 - 2 <= f.x0 and f.x1 <= x1 + 2 and top <= (f.top + f.bottom) / 2 <= bottom
        ]

    def tabular(inside: list[Frag], x0: float, x1: float) -> bool:
        if not inside:
            return False
        rows = _rows_of(inside)
        multi = sum(1 for r in rows if len(r) >= 2)
        wide = any(f.x1 - f.x0 > 0.7 * (x1 - x0) for f in inside)
        prose = sum(1 for f in inside if len(f.text) > 50)
        return multi >= 0.5 * len(rows) and not wide and prose <= 0.3 * len(inside)

    used: set[int] = set()
    for i, s in enumerate(hs):
        if i in used:
            continue
        group = [s]
        for j in range(i + 1, len(hs)):
            t = hs[j]
            if abs(t.x0 - s.x0) > 4 or abs(t.x1 - s.x1) > 4:
                continue
            inside = band(s.x0, s.x1, group[-1].top, t.top)
            if inside and not tabular(inside, s.x0, s.x1):
                break
            group.append(t)
            used.add(j)
        if len(group) < 2:
            continue
        x0, x1 = s.x0, s.x1
        top, bottom = group[0].top, group[-1].bottom
        inside = band(x0, x1, top, bottom)
        if len(_rows_of(inside)) >= 2 and tabular(inside, x0, x1):
            out.append(Region("table", x0, top, x1, bottom, [], [g.top for g in group]))
    return out


def is_drop_cap(frag, size: float) -> bool:
    """Lettrine : une ou deux lettres au moins deux fois plus grandes que le texte qu'elles ouvrent."""
    t = frag.text.strip()
    return 1 <= len(t) <= 2 and t[0].isalpha() and frag.size >= 2 * size


def _drop_cap_rows(frags: list) -> dict[int, float]:
    """Ligne de base à retenir pour chaque lettrine : celle de la première ligne de texte à sa droite.

    Une lettrine descend sur plusieurs lignes et sa ligne de base est celle de la dernière : sans
    correction, elle serait rangée avec cette dernière ligne et l'ordre des premières lignes s'inverserait.
    """
    out: dict[int, float] = {}
    if len(frags) < 2:
        return out
    for f in frags:
        t = f.text.strip()
        if not (1 <= len(t) <= 2 and t[0].isalpha()):
            continue
        right = [
            g
            for g in frags
            if g is not f
            and g.x0 >= f.x1 - 1
            and g.x0 <= f.x1 + 3 * f.size
            and g.top < f.bottom
            and g.bottom > f.top
            and is_drop_cap(f, g.size)
        ]
        if len(right) >= 2:
            out[id(f)] = min(right, key=lambda g: g.top).baseline
    return out


def _rows_of(frags: list) -> list[list]:
    caps = _drop_cap_rows(frags)

    def base(f) -> float:
        return caps.get(id(f), f.baseline)

    def size(f) -> float:
        return f.size if id(f) not in caps else 0.0

    rows: list[list] = []
    for f in sorted(frags, key=base):
        if rows:
            ref = next((g for g in rows[-1] if id(g) not in caps), rows[-1][0])
            tol = 0.5 * min(s for s in (size(f), size(ref)) if s > 0) if size(f) or size(ref) else 1.0
            if abs(base(ref) - base(f)) < tol:
                rows[-1].append(f)
                continue
        rows.append([f])
    for r in rows:
        r.sort(key=lambda f: f.x0)
    return rows


# ---------------------------------------------------------------------------------------------------------
# Notes de bas de page

_NOTE_MARK = re.compile(r"^\s*(\d{1,3}|[*†‡§¶]+)(?:[.)]\s*|\s+)(?=\S)")


def note_marker(frag) -> str | None:
    """Numéro de note en tête de ligne (exposant ou « 3. »), ou None."""
    spans = [s for s in frag.spans if s.text.strip()]
    if not spans:
        return None
    first = spans[0]
    if first.role == "sup" and re.fullmatch(r"\s*(\d{1,3}|[*†‡§¶]+)\s*", first.text) and len(spans) > 1:
        return first.text.strip()
    m = _NOTE_MARK.match(frag.text)
    return m.group(1) if m else None


def split_footnotes(page: PageData, frags: list[Frag], body_size: float, prev_had_notes: bool) -> list[Frag]:
    """Retire de `frags` les notes de bas de page (stockées dans `page.footnotes`) ; renvoie le reste."""
    if not frags:
        return frags
    by_bottom = sorted(frags, key=lambda f: -f.bottom)
    block: list[Frag] = []
    for f in by_bottom:
        if f.size <= 0.92 * body_size:
            block.append(f)
        else:
            break
    if not block or len(block) == len(frags):
        return frags
    block.sort(key=lambda f: (f.top, f.x0))
    rest = [f for f in frags if f not in block]
    body_bottom = max(f.bottom for f in rest)
    calls = {
        s.text.strip()
        for f in rest
        for i, s in enumerate(f.spans)
        if s.role == "sup" and i > 0 and s.text.strip()
    }
    hrules = [s for s in page.segs if s.horizontal and s.x1 - s.x0 < 0.6 * page.width]

    def rule_above(f: Frag, upper: float) -> bool:
        return any(upper - 1 <= s.top <= f.top + 1 for s in hrules)

    start = None
    for i, f in enumerate(block):
        upper = block[i - 1].bottom if i > 0 else body_bottom
        mark = note_marker(f)
        if mark and (mark in calls or rule_above(f, upper)):
            start = i
            break
        if i == 0 and prev_had_notes and rule_above(f, upper):
            start = 0
            break
    if start is None:
        return frags
    notes = block[start:]
    upper = block[start - 1].bottom if start > 0 else body_bottom
    page.footnotes = [
        _line(row, page.index, (min(f.x0 for f in notes), max(f.x1 for f in notes)))
        for row in _rows_of(notes)
    ]
    keep = set(map(id, notes))
    return [f for f in frags if id(f) not in keep]


# ---------------------------------------------------------------------------------------------------------
# Gouttières : un grand blanc entre deux mots n'est une séparation de colonnes que s'il se prolonge,
# aligné, sur plusieurs lignes. Sinon (texte justifié lâche), les morceaux de ligne sont recollés.


def find_gutters(frags: list[Frag], min_gap: float) -> list[tuple[float, float, float, float]]:
    """Rectangles blancs verticaux (x0, x1, haut, bas) bordés de texte sur au moins trois lignes."""
    rows = _rows_of(frags)
    if len(rows) < 3:
        return []
    left_edge = min(f.x0 for f in frags)
    right_edge = max(f.x1 for f in frags)
    row_gaps: list[list[tuple[float, float, bool]]] = []
    for row in rows:
        gaps = []
        if row[0].x0 - left_edge >= min_gap:
            gaps.append((left_edge, row[0].x0, False))
        end = row[0].x1
        for f in row[1:]:
            if f.x0 - end >= min_gap:
                gaps.append((end, f.x0, True))
            end = max(end, f.x1)
        if right_edge - end >= min_gap:
            gaps.append((end, right_edge, False))
        row_gaps.append(gaps)
    found: list[tuple[float, float, float, float]] = []
    active: dict[tuple[float, float, int], int] = {}  # (x0, x1, première ligne) → lignes bordées
    for r, gaps in enumerate(row_gaps + [[]]):
        nxt: dict[tuple[float, float, int], int] = {}
        for (a, b, start), bounded in active.items():
            cont = False
            for g0, g1, gb in gaps:
                lo, hi = max(a, g0), min(b, g1)
                if hi - lo >= 0.6 * min_gap:
                    key = (round(lo, 1), round(hi, 1), start)
                    nxt[key] = max(nxt.get(key, 0), bounded + int(gb))
                    cont = True
            if not cont and r - start >= 3 and bounded >= 3:
                top = min(f.top for f in rows[start])
                bottom = max(f.bottom for f in rows[r - 1])
                found.append((a, b, top, bottom))
        for g0, g1, gb in gaps:
            if gb:
                key = (round(g0, 1), round(g1, 1), r)
                nxt.setdefault(key, 1)
        # élague les candidats inclus dans un autre plus ancien
        active = {}
        for key in sorted(nxt, key=lambda k: (k[2], k[0] - k[1])):
            if any(o[2] <= key[2] and o[0] <= key[0] and key[1] <= o[1] for o in active):
                continue
            active[key] = nxt[key]
    return found


def merge_word_gaps(frags: list[Frag], gutters, vsegs: list[Seg]) -> list[Frag]:
    rows = _rows_of(frags)
    out: list[Frag] = []
    for row in rows:
        cur = row[0]
        for f in row[1:]:
            a, b = cur.x1, f.x0
            y = cur.baseline
            gutter = any(
                g0 < b and a < g1 and min(b, g1) - max(a, g0) > 0.5 and t - 1 <= y <= bt + 1
                for g0, g1, t, bt in gutters
            )
            if gutter or _crosses_rule(a, b, y, vsegs) or abs(f.size - cur.size) > 0.2 * cur.size:
                out.append(cur)
                cur = f
                continue
            spans = cur.spans + ([] if cur.text.endswith(" ") else [Span(" ")]) + f.spans
            total = len(cur.text) + len(f.text)
            cur = Frag(
                spans,
                cur.x0,
                max(cur.x1, f.x1),
                min(cur.top, f.top),
                max(cur.bottom, f.bottom),
                cur.baseline if len(cur.text) >= len(f.text) else f.baseline,
                cur.size if len(cur.text) >= len(f.text) else f.size,
                (len(cur.text) * cur.bold + len(f.text) * f.bold) * 2 > total,
                (len(cur.text) * cur.italic + len(f.text) * f.italic) * 2 > total,
                cur.page,
            )
        out.append(cur)
    return out


# ---------------------------------------------------------------------------------------------------------
# Ordre de lecture (découpage XY récursif)


def _bbox(item) -> tuple[float, float, float, float]:
    return item.bbox


def _vcuts(items: list, min_gap: float) -> list[float]:
    if len(items) < 2:
        return []
    ivs = sorted((_bbox(i)[0], _bbox(i)[2]) for i in items)
    gaps = []
    end = ivs[0][1]
    for a, b in ivs[1:]:
        if a - end >= min_gap:
            gaps.append((end, a))
        end = max(end, b)
    cuts = []
    for a, b in gaps:
        left = [i for i in items if _bbox(i)[2] <= a + 0.01]
        right = [i for i in items if _bbox(i)[0] >= b - 0.01]
        lt, lb = min(_bbox(i)[1] for i in left), max(_bbox(i)[3] for i in left)
        rt, rb = min(_bbox(i)[1] for i in right), max(_bbox(i)[3] for i in right)
        overlap = min(lb, rb) - max(lt, rt)
        if overlap > 0.3 * min(lb - lt, rb - rt) and overlap > 0:
            cuts.append((a + b) / 2)
    return cuts


def _hbands(items: list) -> list[list]:
    bands: list[list] = []
    bottom = None
    for it in sorted(items, key=lambda i: (_bbox(i)[1], _bbox(i)[0])):
        x0, top, x1, bot = _bbox(it)
        if bands and top < bottom - 0.5:
            bands[-1].append(it)
            bottom = max(bottom, bot)
        else:
            bands.append([it])
            bottom = bot
    return bands


def _line(frags: list[Frag], page: int, col: tuple[float, float], region: int = 0) -> Line:
    frags = sorted(frags, key=lambda f: f.x0)
    spans: list[Span] = []
    main = max(frags, key=lambda f: (len(f.text), f.size))
    prev = None
    for f in frags:
        # lettrine suivie de la fin de son mot (« L » + « e vieux baron ») : pas d'espace entre les deux
        glued = (
            prev is not None
            and is_drop_cap(prev, f.size)
            and f.text[:1].islower()
            and f.x0 - prev.x1 < f.size
        )
        if spans and not spans[-1].text.endswith(" ") and not glued:
            spans.append(Span(" "))
        spans.extend(Span(s.text, s.role) for s in f.spans)
        prev = f
    total = sum(len(f.text) for f in frags)
    return Line(
        spans,
        frags[0].x0,
        max(f.x1 for f in frags),
        min(f.top for f in frags),
        max(f.bottom for f in frags),
        main.baseline,
        main.size,
        sum(len(f.text) for f in frags if f.bold) * 2 > total,
        sum(len(f.text) for f in frags if f.italic) * 2 > total,
        page,
        col[0],
        col[1],
        region,
    )


class _Orderer:
    def __init__(self, page: int, min_gap: float, vsegs: list[Seg] | None = None) -> None:
        self.page = page
        self.min_gap = min_gap
        self.vsegs = vsegs or []

    def merge(self, frags: list[Frag]) -> list[Frag]:
        if len(frags) < 2:
            return list(frags)
        return merge_word_gaps(frags, find_gutters(frags, self.min_gap), self.vsegs)

    def order(self, items: list, col: tuple[float, float], region: int) -> list:
        if not items:
            return []
        if len(items) == 1 and isinstance(items[0], Region):
            return self.region(items[0], region)
        cuts = _vcuts(items, self.min_gap)
        if cuts:
            out = []
            bounds = [-1e9, *cuts, 1e9]
            for lo, hi in zip(bounds, bounds[1:], strict=False):
                group = [i for i in items if lo <= (_bbox(i)[0] + _bbox(i)[2]) / 2 < hi]
                if group:
                    gcol = (min(_bbox(i)[0] for i in group), max(_bbox(i)[2] for i in group))
                    out.extend(self.order(group, gcol, region))
            return out
        bands = _hbands(items)
        if len(bands) == 1:
            return self.leaf(items, col, region)
        groups: list[list] = [bands[0]]
        for b in bands[1:]:
            # une bande ne rejoint le groupe précédent que si celui-ci est déjà en colonnes
            if (
                len(groups[-1]) > 1
                and _vcuts(groups[-1], self.min_gap)
                and _vcuts(groups[-1] + b, self.min_gap)
            ):
                groups[-1] = groups[-1] + b
            else:
                groups.append(b)
        out = []
        for g in groups:
            out.extend(self.order(g, col, region) if len(g) < len(items) else self.leaf(g, col, region))
        return out

    def leaf(self, items: list, col: tuple[float, float], region: int) -> list:
        out: list = []
        frags = [i for i in items if isinstance(i, Frag)]
        regions = [i for i in items if isinstance(i, Region)]
        rows = _rows_of(frags)
        entries = [(r[0].top, 0, r) for r in rows] + [(g.top, 1, g) for g in regions]
        for _top, kind, obj in sorted(entries, key=lambda e: (e[0], e[1])):
            if kind == 0:
                out.append(_line(obj, self.page, col, region))
            else:
                out.extend(self.region(obj, region))
        return out

    def region(self, reg: Region, parent: int) -> list:
        if reg.kind == "table":
            table = self.table(reg)
            cells = [cell for row in table.rows for cell in row]
            full_rows = sum(1 for row in table.rows if sum(1 for c in row if c) >= 2)
            if cells and sum(1 for c in cells if c) >= 0.4 * len(cells) and full_rows >= 2:
                return [table]
            # quadrillage presque vide (graphique, formulaire) : lu comme du texte ordinaire
            frags = list(reg.frags)
            for child in _walk(reg.children):
                frags.extend(child.frags)
            return self.order(self.merge(frags), (reg.x0, reg.x1), parent)
        items = self.merge(reg.frags) + list(reg.children)
        return self.order(items, (reg.x0, reg.x1), reg.ident)

    def table(self, reg: Region) -> TableItem:
        frags = list(reg.frags)
        for child in _walk(reg.children):
            frags.extend(child.frags)
        if len(reg.xs) >= 3:
            xb = reg.xs
        else:
            ivs = sorted((f.x0, f.x1) for f in frags)
            cols: list[list[float]] = []
            for a, b in ivs:
                if cols and a <= cols[-1][1] + 2:
                    cols[-1][1] = max(cols[-1][1], b)
                else:
                    cols.append([a, b])
            xb = [reg.x0] + [(cols[i][1] + cols[i + 1][0]) / 2 for i in range(len(cols) - 1)] + [reg.x1]
        if len(reg.ys) >= 3 and len(reg.xs) >= 3:
            yb = reg.ys
        else:
            text_rows = _rows_of(frags)
            yb = (
                [reg.top]
                + [
                    (max(f.bottom for f in text_rows[i]) + min(f.top for f in text_rows[i + 1])) / 2
                    for i in range(len(text_rows) - 1)
                ]
                + [reg.bottom]
            )
            if len(reg.ys) >= 3:  # filets horizontaux intermédiaires : ils séparent aussi des lignes
                yb = sorted(set(yb))
        ncols, nrows = len(xb) - 1, len(yb) - 1
        grid: list[list[list[Frag]]] = [[[] for _ in range(ncols)] for _ in range(nrows)]
        for f in frags:
            cx, cy = (f.x0 + f.x1) / 2, (f.top + f.bottom) / 2
            ci = max(0, min(ncols - 1, sum(1 for x in xb[1:-1] if cx > x)))
            ri = max(0, min(nrows - 1, sum(1 for y in yb[1:-1] if cy > y)))
            grid[ri][ci].append(f)
        rows: list[list[list[Line]]] = []
        for ri in range(nrows):
            cells = []
            for ci in range(ncols):
                cell_frags = grid[ri][ci]
                cells.append([_line(r, self.page, (xb[ci], xb[ci + 1])) for r in _rows_of(cell_frags)])
            if any(cells):
                rows.append(cells)
        return TableItem(self.page, rows, reg.top)


def reading_order(page: PageData, frags: list[Frag], regions: list[Region], body_size: float) -> list:
    """Renvoie les lignes (`Line`) et tableaux (`TableItem`) de la page dans l'ordre de lecture."""
    in_region = set()
    for r in _walk(regions):
        in_region.update(map(id, r.frags))
    orderer = _Orderer(page.index, max(5.0, 0.6 * body_size), [s for s in page.segs if not s.horizontal])
    items: list = orderer.merge([f for f in frags if id(f) not in in_region]) + list(regions)
    if not items:
        return []
    col = (min(_bbox(i)[0] for i in items), max(_bbox(i)[2] for i in items))
    out = orderer.order(items, col, 0)
    _column_extents(out)
    return out


def _column_extents(items: list) -> None:
    """Largeur de colonne de chaque ligne : étendue de la suite de lignes voisines (même colonne) à laquelle
    elle appartient. Sert à reconnaître une ligne courte (fin de paragraphe)."""
    run: list[Line] = []

    def close() -> None:
        if run:
            x0, x1 = min(ln.x0 for ln in run), max(ln.x1 for ln in run)
            for ln in run:
                ln.col_x0, ln.col_x1 = x0, x1
        run.clear()

    for it in items:
        if not isinstance(it, Line):
            close()
            continue
        if run:
            prev = run[-1]
            adjacent = (
                prev.region == it.region
                and 0 < it.baseline - prev.baseline <= 2.2 * max(it.size, prev.size)
                and it.x0 < prev.x1
                and prev.x0 < it.x1
                and abs(it.size - prev.size) <= 0.25 * prev.size
            )
            if not adjacent:
                close()
        run.append(it)
    close()


def starts_with_bullet(text: str) -> bool:
    return bool(text) and text[0] in _LIST_GLYPHS
