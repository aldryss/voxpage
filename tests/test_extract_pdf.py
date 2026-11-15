"""Extracteur PDF : comparaison stricte avec le texte attendu du corpus (tests/corpus/build.py)."""

import json
from pathlib import Path

import pytest

from voxpage.extract import ExtractError, ExtractOptions, extractor_for, supported_extensions
from voxpage.extract.pdf_furniture import page_number_value
from voxpage.extract.pdf_pages import parse_pages
from voxpage.extract.pdf_text import WordStats, clean_text, join_lines, keep_hyphen
from voxpage.progress import Cancelled, CancelToken

CORPUS = Path(__file__).parent / "corpus"


def as_dict(doc) -> dict:
    return {
        "title": doc.title,
        "author": doc.author,
        "lang": doc.lang,
        "chapters": [
            {"title": ch.title, "blocks": [[b.kind, b.level, b.text] for b in ch.blocks]}
            for ch in doc.chapters
        ],
        "warnings": doc.warnings,
    }


def cases():
    for exp in sorted(CORPUS.glob("*.expected.json")):
        name = exp.name.removesuffix(".expected.json")
        for k, case in enumerate(json.loads(exp.read_text(encoding="utf-8"))):
            yield pytest.param(name, case, id=f"{name}-{k}")


def extract(name: str, **options):
    path = CORPUS / f"{name}.pdf"
    return extractor_for(path).extract(path, ExtractOptions(**options))


@pytest.mark.parametrize(("name", "case"), list(cases()))
def test_corpus(name, case):
    if "error" in case:
        with pytest.raises(ExtractError) as err:
            extract(name, **case["options"])
        assert case["error"] in str(err.value)
        return
    got = as_dict(extract(name, **case["options"]))
    want = case["document"]
    # comparaison bloc par bloc d'abord, pour un message d'échec lisible
    for ch_got, ch_want in zip(got["chapters"], want["chapters"], strict=False):
        assert ch_got["title"] == ch_want["title"]
        for b_got, b_want in zip(ch_got["blocks"], ch_want["blocks"], strict=False):
            assert b_got == b_want
    assert got == want


def test_pdf_enregistre_par_defaut():
    assert ".pdf" in supported_extensions()
    assert extractor_for(Path("LIVRE.PDF")).extensions == (".pdf",)


def test_pages_de_blocs():
    doc = extract("entetes")
    pages = [b.page for ch in doc.chapters for b in ch.blocks]
    assert pages == sorted(pages) and pages[0] == 1 and pages[-1] >= 3


def test_selection_de_pages():
    doc = extract("entetes", pages="3-4")
    blocks = [b for ch in doc.chapters for b in ch.blocks]
    assert blocks and all(3 <= b.page <= 4 for b in blocks)
    text = " ".join(b.text for b in blocks)
    assert "Chapitre premier" not in text
    assert not any(b.text.isdigit() and b.text != "1789" for b in blocks)


def test_selection_de_pages_invalide():
    with pytest.raises(ExtractError, match="Sélection de pages invalide"):
        extract("simple", pages="2-1")
    with pytest.raises(ExtractError, match="Aucune page sélectionnée"):
        extract("simple", pages="5-9")


def test_progression_et_annulation():
    steps = []
    extract_path = CORPUS / "entetes.pdf"
    extractor_for(extract_path).extract(extract_path, ExtractOptions(), progress=lambda s, f: steps.append(f))
    assert steps[0] == 0.0 and steps[-1] == 1.0 and steps == sorted(steps)

    token = CancelToken()

    def cancel_after_first(step, frac):
        if frac > 0:
            token.cancel()

    with pytest.raises(Cancelled):
        extractor_for(extract_path).extract(extract_path, ExtractOptions(), cancel_after_first, token)


def test_fichier_introuvable(tmp_path):
    with pytest.raises(ExtractError, match="introuvable"):
        extractor_for(Path("x.pdf")).extract(tmp_path / "absent.pdf", ExtractOptions())


def test_ocr_never_signale_sans_avertir_d_ocr():
    doc = extract("scan", ocr="never")
    assert doc.warnings == ["Page 2 : aucun texte exploitable (page scannée ?)."]


