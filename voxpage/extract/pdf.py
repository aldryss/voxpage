"""Extracteur PDF (texte natif) : pdfminer.six pour la mise en page, pypdfium2 pour le plan et les
métadonnées.

Étapes : lecture des caractères page par page → fragments de ligne → retrait des en-têtes, pieds et
numéros de page → notes de bas de page → tableaux et encadrés → ordre de lecture (colonnes) →
paragraphes (césures recollées) → titres, listes, légendes → chapitres (signets, sinon titres).

OCR (issue #7) : les pages sans texte exploitable (`ocr="auto"`) ou toutes les pages (`ocr="always"`) sont
lues par `voxpage.extract.ocr` si le moteur et ses modèles sont présents. Les lignes reconnues deviennent des
`PageData` comme les pages natives, et passent donc par la même suite (en-têtes et pieds répétés, colonnes,
paragraphes, césures). Sans moteur, un avertissement nomme les pages concernées.
"""

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError, PDFPasswordIncorrect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.psparser import PSException

from voxpage.document import Document
from voxpage.extract import ocr
from voxpage.extract.base import ExtractError, ExtractOptions
from voxpage.extract.ocr import MIN_SCORE_WARN, OcrPage, scale_sizes, to_page_data
from voxpage.extract.pdf_furniture import detect_furniture
from voxpage.extract.pdf_layout import (
    Aggregator,
    Line,
    PageData,
    TableItem,
    detect_regions,
    read_page,
    reading_order,
    split_footnotes,
)
from voxpage.extract.pdf_pages import parse_pages
from voxpage.extract.pdf_structure import (
    Bookmark,
    Builder,
    apply_bookmarks,
    body_size_of,
    build_notes,
    classify,
    heading_levels,
    heading_splits,
    make_chapters,
    render_line,
    reorder_continuations,
    word_stats,
)
from voxpage.extract.pdf_tabular import LooseItem, TocEntry, find_loose, find_toc, loose_pages
from voxpage.extract.pdf_text import clean_text
from voxpage.lang import detect_lang
from voxpage.progress import Cancelled, CancelToken, ProgressCb

OcrFn = Callable[[Path, int, str | None], "OcrPage"]
READ_SHARE = 0.15  # part de la progression pour la lecture du texte natif ; l'OCR prend le reste jusqu'à 0.9
OCR_SHARE = 0.75

_JUNK_TITLE = re.compile(
    r"^(?:untitled|sans titre|document\d*|microsoft (?:word|powerpoint) - .*"
    r"|.*\.(?:docx?|odt|rtf|pdf|indd|tex|dvi|qxd|ps)|.*\bcop(?:ie|y))$",
    re.IGNORECASE,
)


def _ocr_engine() -> OcrFn | None:
    """Le moteur OCR, ou None s'il n'est pas disponible (bibliothèque ou modèles absents)."""
    return ocr.recognize if ocr.available() else None


GARBLED_MIN_WORDS = 20  # en dessous, trop peu de texte pour juger d'une couche de texte incohérente
GARBLED_RATIO = 0.5


def _has_usable_text(page: PageData) -> bool:
    """La page porte-t-elle un texte exploitable ? Sinon, c'est une page scannée (ou illisible) à passer
    à l'OCR. Une page vraiment blanche (ni texte ni image) est considérée comme exploitable : il n'y a rien
    à reconnaître.

    Une page est inexploitable si l'un de ces critères est vrai :

    1. plus de 30 % des caractères n'ont pas d'équivalent Unicode (polices sans table de correspondance) ;
    2. moins de 20 caractères alphanumériques alors qu'une image couvre au moins 30 % de la page (couche de
       texte vide ou quasi vide sur une numérisation) ;
    3. couche de texte incohérente : au moins 20 mots dont plus de la moitié relèvent du charabia (lettres
       isolées, ponctuation seule, suites de consonnes, encodage cassé), typique d'un OCR d'origine raté.
    """
    total = page.n_chars + page.n_unknown
    if total and page.n_unknown / total > 0.3:
        return False
    area = page.width * page.height
    if page.n_alnum < 20 and area and page.image_area >= 0.3 * area:
        return False
    if page.n_words >= GARBLED_MIN_WORDS and page.n_junk > GARBLED_RATIO * page.n_words:
        return False
    return True


