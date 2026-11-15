"""Structure du document : lignes en ordre de lecture → blocs (paragraphes, titres, listes, notes,
tableaux, légendes) → chapitres."""

import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from voxpage.document import Block, Chapter
from voxpage.extract.pdf_layout import Line, TableItem, note_marker, starts_with_bullet
from voxpage.extract.pdf_text import WordStats, clean_text, ends_with_break_hyphen, join_lines

_TERMINAL = tuple('.!?…:»”")')
_NUMBERED = re.compile(r"^(?:\(?\d{1,3}[.)]|\(?[a-z][.)]|\(?[ivx]{1,5}[.)])\s+\S")
_BULLET = re.compile(r"^[•◦▪▫‣⁃●○■□►▶➢➤✓✔∙·]\s*")
_DASH_ITEM = re.compile(r"^[–-]\s+\S")
_LEADING_ZERO = re.compile(r"^\(?0\d")
_ORNAMENT = re.compile(r"^[a-z]$")
_CAPTION = re.compile(
    r"^(?:Figure|Fig\.|Tableau|Table|Illustration|Graphique|Schéma|Carte|Photo|Image|Planche|Chart|Graph|"
    r"Plate|Encadré)\s*(?:n°\s*)?(?:\d+|[IVXLC]+)(?:[.-]\d+)?[a-z]?\s*[.:—–−-]",
)
_UNITS = frozenset("m cm mm km dm µm nm m/s s kg g l dl cl ml".split())
_SUPERSCRIPT = str.maketrans("0123456789+-−=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿ")
_CALL = re.compile(r"^(?:\d{1,3}|[*†‡§¶]{1,3})(?:[,;]\s?(?:\d{1,3}|[*†‡§¶]{1,3}))*$")


# ---------------------------------------------------------------------------------------------------------
# Rendu d'une ligne : exposants, appels de note


def _exponent_base(before: str, last_word: str) -> bool:
    """Le texte qui précède un chiffre en exposant en fait-il un exposant mathématique (10³, m², (a+b)²)
    plutôt qu'un appel de note (« en 2018⁶ », « (croissance acquise)⁴ ») ?"""
    if last_word in _UNITS:
        return True
    if before[-1] == ")":
        inner = before[before.rfind("(") + 1 : -1] if "(" in before else ""
        return bool(inner) and " " not in inner.strip()  # (a+b)² ; une parenthèse de prose a des espaces
    if before[-1].isdigit():
        m = re.search(r"(\d+)$", before)
        year = m is not None and len(m.group(1)) == 4 and 1500 <= int(m.group(1)) <= 2100
        return not year  # « en 2018⁶ » : une année porte un appel de note, pas une puissance
    return False


def render_line(line: Line) -> tuple[str, list[str]]:
    """Texte brut de la ligne et appels de note qu'elle contient (retirés du texte)."""
    out = ""
    calls: list[str] = []
    for span in line.spans:
        if span.role != "sup":
            out += span.text
            continue
        t = span.text.strip()
        trail = " " if span.text.endswith(" ") else ""
        if not t:
            out += span.text
            continue
        if _CALL.match(t):
            before = out.rstrip()
            last_word = before.split(" ")[-1].lower() if before else ""
            if not before:
                out += t + " "  # marque en tête de ligne (note non détectée) : gardée telle quelle
            elif t.isdigit() and _exponent_base(before, last_word):
                out += t.translate(_SUPERSCRIPT) + trail  # exposant mathématique : 10 m², 10³
            else:
                calls.extend(re.split(r"[,;]\s?", t))
                out += trail
        else:
            out += span.text  # « 1er », « XIXe », « Mlle »
    return out, calls


# ---------------------------------------------------------------------------------------------------------
# Éléments flottants


def _short(line: Line) -> bool:
    width = line.col_x1 - line.col_x0
    return line.x1 < line.col_x1 - max(0.12 * width, 2 * line.size)


def _body(item) -> bool:
    return isinstance(item, Line) and item.region == 0


def _below(prev: Line, line: Line) -> bool:
    """`line` suit `prev` dans la même colonne (juste en dessous, sur la même page)."""
    return (
        prev.page == line.page
        and line.top > prev.top + 0.3 * line.size
        and line.top - prev.bottom < 1.5 * line.size
        and line.x0 < prev.x1
        and prev.x0 < line.x1
    )