def test_ocr_branche(monkeypatch):
    import voxpage.extract.pdf as pdf

    calls = []

    def fake_ocr(path, index, lang):
        calls.append(index)
        return "Texte reconnu\nsur deux lignes.\n\nSecond paragraphe."

    monkeypatch.setattr(pdf, "_ocr_engine", lambda: fake_ocr)
    doc = extract("scan")
    assert calls == [1]
    assert [(b.text, b.page) for b in doc.chapters[0].blocks] == [
        ("Cette première page contient du texte natif.", 1),
        ("Texte reconnu sur deux lignes.", 2),
        ("Second paragraphe.", 2),
    ]
    assert doc.warnings == ["Page 2 : texte reconnu par OCR, à vérifier."]


# ---------------------------------------------------------------------------------------------------------
# Règles unitaires


@pytest.mark.parametrize(
    ("left", "right", "keep"),
    [
        ("transcrip", "tion", False),
        ("rapide", "ment", False),
        ("peut", "être", True),
        ("Jean", "Pierre", True),
        ("c'est-à", "dire", True),
        ("arc-en", "ciel", True),
        ("dit", "il", True),
        ("anti", "inflammatoire", True),
        ("après", "midi", True),
        ("Moyen", "Âge", True),
        ("bou", "les", False),
        ("va", "leur", False),
        ("well", "known", True),
        ("trans", "formation", False),
    ],
)
def test_regle_cesure(left, right, keep):
    assert keep_hyphen(left, right) is keep


def test_cesure_tranchee_par_le_document():
    stats = WordStats()
    stats.add_line("un week-end au calme, sans contredire personne")
    assert join_lines("le week-", "end dernier", stats) == "le week-end dernier"
    assert join_lines("ne contre-", "dire rien", stats) == "ne contredire rien"
    assert join_lines("ne contre-", "dire rien", WordStats()) == "ne contre-dire rien"


@pytest.mark.parametrize(
    ("prev", "nxt", "joined"),
    [
        ("biblio\u00ad", "thèque", "bibliothèque"),
        ("de 1914-", "1918", "de 1914-1918"),
        ("neuf heures —", "et ferme", "neuf heures — et ferme"),
        ("voir https://exemple.fr/", "page", "voir https://exemple.fr/page"),
        ("fin de ligne", "suite", "fin de ligne suite"),
        ("un tiret -", "isolé", "un tiret - isolé"),
    ],
)
def test_recollage_de_lignes(prev, nxt, joined):
    assert join_lines(prev, nxt) == joined


def test_nettoyage_des_caracteres():
    assert (
        clean_text("e\ufb00et, e\ufb03cace, sou\ufb04e, \ufb01n, \ufb02eur")
        == "effet, efficace, souffle, fin, fleur"
    )
    assert clean_text("e\u0301te\u0301") == "été"
    assert clean_text("a\u00a0:\u202f!\u2009b") == "a : ! b"
    assert clean_text("anti\u00adconstitution\u200bnel\u0007") == "anticonstitutionnel"
    assert clean_text("\uf0b7 puce") == "• puce"
    assert clean_text("  trop   d'espaces  ") == "trop d'espaces"


@pytest.mark.parametrize(
    ("spec", "pages"),
    [
        (None, [0, 1, 2, 3, 4]),
        ("1-2,5", [0, 1, 4]),
        ("4-", [3, 4]),
        ("-2", [0, 1]),
        ("3, 3 ; 1", [0, 2]),
        ("2-99", [1, 2, 3, 4]),
    ],
)
def test_parse_pages(spec, pages):
    assert parse_pages(spec, 5) == pages


@pytest.mark.parametrize("spec", ["a", "0", "3-1", "1--2"])
def test_parse_pages_invalide(spec):
    with pytest.raises(ValueError):
        parse_pages(spec, 5)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("12", ("arabic", 12)),
        ("- 12 -", ("arabic", 12)),
        ("Page 3", ("arabic", 3)),
        ("3 / 40", ("arabic", 3)),
        ("xiv", ("roman", 14)),
        ("12 heures", None),
        ("Chapitre 2", None),
    ],
)
def test_numero_de_page(text, value):
    assert page_number_value(text) == value