def _pages_label(indexes: list[int]) -> str:
    nums = [i + 1 for i in indexes]
    parts: list[str] = []
    start = prev = nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        parts.append(str(start) if start == prev else f"{start} à {prev}")
        if n is not None:
            start = prev = n
    word = "page" if len(nums) == 1 else "pages"
    return f"{word} {', '.join(parts)}"


def _sample_lang(pages: dict[int, PageData]) -> str | None:
    """Langue du document d'après ses pages à texte natif (None s'il n'y en a pas)."""
    text = " ".join(f.text for p in pages.values() if _has_usable_text(p) for f in p.frags)
    return detect_lang(text[:50_000]) if text.strip() else None


def _body_size(pages: list[PageData]) -> float | None:
    sizes: Counter[float] = Counter()
    for p in pages:
        for f in p.frags:
            sizes[round(f.size * 2) / 2] += len(f.text.strip())
    return body_size_of(sizes) if sizes else None


def _open_pdfium(path: Path) -> pdfium.PdfDocument:
    if not path.is_file():
        raise ExtractError(f"Fichier introuvable : « {path.name} ».")
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        msg = str(exc).lower()
        if "password" in msg:
            raise ExtractError(
                f"« {path.name} » est protégé par un mot de passe : Voxpage ne peut pas l'ouvrir. "
                "Retirez la protection puis réessayez."
            ) from None
        raise ExtractError(f"« {path.name} » n'est pas un PDF valide ou il est endommagé.") from None


def _read_toc(pdf: pdfium.PdfDocument) -> list[Bookmark]:
    out: list[Bookmark] = []
    try:
        for bm in pdf.get_toc():
            title = clean_text(bm.get_title() or "")
            dest = bm.get_dest()
            if dest is None:
                action = pdfium_c.FPDFBookmark_GetAction(bm.raw)
                if action:
                    raw = pdfium_c.FPDFAction_GetDest(pdf.raw, action)
                    if raw:
                        dest = pdfium.PdfDest(raw, pdf=pdf)
            if dest is None or not title:
                continue
            index = dest.get_index()
            if index is None:
                continue
            top = None
            try:
                mode, pos = dest.get_view()
                if mode == pdfium_c.PDFDEST_VIEW_XYZ and len(pos) >= 2:
                    top = pdf.get_page_size(index)[1] - pos[1]
                elif mode in (pdfium_c.PDFDEST_VIEW_FITH, pdfium_c.PDFDEST_VIEW_FITBH) and pos:
                    top = pdf.get_page_size(index)[1] - pos[0]
            except Exception:  # noqa: BLE001 — position facultative
                top = None
            out.append(Bookmark(title, bm.level, index, top))
    except Exception:  # noqa: BLE001 — un plan endommagé ne doit pas empêcher la lecture du texte
        return []
    return out


def _metadata(pdf: pdfium.PdfDocument) -> tuple[str | None, str | None]:
    try:
        meta = pdf.get_metadata_dict()
    except Exception:  # noqa: BLE001
        return None, None
    title = clean_text(meta.get("Title") or "")
    author = clean_text(meta.get("Author") or "")
    if not title or _JUNK_TITLE.match(title) or not any(c.isalpha() for c in title):
        title = ""
    return title or None, author or None