def _same_font(a: Line, b: Line) -> bool:
    return abs(a.size - b.size) <= 0.08 * max(a.size, b.size) and a.bold == b.bold


def reorder_continuations(stream: list, body_size: float) -> list:
    """Paragraphe interrompu au milieu d'une phrase par un encadré, un tableau, une figure ou une autre
    colonne : on cherche sa suite (première ligne d'une colonne, en minuscule, même police, sur la même page
    ou la suivante) et on la remonte juste après lui. Le contenu intercalé est lu ensuite, rien n'est perdu.
    """
    items = list(stream)
    texts = {id(it): render_line(it)[0].strip() for it in items if isinstance(it, Line)}

    def mid_sentence(line: Line) -> bool:
        t = texts[id(line)]
        return bool(t) and (ends_with_break_hyphen(t) or not t.endswith(_TERMINAL + (";",)))

    def continues(prev: Line, line: Line) -> bool:
        t = texts[id(line)]
        return bool(t) and (ends_with_break_hyphen(texts[id(prev)]) or t[0].islower())

    i = 0
    while i < len(items) - 1:
        it = items[i]
        nxt = items[i + 1]
        if (
            not (_body(it) and mid_sentence(it))
            or abs(it.size - body_size) > 0.08 * body_size  # seul le texte courant est concerné
            or (_body(nxt) and _below(it, nxt))  # la colonne continue : pas d'interruption
            or (_body(nxt) and continues(it, nxt) and _same_font(it, nxt))
        ):
            i += 1
            continue
        found = None
        for j in range(i + 2, min(len(items), i + 600)):
            cand = items[j]
            if isinstance(cand, Line) and cand.page > it.page + 1:
                break
            if not (_body(cand) and _same_font(it, cand) and continues(it, cand)):
                continue
            before = items[j - 1]
            if _body(before) and _below(before, cand) and _same_font(before, cand):
                continue  # pas une tête de colonne
            if _body(before) and mid_sentence(before) and _same_font(before, cand):
                continue  # c'est la suite d'un autre paragraphe
            found = j
            break
        if found is None:
            i += 1
            continue
        k = found
        while (
            k + 1 < len(items)
            and _body(items[k + 1])
            and _below(items[k], items[k + 1])
            and not (texts[id(items[k])].endswith(_TERMINAL) and _short(items[k]))
        ):
            k += 1
        segment = items[found : k + 1]
        del items[found : k + 1]
        items[i + 1 : i + 1] = segment
        i += 1
    return items


# ---------------------------------------------------------------------------------------------------------
# Blocs


@dataclass
class _Block:
    kind: str
    lines: list[Line] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    calls: list[tuple[int, str]] = field(default_factory=list)
    level: int = 0
    text: str = ""
    marker: str = ""

    @property
    def page(self) -> int:
        return self.lines[0].page if self.lines else 0

    @property
    def pages(self) -> set[int]:
        return {ln.page for ln in self.lines}

    @property
    def size(self) -> float:
        weights: Counter[float] = Counter()
        for ln in self.lines:
            weights[round(ln.size * 2) / 2] += len(ln.text)
        return weights.most_common(1)[0][0] if weights else 0.0

    @property
    def bold(self) -> bool:
        total = sum(len(ln.text) for ln in self.lines)
        return sum(len(ln.text) for ln in self.lines if ln.bold) * 2 > total


@dataclass
class Note:
    page: int
    marker: str
    texts: list[str]


@dataclass
class Bookmark:
    title: str
    level: int
    page: int  # index à partir de 0
    top: float | None  # position verticale (de haut en bas), si connue


def body_size_of(lines_sizes: Counter) -> float:
    if not lines_sizes:
        return 10.0
    return max(lines_sizes.items(), key=lambda kv: (kv[1], -kv[0]))[0]


