"""Tableaux annoncés, pictogrammes nommés (issue #12)."""


from voxpage.document import Block, Chapter, Document
from voxpage.normalize import NormalizeOptions, normalize


def _said(blocks, lang="fr"):
    doc = Document("T", None, lang, [Chapter("", blocks)])
    return [s.text for s in normalize(doc, NormalizeOptions())[0].segments]


def test_tableau_avec_en_tete():
    said = _said([Block("table", "Année; Naissances; Décès\n2019; 753; 613\n2020; 740; 669")])
    assert said == [
        "Tableau.",
        "Année : 2019, Naissances : 753, Décès : 613",
        "Année : 2020, Naissances : 740, Décès : 669",
        "Fin du tableau.",
    ]


def test_tableau_en_tete_avec_coin_vide():
    said = _said([Block("table", "\tPrix\tStock\nPommes\t2\t10")])
    assert said[0] == "Tableau." and said[-1] == "Fin du tableau."
    assert said[1] == "Pommes, Prix : 2, Stock : 10"


def test_tableau_sans_en_tete_identifiable():
    said = _said([Block("table", "Paris; 2 100 000\nLyon; 520 000")])
    assert said == ["Tableau.", "Paris, 2100000", "Lyon, 520000", "Fin du tableau."]


def test_tableau_largeurs_inegales_pas_d_en_tete():
    said = _said([Block("table", "Ville; Habitants\nParis; 2 100 000; 2024")])
    assert not any(" : " in s for s in said)
    assert said[0] == "Tableau." and said[-1] == "Fin du tableau."


def test_aucun_texte_perdu_dans_un_tableau():
    said = _said([Block("table", "Année; Valeur\n2020; 5\n2021; 6")])
    assert " ".join(said) == "Tableau. Année : 2020, Valeur : 5 Année : 2021, Valeur : 6 Fin du tableau."


def test_tableau_anglais():
    said = _said([Block("table", "City; People\nParis; 2")], "en")
    assert said[0] == "Table." and said[-1] == "End of table."
    assert said[1] == "City : Paris, People : 2"


def test_tableau_vide_non_annonce():
    assert _said([Block("table", "; \n\t")]) == []


def test_zone_sans_structure():
    said = _said([Block("table", "950\n900\n850\nNaissances\n800", loose=True)])
    assert said[0] == "Tableau ou graphique, lu tel quel."
    assert said[-1] == "Fin du tableau ou graphique."
    assert said[1:-1] == ["950", "900", "850", "Naissances", "800"]


def test_zone_sans_structure_anglais():
    said = _said([Block("table", "1\n2\n3", loose=True)], "en")
    assert said[0] == "Table or chart, read as is." and said[-1] == "End of table or chart."


def test_paragraphe_voisin_pas_annonce():
    blocks = [Block("paragraph", "Un texte."), Block("table", "a; b\nc; d"), Block("paragraph", "Suite.")]
    said = _said(blocks)
    assert said[0] == "Un texte." and said[-1] == "Suite."
    assert said.count("Tableau.") == 1
