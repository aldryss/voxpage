"""Zones tabulaires sans structure (issue #12)."""

from pathlib import Path

import pytest

from voxpage.extract import ExtractOptions, extractor_for
from voxpage.extract.pdf_layout import Line, Span
from voxpage.extract.pdf_structure import render_line
from voxpage.extract.pdf_tabular import LooseItem, find_loose

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

W, H = A4


def _line(text, x0=50.0, x1=None, top=0.0, page=0, region=0):
    x1 = x1 if x1 is not None else x0 + 6 * len(text)
    return Line([Span(text)], x0, x1, top, top + 10, top + 8, 10.0, False, False, page, 50.0, 500.0, region)


def _stream(texts, **kw):
    return [_line(t, top=12.0 * i, **kw) for i, t in enumerate(texts)]


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