class Builder:
    def __init__(self, body_size: float, stats: WordStats) -> None:
        self.body = body_size
        self.stats = stats
        self.blocks: list[_Block] = []
        self.cur: _Block | None = None
        self.prev: Line | None = None
        self.leading: dict[float, float] = {}

    # -- interligne typique par taille de police
    def learn_leading(self, items: list) -> None:
        spacings: dict[float, list[float]] = defaultdict(list)
        prev = None
        for it in items:
            if not isinstance(it, Line):
                prev = None
                continue
            if (
                prev is not None
                and prev.page == it.page
                and prev.region == it.region
                and abs(prev.size - it.size) < 0.3
            ):
                d = it.baseline - prev.baseline
                if 0.8 * it.size <= d <= 2.5 * it.size and prev.x0 < it.x1 and it.x0 < prev.x1:
                    spacings[round(it.size * 2) / 2].append(d)
            prev = it
        self.leading = {k: statistics.median(v) for k, v in spacings.items() if v}

    def expected_leading(self, size: float) -> float:
        return self.leading.get(round(size * 2) / 2, 1.2 * size)

    def flush(self) -> None:
        if self.cur and self.cur.lines:
            self.blocks.append(self.cur)
        self.cur = None

    def table(self, item: TableItem) -> None:
        self.flush()
        self.prev = None
        rows = []
        calls: list[tuple[int, str]] = []
        all_lines: list[Line] = []
        for row in item.rows:
            cells = []
            for cell in row:
                text = ""
                prev_t = ""
                for ln in cell:
                    t, c = render_line(ln)
                    calls.extend((ln.page, x) for x in c)
                    text = join_lines(text, t, self.stats) if prev_t else t
                    prev_t = t
                    all_lines.append(ln)
                cells.append(clean_text(text))
            rows.append("; ".join(cells))
        if not all_lines:
            return
        b = _Block("table", lines=all_lines, calls=calls)
        b.text = "\n".join(r for r in rows if r.strip("; "))
        self.blocks.append(b)

    def start(self, kind: str, line: Line, text: str, calls: list[str]) -> None:
        self.flush()
        self.cur = _Block(kind)
        self.append(line, text, calls)

    def append(self, line: Line, text: str, calls: list[str]) -> None:
        assert self.cur is not None
        self.cur.lines.append(line)
        self.cur.texts.append(text)
        self.cur.calls.extend((line.page, c) for c in calls)
        self.prev = line

    def add(self, line: Line, text: str, calls: list[str]) -> None:
        stripped = text.strip()
        if not stripped:
            return
        bullet = starts_with_bullet(stripped) or bool(_DASH_ITEM.match(stripped))
        cur, prev = self.cur, self.prev
        prev_text = cur.texts[-1].rstrip() if cur and cur.texts else ""
        numbered = (
            bool(_NUMBERED.match(stripped))
            and not _LEADING_ZERO.match(stripped)  # « 089) ; » : suite d'une référence coupée, pas un numéro
            and not ends_with_break_hyphen(prev_text)
            and (
                cur is None
                or prev_text.endswith(_TERMINAL + (";",))
                or cur.kind == "list_item"
                or prev is None
            )
        )
        if cur is None or prev is None:
            self.start("list_item" if bullet or numbered else "paragraph", line, text, calls)
            return
        if bullet or numbered:
            if not (
                bullet
                and stripped[0] in "–—-"
                and cur.kind == "paragraph"
                and not prev_text.endswith(_TERMINAL)
            ):
                self.start("list_item", line, text, calls)
                return
        same_size = abs(line.size - cur.lines[-1].size) <= 0.08 * max(line.size, 1)
        # passage gras/maigre : nouveau bloc, sauf au milieu d'une phrase (ligne suivante en minuscule)
        mid_sentence = not prev_text.endswith(_TERMINAL) and stripped[0].islower()
        same_font = same_size and (line.bold == prev.bold or mid_sentence)
        if line.region != prev.region or not same_font:
            self.start("paragraph", line, text, calls)
            return
        jump = not (
            line.page == prev.page
            and line.top > prev.top + 0.3 * line.size
            and line.x0 < prev.x1
            and prev.x0 < line.x1
        )
        indent = line.x0 - line.col_x0 > 0.8 * line.size
        if jump:
            # changement de colonne ou de page : le paragraphe continue-t-il ?
            if abs(line.baseline - prev.baseline) < 0.3 * line.size:
                # même ligne de base, plus à droite : autre colonne ou cellule
                cont = not prev_text.endswith(_TERMINAL) and stripped[0].islower()
            elif cur.kind == "list_item":
                cont = (indent and not (prev_text.endswith(_TERMINAL) and _short(prev))) or (
                    not prev_text.endswith(_TERMINAL) and stripped[0].islower()
                )
            elif ends_with_break_hyphen(prev_text):
                cont = True
            elif not prev_text.endswith(_TERMINAL):
                cont = not indent or not stripped[0].isupper()
            else:
                cont = not indent and not _short(prev)
            if cont and cur.kind in ("paragraph", "list_item"):
                self.append(line, text, calls)
            else:
                self.start("paragraph", line, text, calls)
            return
        spacing = line.baseline - prev.baseline
        expected = self.expected_leading(line.size)
        if len(cur.lines) >= 2:
            last = cur.lines[-1].baseline - cur.lines[-2].baseline
            if cur.lines[-1].page == cur.lines[-2].page and 0.8 * line.size <= last < expected:
                expected = last
        if spacing > 1.35 * expected and spacing > expected + 0.25 * line.size:
            self.start("paragraph", line, text, calls)
            return
        if cur.kind == "list_item":
            first = cur.lines[0]
            # élément de liste dont les lignes suivantes reviennent à la marge (sans retrait) : la phrase
            # continue si la ligne précédente, pleine, ne la termine pas
            wraps = not _short(prev) and (
                ends_with_break_hyphen(prev_text) or not prev_text.endswith(_TERMINAL + (";",))
            )
            if line.x0 <= first.x0 + 0.3 * line.size and not indent and not wraps:
                self.start("paragraph", line, text, calls)
            else:
                self.append(line, text, calls)
            return
        if _short(prev) and (
            prev_text.endswith(_TERMINAL) or (prev_text.endswith(";") and stripped[0].isupper())
        ):
            self.start("paragraph", line, text, calls)
            return
        width = max(prev.col_x1 - prev.col_x0, 1.0)
        if (
            (prev.x1 - prev.x0) < 0.6 * width
            and (stripped[0].isupper() or stripped[0].isdigit())
            and (len(cur.lines) == 1 or prev_text.endswith(_TERMINAL))
        ):
            self.start("paragraph", line, text, calls)  # ligne isolée très courte : bloc à part
            return
        prev_indent = prev.x0 - prev.col_x0 > 0.8 * prev.size
        if (
            indent
            and not prev_indent
            and abs(line.x0 - prev.x0) > 0.8 * line.size
            and prev_text.endswith(_TERMINAL)
        ):
            self.start("paragraph", line, text, calls)
            return
        self.append(line, text, calls)

    def finish(self) -> list[_Block]:
        self.flush()
        for b in self.blocks:
            if b.kind == "table":
                continue
            text = ""
            for t in b.texts:
                text = join_lines(text, t, self.stats) if text else t
            b.text = clean_text(text)
        # une lettre minuscule seule formant un bloc : vignette ou fleuron d'une police décorative (« n »)
        return [b for b in self.blocks if b.text and not (b.kind == "paragraph" and _ORNAMENT.match(b.text))]


