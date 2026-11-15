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


WORDS = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliett Kilo Lima Mike November".split()


def test_en_tete_d_un_livre_centre_sur_une_page_plus_grande(tmp_path):
    """Cour des comptes, RPA 2023 : maquette A5 centrée sur une page A4 ; l'en-tête « 6 COUR DES COMPTES »
    est à 17 % du haut de la page, hors de la marge de 15 % : il était lu à chaque page paire."""
    path = tmp_path / "rpa.pdf"
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    for n in range(1, 5):
        c.setFont("Helvetica", 8)
        c.drawString(150, H - 150, f"{n + 1} COUR DES COMPTES" if n % 2 else f"CHAPITRE PREMIER {n + 1}")
        y = H - 190
        for k in range(30):
            c.setFont("Helvetica", 10)
            c.drawString(150, y, f"{WORDS[n]} {WORDS[k % 14]} ligne {k} de la page {n}, texte courant.")
            y -= 13
        c.showPage()
    c.save()
    text = "\n".join(_texts(path))
    assert "COUR DES COMPTES" not in text and "CHAPITRE PREMIER" not in text
    assert "ligne 0 de la page 1" in text and "ligne 29 de la page 4" in text


@pytest.mark.parametrize(
    ("before", "exponent"),
    [
        ("10", True),  # 10³
        ("50 m", True),  # m²
        ("(a+b)", True),
        ("atteint en 2018", False),  # Cour des comptes : « en 2018⁶ », appel de note
        ('on parle de « croissance acquise »)', False),  # « (… croissance acquise »)⁴ »
    ],
)
def test_exposant_ou_appel_de_note(before, exponent):
    from voxpage.extract.pdf_structure import _exponent_base

    assert _exponent_base(before, before.split(" ")[-1].lower()) is exponent


def test_chapitre_trop_long_decoupe_au_niveau_inferieur():
    """Cour des comptes, RPA 2023 : 6 signets de premier niveau pour 572 pages ; « La décentralisation
    40 ans après » (pages 59 à 572) faisait un seul fichier de 17 heures en mode « chapitres »."""
    from voxpage.extract.pdf_structure import Bookmark, _chapter_openers

    toc = [
        Bookmark("Sommaire", 0, 2, None),
        Bookmark("Finances publiques", 0, 12, None),
        Bookmark("I - Le déficit", 1, 15, None),  # chapitre court : ses sous-parties restent dedans
        Bookmark("La décentralisation", 0, 58, None),
        Bookmark("Synthèse", 1, 60, None),
        Bookmark("Première partie", 1, 70, None),
        Bookmark("1 Un élan à retrouver", 2, 72, None),
        Bookmark("2 Les finances locales", 2, 124, None),
        Bookmark("Seconde partie", 1, 210, None),
        Bookmark("1 Développement économique", 2, 212, None),
        Bookmark("Réponses", 3, 244, None),  # 66 pages : pas de découpage plus fin
        Bookmark("2 Politiques sociales", 2, 278, None),
        Bookmark("Conclusion", 1, 566, None),
    ]
    titles = [toc[n].title for n in sorted(_chapter_openers(toc, 0))]
    assert titles == [
        "Sommaire",
        "Finances publiques",
        "La décentralisation",
        "Synthèse",
        "Première partie",
        "1 Un élan à retrouver",
        "2 Les finances locales",
        "Seconde partie",
        "1 Développement économique",
        "2 Politiques sociales",
        "Conclusion",
    ]


def test_lettrine_dont_la_boite_deborde_sur_le_retrait(tmp_path):
    """« T, » (Bibebook, « La folle ») : la boîte de la lettrine dépasse le retrait des lignes suivantes."""

    def draw(c):
        c.setFont("Helvetica", 40)
        c.drawString(60, 700 - 24, "T,")  # largeur ~ 33 pt : déborde sur le retrait (x = 88)
        _lines(c, 110, 700, ["enez, dit M. Mathieu, les bécasses me rappellent une"])
        _lines(c, 88, 688, ["bien sinistre anecdote de la guerre. Vous connaissez", "ma propriété."])
        _lines(c, 60, 664, ["Je l'habitais au moment de l'arrivée des Prussiens."])

    text = " ".join(_texts(_pdf(tmp_path / "t.pdf", draw)))
    assert text.index("Mathieu") < text.index("sinistre") < text.index("propriété") < text.index("habitais")