class PdfExtractor:
    extensions = (".pdf",)

    def extract(
        self,
        path: Path,
        options: ExtractOptions,
        progress: ProgressCb | None = None,
        cancel: CancelToken | None = None,
    ) -> Document:
        path = Path(path)
        warnings: list[str] = []
        pdf = _open_pdfium(path)
        try:
            count = len(pdf)
            if count == 0:
                raise ExtractError(f"« {path.name} » ne contient aucune page.")
            try:
                selected = parse_pages(options.pages, count)
            except ValueError as exc:
                raise ExtractError(str(exc)) from None
            meta_title, author = _metadata(pdf)
            toc = _read_toc(pdf)
        finally:
            pdf.close()

        # quelques pages voisines aident à repérer en-têtes et pieds quand la sélection est courte
        sample = set(selected)
        if len(sample) < 6:
            lo, hi = selected[0], selected[-1]
            for i in range(max(0, lo - 3), min(count, hi + 4)):
                if len(sample) >= 6:
                    break
                sample.add(i)
        pages = self._read_pages(path, sorted(sample), set(selected), progress, cancel, warnings)
        chosen = [pages[i] for i in selected if i in pages]

        # pages sans texte exploitable → OCR
        engine = _ocr_engine()
        if options.ocr == "always":
            ocr_pages = [p.index for p in chosen]
        elif options.ocr == "auto":
            ocr_pages = [p.index for p in chosen if not _has_usable_text(p)]
        else:
            ocr_pages = []
        ocr_done: set[int] = set()
        if ocr_pages and engine is None:
            if options.ocr == "auto":
                warnings.append(
                    f"{_pages_label(ocr_pages).capitalize()} : aucun texte exploitable (page scannée ?). "
                    "La reconnaissance de caractères (OCR) n'est pas disponible : contenu ignoré."
                )
            else:
                warnings.append(
                    "La reconnaissance de caractères (OCR) n'est pas disponible : texte natif utilisé."
                )
        elif ocr_pages and engine is not None:
            lang = _sample_lang(pages)
            ocr_done, weak, empty, failed = self._run_ocr(
                engine, path, ocr_pages, lang, pages, progress, cancel
            )
            chosen = [pages[i] for i in selected if i in pages]
            if ocr_done:
                warnings.append(
                    f"{_pages_label(sorted(ocr_done)).capitalize()} : texte reconnu par OCR, "
                    "des erreurs de lecture sont possibles."
                )
            if weak:
                warnings.append(
                    f"{_pages_label(weak).capitalize()} : lecture peu fiable (numérisation de mauvaise "
                    "qualité), vérifiez ce passage."
                )
            if empty:
                warnings.append(f"{_pages_label(empty).capitalize()} : aucun texte reconnu par l'OCR.")
            if failed:
                warnings.append(
                    f"{_pages_label(failed).capitalize()} : la reconnaissance de caractères a échoué, "
                    "contenu ignoré."
                )
        elif options.ocr == "never":
            empty = [p.index for p in chosen if not _has_usable_text(p)]
            if empty:
                warnings.append(
                    f"{_pages_label(empty).capitalize()} : aucun texte exploitable (page scannée ?)."
                )

        for p in chosen:
            if p.n_rotated >= 20:
                warnings.append(f"Page {p.index + 1} : texte vertical ou incliné ignoré.")
            if p.n_unknown >= 5 and p.index not in ocr_done and _has_usable_text(p):
                warnings.append(f"Page {p.index + 1} : {p.n_unknown} caractères illisibles ignorés.")

        if progress:
            progress("Analyse de la structure", 0.9)
        doc = self._structure(path, pages, chosen, toc, options, meta_title, author, warnings)
        if progress:
            progress("Analyse de la structure", 1.0)
        return doc

    # -----------------------------------------------------------------------------------------------------

    def _run_ocr(
        self,
        engine: OcrFn,
        path: Path,
        indexes: list[int],
        lang: str | None,
        pages: dict[int, PageData],
        progress: ProgressCb | None,
        cancel: CancelToken | None,
    ) -> tuple[set[int], list[int], list[int], list[int]]:
        """Lit les pages `indexes` par OCR et remplace leur `PageData` (dans `pages`) par celle du texte
        reconnu. Renvoie (pages lues, pages peu fiables, pages sans texte reconnu, pages en échec). Une page
        dont l'OCR échoue garde son contenu natif ; l'annulation est vérifiée avant chaque page."""
        done: set[int] = set()
        weak: list[int] = []
        empty: list[int] = []
        failed: list[int] = []
        native = [p for i, p in pages.items() if i not in indexes and _has_usable_text(p)]
        native_body = _body_size(native)
        for k, idx in enumerate(indexes):
            if cancel:
                cancel.raise_if_cancelled()
            if progress:
                share = READ_SHARE + OCR_SHARE * k / len(indexes)
                progress(f"Reconnaissance de caractères, page {idx + 1}", share)
            try:
                result = engine(path, idx, lang)
            except Cancelled:
                raise
            except Exception:  # noqa: BLE001 — une page illisible ne doit pas arrêter la conversion
                failed.append(idx)
                continue
            data = to_page_data(result, idx)
            if not data.n_alnum:
                if not _has_usable_text(pages[idx]):
                    empty.append(idx)
                continue  # rien de reconnu : le texte natif éventuel est conservé
            if native_body:
                scale_sizes(data, native_body)
            pages[idx] = data
            done.add(idx)
            if result.mean_score < MIN_SCORE_WARN:
                weak.append(idx)
        return done, weak, empty, failed

    def _read_pages(
        self,
        path: Path,
        wanted: list[int],
        selected: set[int],
        progress: ProgressCb | None,
        cancel: CancelToken | None,
        warnings: list[str],
    ) -> dict[int, PageData]:
        out: dict[int, PageData] = {}
        wanted_set = set(wanted)
        try:
            fp = open(path, "rb")  # noqa: SIM115
        except OSError as exc:
            raise ExtractError(f"Impossible de lire « {path.name} » : {exc.strerror}.") from None
        with fp:
            try:
                doc = PDFDocument(PDFParser(fp), password="")
            except PDFPasswordIncorrect:
                raise ExtractError(
                    f"« {path.name} » est protégé par un mot de passe : Voxpage ne peut pas l'ouvrir. "
                    "Retirez la protection puis réessayez."
                ) from None
            except PDFEncryptionError:
                raise ExtractError(f"« {path.name} » utilise un chiffrement non pris en charge.") from None
            except (PSException, ValueError, KeyError, TypeError) as exc:
                raise ExtractError(
                    f"« {path.name} » n'est pas un PDF valide ou il est endommagé ({exc})."
                ) from None
            rsrc = PDFResourceManager(caching=True)
            device = Aggregator(rsrc, laparams=None)
            interp = PDFPageInterpreter(rsrc, device)
            done = 0
            last = max(wanted)
            try:
                for index, page in enumerate(PDFPage.create_pages(doc)):
                    if index > last:
                        break
                    if index not in wanted_set:
                        continue
                    if cancel:
                        cancel.raise_if_cancelled()
                    if progress:
                        progress(f"Lecture de la page {index + 1}", READ_SHARE * done / len(wanted))
                    try:
                        interp.process_page(page)
                        out[index] = read_page(device.get_result(), index)
                    except Exception:  # noqa: BLE001 — une page endommagée ne bloque pas les autres
                        if index in selected:
                            warnings.append(f"Page {index + 1} : contenu endommagé, page ignorée.")
                    done += 1
            except PSException as exc:
                if not out:
                    raise ExtractError(
                        f"« {path.name} » n'est pas un PDF valide ou il est endommagé ({exc})."
                    ) from None
                warnings.append("La fin du document est endommagée : certaines pages n'ont pas pu être lues.")
        return out

    def _structure(
        self,
        path: Path,
        pages: dict[int, PageData],
        chosen: list[PageData],
        toc: list[Bookmark],
        options: ExtractOptions,
        meta_title: str | None,
        author: str | None,
        warnings: list[str],
    ) -> Document:
        sizes: Counter[float] = Counter()
        for p in chosen:
            for f in p.frags:
                sizes[round(f.size * 2) / 2] += len(f.text.strip())
        body = body_size_of(sizes)

        removed = detect_furniture(list(pages.values()), body)
        stream: list = []
        notes_by_page: list[tuple[int, list[Line]]] = []
        prev_notes = False
        for p in chosen:
            if not _has_usable_text(p):
                prev_notes = False
                continue
            frags = [f for f in p.frags if id(f) not in removed]
            frags = split_footnotes(p, frags, body, prev_notes)
            prev_notes = bool(p.footnotes)
            if p.footnotes:
                notes_by_page.append((p.index, p.footnotes))
            regions = detect_regions(p, frags, body)
            stream.extend(reading_order(p, frags, regions, body))

        stream = reorder_continuations(stream, body)
        stream = find_loose(find_toc(stream, render_line), render_line)
        rendered: list[str] = []
        for it in stream:
            if isinstance(it, Line):
                rendered.append(render_line(it)[0])
            elif isinstance(it, TocEntry):
                rendered.append(it.text)
            elif isinstance(it, LooseItem):
                rendered.extend(render_line(ln)[0] for ln in it.lines)
            elif isinstance(it, TableItem):
                for row in it.rows:
                    for cell in row:
                        rendered.extend(render_line(ln)[0] for ln in cell)
        for _page, lines in notes_by_page:
            rendered.extend(render_line(ln)[0] for ln in lines)
        stats = word_stats(rendered)

        builder = Builder(body, stats)
        builder.learn_leading([it for it in stream if isinstance(it, Line)])
        for it in stream:
            if isinstance(it, Line):
                text, calls = render_line(it)
                builder.add(it, text, calls)
            elif isinstance(it, TocEntry):
                builder.entry(it.line, it.text)
            elif isinstance(it, LooseItem):
                builder.loose(it)
            elif isinstance(it, TableItem):
                builder.table(it)
        blocks = builder.finish()
        classify(blocks, body)
        heading_levels(blocks, body)

        chosen_idx = {p.index for p in chosen}
        if toc:
            levels = Counter(bm.level for bm in toc)
            chapter_level = min((lv for lv, n in levels.items() if n >= 2), default=min(levels))
            splits = apply_bookmarks(blocks, [bm for bm in toc if bm.page in chosen_idx], chapter_level)
        else:
            chapter_level = 0
            splits = heading_splits(blocks)

        title = meta_title
        if not title:
            heads = [b for b in blocks if b.kind == "heading" and b.page <= chosen[0].index + 2]
            if heads:
                top = min(b.level for b in heads)
                title = next(b.text for b in heads if b.level == top)
        if not title:
            title = path.stem

        preamble = title
        if toc and chosen:
            covering = [bm for bm in toc if bm.page < chosen[0].index and bm.level == chapter_level]
            if covering:
                preamble = covering[-1].title

        notes = build_notes(notes_by_page)
        chapters = make_chapters(blocks, splits, preamble, notes, options.footnotes, stats)

        if not any(ch.blocks for ch in chapters):
            if any(not _has_usable_text(p) for p in chosen):
                raise ExtractError(
                    f"« {path.name} » ne contient pas de texte lisible : il s'agit probablement d'un "
                    "document scanné. La reconnaissance de caractères (OCR) est nécessaire pour le lire."
                )
            raise ExtractError(f"« {path.name} » ne contient aucun texte.")

        loose = loose_pages([b for ch in chapters for b in ch.blocks])
        if loose:
            label = _pages_label([p - 1 for p in loose]).capitalize()
            warnings.append(f"{label} : tableaux ou graphiques lus sans structure.")

        sample = " ".join(
            b.text for ch in chapters for b in ch.blocks if b.kind in ("paragraph", "list_item")
        )
        lang = detect_lang(sample[:100_000] or " ".join(b.text for ch in chapters for b in ch.blocks))
        return Document(title, author, lang, chapters, warnings)
