"""Pictogrammes nommés (issue #12)."""

from voxpage.document import Block, Chapter, Document
from voxpage.normalize import NormalizeOptions, normalize
from voxpage.normalize.text import speak


def _said(blocks, lang="fr"):
    doc = Document("T", None, lang, [Chapter("", blocks)])
    return [s.text for s in normalize(doc, NormalizeOptions())[0].segments]


def test_pictogrammes_noms_exacts():
    assert speak("⚠ Ne pas ouvrir", "fr") == "attention Ne pas ouvrir"
    assert speak("Oui ✓", "fr") == "Oui coché"
    assert speak("Non ✗", "fr") == "Non croix"
    assert speak("Écrire ✉ au service", "fr") == "Écrire courrier au service"
    assert speak("Warning ⚠", "en") == "Warning warning"
    assert speak("☎", "en") == "telephone"


def test_pictogramme_seul_dit_et_fleuron_retire():
    assert _said([Block("paragraph", "☎")]) == ["téléphone"]
    assert _said([Block("paragraph", "❦")]) == []
    assert _said([Block("paragraph", "✦ ✦ ✦")]) == []
    assert _said([Block("paragraph", "* * *")]) == []


def test_coche_en_cellule_de_tableau():
    said = _said([Block("table", "Option; Inclus\nA; ✓\nB; ✗")])
    assert "Inclus : coché" in " ".join(said) and "Inclus : croix" in " ".join(said)


def test_puce_coche_reste_une_puce():
    assert _said([Block("list_item", "✓ Premier point")]) == ["Premier point"]
