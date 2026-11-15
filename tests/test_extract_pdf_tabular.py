"""Sommaires et zones tabulaires sans structure (issue #12)."""

from pathlib import Path

import pytest

from voxpage.extract import ExtractOptions, extractor_for
from voxpage.extract.pdf_layout import Line, Span
from voxpage.extract.pdf_structure import render_line
from voxpage.extract.pdf_tabular import LooseItem, TocEntry, find_loose, find_toc

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

W, H = A4


def _line(text, x0=50.0, x1=None, top=0.0, page=0, region=0):
    x1 = x1 if x1 is not None else x0 + 6 * len(text)
    return Line([Span(text)], x0, x1, top, top + 10, top + 8, 10.0, False, False, page, 50.0, 500.0, region)


def _stream(texts, **kw):
    return [_line(t, top=12.0 * i, **kw) for i, t in enumerate(texts)]


def _texts(stream):
    return [x.text if isinstance(x, TocEntry) else render_line(x)[0] for x in stream]


TOC_POINTS = [
    "Introduction ........................ 5",
    "Chapitre 1. Le contexte ............... 9",
    "Chapitre 2. Les résultats ............ 27",
    "Conclusion ........................... 41",
]


def test_sommaire_a_points_de_conduite():
    out = find_toc(_stream(TOC_POINTS), render_line)
    assert [type(x) for x in out] == [TocEntry] * 4
    assert _texts(out) == [
        "Introduction", "Chapitre 1. Le contexte", "Chapitre 2. Les résultats", "Conclusion",
    ]


def test_sommaire_sans_points_numeros_alignes():
    texts = ["Préface 7", "La naissance 11", "L'enfance 25", "La guerre 61", "La paix 102"]
    stream = [_line(t, x1=480.0, top=12.0 * i) for i, t in enumerate(texts)]
    out = find_toc(stream, render_line)
    assert _texts(out) == ["Préface", "La naissance", "L'enfance", "La guerre", "La paix"]


def test_trois_lignes_ne_font_pas_un_sommaire():
    out = find_toc(_stream(TOC_POINTS[:3]), render_line)
    assert all(not isinstance(x, TocEntry) for x in out)


def test_numerotation_n_est_pas_un_sommaire():
    texts = ["Étape 1", "Étape 2", "Étape 3", "Étape 4", "Étape 5"]
    out = find_toc([_line(t, x1=480.0, top=12.0 * i) for i, t in enumerate(texts)], render_line)
    assert all(not isinstance(x, TocEntry) for x in out)


def test_nombres_non_croissants_pas_un_sommaire():
    texts = ["Le prix 40", "La taille 12", "Le poids 70", "L'age 3"]
    out = find_toc([_line(t, x1=480.0, top=12.0 * i) for i, t in enumerate(texts)], render_line)
    assert all(not isinstance(x, TocEntry) for x in out)


def test_prose_avec_nombre_final_intacte():
    texts = ["Il a vu 3", "Elle est née en 1990", "Nous étions 12", "La route fait 40", "Ils sont 250"]
    out = find_toc(_stream(texts), render_line)
    assert _texts(out) == texts


NUMS = ["950", "900", "850", "Naissances", "800", "750", "700"]


def test_zone_numerique_alignee_regroupee():
    stream = [_line("Titre du graphique, assez long pour être du texte", top=0)] + [
        _line(t, x0=100.0, x1=100.0 + 6 * len(t), top=20.0 + 12 * i) for i, t in enumerate(NUMS)
    ]
    out = find_loose(stream, render_line)
    assert isinstance(out[0], Line) and isinstance(out[1], LooseItem) and len(out) == 2
    assert [render_line(ln)[0] for ln in out[1].lines] == NUMS  # rien n'est perdu


def test_prose_courte_non_regroupee():
    texts = ["Oui.", "Non.", "Peut-être.", "Demain.", "Jamais.", "Toujours.", "Souvent."]
    assert all(not isinstance(x, LooseItem) for x in find_loose(_stream(texts), render_line))


def test_quelques_nombres_non_regroupes():
    texts = ["1", "2", "3", "4", "5"]
    assert all(not isinstance(x, LooseItem) for x in find_loose(_stream(texts), render_line))


def test_nombres_non_alignes_non_regroupes():
    values = ["10", "20", "30", "40", "50", "60"]
    stream = [_line(t, x0=20.0 + 37 * i, top=12.0 * i) for i, t in enumerate(values)]
    assert all(not isinstance(x, LooseItem) for x in find_loose(stream, render_line))


# ------------------------------------------------------------------ de bout en bout, sur de petits PDF


def _pdf(path: Path, draw) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    draw(c)
    c.showPage()
    c.save()
    return path


def _doc(path: Path):
    return extractor_for(path).extract(path, ExtractOptions())


def test_pdf_sommaire(tmp_path):
    def draw(c):
        c.setFont("Helvetica", 11)
        y = 700
        c.drawString(60, y + 40, "Voici d'abord un texte d'introduction qui précède le sommaire du livre.")
        entries = [("Avant-propos", 5), ("Le début du voyage", 9), ("Les montagnes", 27), ("Le retour", 41)]
        for t, n in entries:
            c.drawString(60, y, t)
            start = 60 + c.stringWidth(t, "Helvetica", 11) + 4
            room = 498 - c.stringWidth(str(n), "Helvetica", 11) - start
            c.drawString(start, y, "." * int(room / c.stringWidth(".", "Helvetica", 11)))
            c.drawRightString(500, y, str(n))
            y -= 16
    doc = _doc(_pdf(tmp_path / "s.pdf", draw))
    text = " ".join(b.text for ch in doc.chapters for b in ch.blocks)
    for t in ("Avant-propos", "Le début du voyage", "Les montagnes", "Le retour"):
        assert t in text
    assert "...." not in text and "27" not in text and "41" not in text


def test_pdf_zone_numerique_signalee(tmp_path):
    def draw(c):
        c.setFont("Helvetica", 11)
        c.drawString(60, 760, "L'évolution des naissances est présentée dans le graphique, année par année.")
        for i, v in enumerate(["950", "900", "850", "800", "750", "700", "650"]):
            c.drawRightString(90, 700 - 14 * i, v)
        c.drawString(60, 560, "Le texte reprend ici, après le graphique, avec une phrase normale.")
    doc = _doc(_pdf(tmp_path / "g.pdf", draw))
    loose = [b for ch in doc.chapters for b in ch.blocks if b.kind == "table" and b.loose]
    assert len(loose) == 1 and loose[0].text.split("\n") == ["950", "900", "850", "800", "750", "700", "650"]
    assert loose[0].page == 1
    assert any("Page 1 : tableaux ou graphiques lus sans structure" in w for w in doc.warnings)
    text = " ".join(b.text for ch in doc.chapters for b in ch.blocks)
    assert "naissances" in text and "Le texte reprend" in text


def test_pdf_prose_sans_avertissement(tmp_path):
    def draw(c):
        c.setFont("Helvetica", 11)
        for i in range(8):
            c.drawString(60, 760 - 14 * i, f"Ligne {i} de prose ordinaire, qui continue jusqu'au bout.")
    doc = _doc(_pdf(tmp_path / "p.pdf", draw))
    assert not any("sans structure" in w for w in doc.warnings)