def word_stats(rendered: list[str]) -> WordStats:
    stats = WordStats()
    prev = ""
    for t in rendered:
        if ends_with_break_hyphen(prev):
            stats.add_line_after_break(t)
        else:
            stats.add_line(t)
        prev = t
    return stats


def classify(blocks: list[_Block], body: float) -> None:
    for b in blocks:
        if b.kind in ("table", "footnote"):
            continue
        text = b.text
        n_lines = len(b.lines)
        size = b.size
        if len(text) <= 400 and n_lines <= 4 and _CAPTION.match(text):
            b.kind = "caption"
            continue
        first_alpha = next((c for c in text if c.isalpha()), "")
        big = size >= 1.15 * body and n_lines <= 3 and len(text) <= 200
        strong = (
            b.bold
            and size >= 0.95 * body
            and n_lines <= 2
            and len(text) <= 150
            and not text.endswith((".", ",", ";"))
        )
        bullet = bool(_BULLET.match(text) or _DASH_ITEM.match(text))
        if (big or strong) and not bullet and not first_alpha.islower():
            b.kind = "heading"
            continue
        if b.kind == "list_item":
            b.text = _BULLET.sub("", text, count=1)
            if _DASH_ITEM.match(b.text):
                b.text = b.text[1:].lstrip()


