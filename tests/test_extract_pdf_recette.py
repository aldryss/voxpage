"""Extracteur PDF : défauts relevés lors de la recette de bout en bout (issue #11) sur des documents réels,
reproduits sur de petits PDF générés."""

from pathlib import Path

import pytest

from voxpage.extract import ExtractOptions, extractor_for

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

W, H = A4


def _pdf(path: Path, draw) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    draw(c)
    c.showPage()
    c.save()
    return path


def _lines(c, x, y, lines, size=10, font="Helvetica", leading=12):
    for i, t in enumerate(lines):
        c.setFont(font, size)
        c.drawString(x, y - i * leading, t)


def _texts(path: Path) -> list[str]:
    doc = extractor_for(path).extract(path, ExtractOptions())
    return [b.text for ch in doc.chapters for b in ch.blocks]


def _doc(path: Path):
    return extractor_for(path).extract(path, ExtractOptions())


def test_lettrine_ordre_des_lignes(tmp_path):
    """Lettrine sur trois lignes (Contes de la bécasse, Bibebook) : sa ligne de base est celle de la
    troisième ligne ; les lignes ne doivent pas être lues dans le désordre."""

    def draw(c):
        c.setFont("Helvetica", 40)
        c.drawString(60, 700 - 24, "L")  # ligne de base au niveau de la 3e ligne de texte
        _lines(
            c,
            92,
            700,
            [
                "e vieux baron des Ravots avait été pendant quarante ans le roi",
                "des chasseurs de sa province. Mais, depuis cinq à six années, une",
                "paralysie des jambes le clouait à son fauteuil, et il ne pouvait",
            ],
        )
        _lines(c, 60, 700 - 36, ["plus que tirer des pigeons de la fenêtre de son salon."])

    text = " ".join(_texts(_pdf(tmp_path / "l.pdf", draw)))
    assert text.startswith("Le vieux baron des Ravots avait été pendant quarante ans le roi des chasseurs")
    assert "une paralysie des jambes" in text and "ne pouvait plus que tirer" in text


def test_element_de_liste_qui_revient_a_la_marge(tmp_path):
    """Notice des impôts 2041-E : « 1. Votre foyer … la Nouvelle- / Calédonie et les TAAF … » coupé en deux
    titres (deux chapitres) ; et « (SU- / 089) ; » pris pour un nouvel élément numéroté."""

    long1 = "1. Votre foyer est installé en dehors du territoire national (tous les États, la Nouvelle-"
    long2 = "Calédonie et les TAAF) et vous percevez l'un des revenus suivants, quelle que soit leur nature :"

    def draw(c):
        _lines(c, 50, 760, [long1, long2], font="Helvetica-Bold", size=9, leading=11)
        _lines(
            c,
            50,
            700,
            [
                "1. un discours administratif qui met l'accent sur la demande de la part de la tutelle (SU-",
                "089) ;",
                "2. un discours politique voire idéologique qui souligne l'intérêt d'utiliser HAL (UCA-",
                "036) ;",
            ],
            size=9,
            leading=11,
        )

    doc = _doc(_pdf(tmp_path / "liste.pdf", draw))
    texts = [b.text for ch in doc.chapters for b in ch.blocks]
    assert any("la Nouvelle-Calédonie et les TAAF" in t for t in texts)
    assert any(t.endswith("(SU-089) ;") for t in texts)
    assert any(t.endswith("(UCA-036) ;") for t in texts)
    assert not any(t.startswith(("089", "036", "Calédonie")) for t in texts)


def test_microtexte_dans_une_icone_ignore(tmp_path):
    """Notice Riviera-et-Bar : le libellé « STOP » d'une icône, en corps 2,7, s'intercalait lettre à lettre
    dans la ligne voisine (« l'eSaTOPu »)."""

    def draw(c):
        c.setFont("Helvetica", 10)
        c.drawString(60, 700, "Le mouvement permet à l'eau de circuler librement autour des feuilles.")
        c.setFont("Helvetica", 2.7)
        c.drawString(165, 701, "STOP")
        c.setFont("Helvetica", 10)
        c.drawString(60, 686, "Une infusion maximale est ainsi obtenue.")

    text = " ".join(_texts(_pdf(tmp_path / "icone.pdf", draw)))
    assert "STOP" not in text and "à l'eau de circuler" in text


def test_titres_de_figures_numerotes_ne_sont_pas_des_chapitres(tmp_path):
    """Insee Première : « 1. Évolution de la population… » (titre de figure) ouvrait un chapitre."""

    prose = [
        "Le nombre de naissances dépend du nombre de femmes en âge d'avoir des enfants et de leur",
        "fécondité, qui recule depuis plusieurs années.",
    ]

    def draw(c):
        y = 780
        for title, body in [
            ("Les naissances diminuent en 2024", prose),
            ("1. Évolution de la population, de 2019 à 2025", ["Milliers", "Année", "2019 2020", "Solde"]),
            ("Le nombre de décès augmente en 2024", prose),
            ("2. Nombre de naissances depuis 1965", ["950", "900", "Naissances", "1965 1969 1973"]),
            ("Le nombre de mariages augmente en 2024", prose),
        ]:
            _lines(c, 50, y, [title], font="Helvetica-Bold", size=10)
            _lines(c, 50, y - 16, body, size=10)
            y -= 16 + 14 * len(body) + 20

    doc = _doc(_pdf(tmp_path / "fig.pdf", draw))
    titles = [ch.title for ch in doc.chapters]
    assert titles == [
        "Les naissances diminuent en 2024",
        "Le nombre de décès augmente en 2024",
        "Le nombre de mariages augmente en 2024",
    ]
    kinds = {b.text: b.kind for ch in doc.chapters for b in ch.blocks}
    assert kinds["1. Évolution de la population, de 2019 à 2025"] == "caption"  # toujours lu


def test_sections_numerotees_restent_des_chapitres(tmp_path):
    """Article : « Résumé », « 1. Introduction », « 2. Méthode » : sections numérotées suivies de texte."""

    para = "Ce paragraphe de texte courant est assez long pour former une vraie section de l'article ici."

    def draw(c):
        y = 780
        for title in ["Résumé", "1. Introduction", "2. Méthode", "Références"]:
            _lines(c, 50, y, [title], font="Helvetica-Bold", size=12)
            _lines(c, 50, y - 18, [para, para], size=10)
            y -= 80

    doc = _doc(_pdf(tmp_path / "art.pdf", draw))
    assert [ch.title for ch in doc.chapters] == ["Résumé", "1. Introduction", "2. Méthode", "Références"]


def test_fleuron_isole_ignore(tmp_path):
    """Bibebook : un fleuron de police décorative extrait comme la lettre « n » en fin de chapitre."""

    def draw(c):
        _lines(c, 60, 700, ["Voici quelques-uns de ces récits :"])
        c.setFont("Helvetica", 10)
        c.drawString(200, 660, "n")

    assert _texts(_pdf(tmp_path / "fleuron.pdf", draw)) == ["Voici quelques-uns de ces récits :"]