def heading_levels(blocks: list[_Block], body: float) -> None:
    heads = [b for b in blocks if b.kind == "heading"]
    sizes = sorted({round(b.size * 2) / 2 for b in heads if b.size >= 1.15 * body}, reverse=True)
    for b in heads:
        s = round(b.size * 2) / 2
        b.level = min(6, sizes.index(s) + 1 if s in sizes else len(sizes) + 1)
    demote_figure_titles(blocks)


_NUMBERED_TITLE = re.compile(r"^\d{1,2}[.)]\s+\S")


def _figure_like(content: list[_Block]) -> bool:
    """Début de contenu d'une figure ou d'un tableau plutôt que d'une section : des étiquettes courtes
    (axes, légendes, cellules) ou des chiffres, là où une section commence par un paragraphe."""

    def label(t: str) -> bool:
        alnum = sum(1 for c in t if c.isalnum())
        return len(t) <= 40 or sum(1 for c in t if c.isdigit()) >= 0.3 * max(1, alnum)

    head = [b.text for b in content if b.kind != "heading"][:5]
    if not head or not label(head[0]):
        return False
    return sum(1 for t in head if label(t)) * 2 > len(head)


def demote_figure_titles(blocks: list[_Block]) -> None:
    """Titres de figures numérotées (« 1. Évolution de la population… ») pris pour des titres de section :
    quand, à un même niveau, des titres numérotés côtoient des titres qui ne le sont pas, un titre numéroté
    suivi d'un contenu de figure (étiquettes courtes, chiffres) devient une légende. Il reste lu, mais
    n'ouvre plus de chapitre."""
    heads = [(i, b) for i, b in enumerate(blocks) if b.kind == "heading"]
    for level in {b.level for _, b in heads}:
        same = [(i, b) for i, b in heads if b.level == level]
        numbered = [(i, b) for i, b in same if _NUMBERED_TITLE.match(b.text)]
        if not numbered or len(numbered) == len(same):
            continue
        for i, b in numbered:
            content = []
            for nxt in blocks[i + 1 :]:
                if nxt.kind == "heading":
                    break
                content.append(nxt)
            if _figure_like(content):
                b.kind, b.level = "caption", 0


def build_notes(pages_notes: list[tuple[int, list[Line]]]) -> list[Note]:
    notes: list[Note] = []
    for page, lines in pages_notes:
        for ln in lines:
            text, _calls = render_line(ln)
            mark = note_marker(ln)
            if mark:
                body = text.strip()
                body = body[len(mark) :] if body.startswith(mark) else re.sub(r"^\S+\s*", "", body)
                body = re.sub(r"^[.)]?\s*", "", body)
                notes.append(Note(page, mark, [body]))
            elif notes:
                notes[-1].texts.append(text)
            else:
                notes.append(Note(page, "", [text]))
    return notes


def note_text(note: Note, stats: WordStats) -> str:
    text = ""
    for t in note.texts:
        text = join_lines(text, t, stats) if text else t
    return clean_text(text)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if c.isalnum())


MAX_CHAPTER_PAGES = 80


def _chapter_openers(bookmarks: list[Bookmark], chapter_level: int) -> set[int]:
    """Signets qui ouvrent un chapitre : ceux de `chapter_level`, plus, dans un chapitre de plus de
    MAX_CHAPTER_PAGES pages, ceux du niveau inférieur (récursivement). Un chapitre de 500 pages (rapport
    en deux grandes parties) ferait un fichier de 17 heures, impossible à parcourir à l'oreille."""
    openers = {n for n, bm in enumerate(bookmarks) if bm.level == chapter_level}
    last_page = max(bm.page for bm in bookmarks)
    changed = True
    while changed:
        changed = False
        ordered = sorted(openers)
        for k, n in enumerate(ordered):
            end_n = ordered[k + 1] if k + 1 < len(ordered) else len(bookmarks)
            end_page = bookmarks[end_n].page if end_n < len(bookmarks) else last_page + 1
            if end_page - bookmarks[n].page <= MAX_CHAPTER_PAGES:
                continue
            level = bookmarks[n].level
            children = [m for m in range(n + 1, end_n) if bookmarks[m].level == level + 1]
            if children and not set(children) <= openers:
                openers.update(children)
                changed = True
    return openers


def apply_bookmarks(
    blocks: list[_Block], bookmarks: list[Bookmark], chapter_level: int
) -> list[tuple[int, str]]:
    """Marque les titres désignés par les signets ; renvoie les points de coupure des chapitres
    (index du bloc, titre). Les signets de niveau `chapter_level` ouvrent un chapitre."""
    if not bookmarks:
        return []
    openers = _chapter_openers(bookmarks, chapter_level)
    splits: list[tuple[int, str]] = []
    used: set[int] = set()
    for n, bm in enumerate(bookmarks):
        key = _norm(bm.title)
        idx = None
        if key:
            for i, b in enumerate(blocks):
                if i in used or b.kind in ("table", "footnote") or abs(b.page - bm.page) > 1:
                    continue
                bk = _norm(b.text)
                if bk == key or (b.kind == "heading" and bk.startswith(key) and len(bk) < 2 * len(key) + 10):
                    idx = i
                    break
        if idx is not None:
            used.add(idx)
            blk = blocks[idx]
            blk.kind = "heading"
            blk.level = max(1, bm.level - chapter_level + 1)
        if n not in openers:
            continue
        if idx is None:
            for i, b in enumerate(blocks):
                if b.page > bm.page or (
                    b.page == bm.page and (bm.top is None or b.lines[0].top >= bm.top - 5)
                ):
                    idx = i
                    break
        if idx is not None:
            splits.append((idx, clean_text(bm.title)))
    splits.sort()
    dedup: list[tuple[int, str]] = []
    for idx, title in splits:
        if dedup and dedup[-1][0] == idx:
            continue
        dedup.append((idx, title))
    return dedup


def heading_splits(blocks: list[_Block]) -> list[tuple[int, str]]:
    """Coupures de chapitres d'après les titres : le niveau le plus haut dont au moins deux titres sont
    suivis de texte (un surtitre ou un titre de document isolé ne fait pas un chapitre)."""
    with_body: Counter[int] = Counter()
    for i, b in enumerate(blocks):
        if b.kind != "heading":
            continue
        for nxt in blocks[i + 1 :]:
            if nxt.kind == "heading" and nxt.level <= b.level:
                break
            if nxt.kind != "heading":
                with_body[b.level] += 1
                break
    chapter_level = min((lv for lv, n in with_body.items() if n >= 2), default=None)
    if chapter_level is None:
        return []
    return [(i, b.text) for i, b in enumerate(blocks) if b.kind == "heading" and b.level == chapter_level]


def to_block(b: _Block) -> Block:
    return Block(b.kind, b.text, b.level if b.kind == "heading" else 0, b.page + 1)


def make_chapters(
    blocks: list[_Block],
    splits: list[tuple[int, str]],
    preamble_title: str,
    notes: list[Note],
    footnotes_mode: str,
    stats: WordStats,
) -> list[Chapter]:
    # placement des notes
    anchors: dict[int, list[Note]] = defaultdict(list)
    for note in notes:
        target = None
        if note.marker:
            for i, b in enumerate(blocks):
                if (note.page, note.marker) in b.calls:
                    target = i
                    break
        if target is None:  # pas d'appel retrouvé : après le dernier bloc de la page (ou d'avant)
            for i, b in enumerate(blocks):
                if b.page <= note.page:
                    target = i
        if target is None:
            target = 0
        anchors[target].append(note)

    groups: list[tuple[str, list[int]]] = []
    bounds = [i for i, _ in splits]
    if not splits:
        groups.append(("", list(range(len(blocks)))))
    else:
        if bounds[0] > 0:
            pre = list(range(bounds[0]))
            if all(blocks[i].kind == "heading" for i in pre):
                splits = [(0, splits[0][1])] + splits[1:]
                bounds[0] = 0
            else:
                groups.append((preamble_title, pre))
        for k, (start, title) in enumerate(splits):
            end = bounds[k + 1] if k + 1 < len(bounds) else len(blocks)
            groups.append((title, list(range(start, end))))

    chapters = []
    for title, idxs in groups:
        out: list[Block] = []
        tail: list[Block] = []
        for i in idxs:
            out.append(to_block(blocks[i]))
            for note in anchors.get(i, []):
                nb = Block("footnote", note_text(note, stats), 0, note.page + 1)
                if not nb.text:
                    continue
                if footnotes_mode == "inline":
                    out.append(nb)
                elif footnotes_mode == "end_of_chapter":
                    tail.append(nb)
        chapters.append(Chapter(title, out + tail))
    if not chapters:
        chapters.append(Chapter("", []))
    return chapters
