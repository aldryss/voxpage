"""Tests d'intégration de normalize() sur des Document complets + relecture de textes réels."""

import re

from voxpage.document import Block, Chapter, Document
from voxpage.normalize import NormalizeOptions, Segment, normalize

OPTS = NormalizeOptions(sentence_pause_ms=250, paragraph_pause_ms=700, heading_pause_ms=1200)


def texts(chapter):
    return [s.text for s in chapter.segments]


def make_doc():
    return Document(
        title="Rapport",
        author=None,
        lang="fr",
        chapters=[
            Chapter("INTRODUCTION", [
                Block("heading", "INTRODUCTION", level=1, page=1),
                Block("paragraph", "M. Dupont est arrivé le 12/03/2024 à 14h30. Il a payé 12,50 €.", page=1),
                Block("list_item", "• Premier point", page=1),
                Block("list_item", "• Second point, avec 3,5 km.", page=1),
                Block("table", "Ville\tHabitants\nParis\t2 100 000", page=2),
                Block("caption", "Figure 1. Vue de Paris", page=2),
                Block("footnote", "Voir p. 12 du rapport.", page=2),
            ]),
            Chapter("Conclusion", [
                Block("paragraph", "Fin du rapport…", page=3),
            ]),
        ],
    )


def test_document_complet():
    chapters = normalize(make_doc(), OPTS)
    assert [c.title for c in chapters] == ["INTRODUCTION", "Conclusion"]
    assert [(s.text, s.pause_after_ms) for s in chapters[0].segments] == [
        ("Introduction", 1200),  # titre dit une seule fois, en casse normale
        ("Monsieur Dupont est arrivé le 12 mars 2024 à 14 heures 30.", 250),
        ("Il a payé 12 euros 50.", 700),
        ("Premier point", 700),
        ("Second point, avec trois virgule cinq kilomètres.", 700),
        ("Ville, Habitants", 250),
        ("Paris, 2100000", 700),
        ("Figure 1.", 250),
        ("Vue de Paris", 700),
        ("Note : Voir page 12 du rapport.", 700),
    ]
    assert [(s.text, s.pause_after_ms) for s in chapters[1].segments] == [
        ("Conclusion", 1200),
        ("Fin du rapport…", 700),
    ]


def test_titre_de_chapitre_dit_si_pas_de_bloc_heading():
    doc = Document("T", None, "fr", [Chapter("Premier chapitre", [Block("paragraph", "Texte.")])])
    segs = normalize(doc, OPTS)[0].segments
    assert segs == [Segment("Premier chapitre", 1200), Segment("Texte.", 700)]


def test_titre_de_chapitre_non_duplique_meme_avec_casse_differente():
    doc = Document("T", None, "fr", [Chapter("Chapitre 1", [
        Block("heading", "CHAPITRE 1", level=1), Block("paragraph", "Texte.")])])
    assert texts(normalize(doc, OPTS)[0]) == ["Chapitre 1", "Texte."]


def test_titre_different_du_premier_heading_est_dit_en_plus():
    doc = Document("T", None, "fr", [Chapter("Partie A", [
        Block("heading", "Un autre titre", level=2), Block("paragraph", "Texte.")])])
    assert texts(normalize(doc, OPTS)[0]) == ["Partie A", "Un autre titre", "Texte."]


def test_chapitre_sans_titre():
    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", "Texte.")])])
    assert [c.title for c in normalize(doc, OPTS)] == [""]
    assert texts(normalize(doc, OPTS)[0]) == ["Texte."]


def test_headings_non_annonces():
    opts = NormalizeOptions(announce_headings=False)
    chapters = normalize(make_doc(), opts)
    assert chapters[0].title == "INTRODUCTION"
    assert "Introduction" not in texts(chapters[0])
    assert texts(chapters[1]) == ["Fin du rapport…"]


def test_pauses_personnalisees():
    opts = NormalizeOptions(sentence_pause_ms=100, paragraph_pause_ms=500, heading_pause_ms=900)
    segs = normalize(make_doc(), opts)[0].segments
    assert segs[0].pause_after_ms == 900
    assert segs[1].pause_after_ms == 100
    assert segs[2].pause_after_ms == 500


def test_document_vide_et_blocs_vides():
    assert normalize(Document("T", None, "fr", []), OPTS) == []
    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", "   "), Block("paragraph", "…")])])
    assert normalize(doc, OPTS)[0].segments == []


def test_aucun_segment_vide_ni_ponctuation_seule():
    doc = Document("T", None, "fr", [Chapter("", [
        Block("paragraph", "— — —"),
        Block("paragraph", "• "),
        Block("list_item", "•"),
        Block("table", "|\t|\n"),
        Block("paragraph", "[12]"),
        Block("paragraph", "Vrai texte."),
    ])])
    segs = normalize(doc, OPTS)[0].segments
    assert [s.text for s in segs] == ["Vrai texte."]
    assert segs[-1].pause_after_ms == 700


def test_phrase_tres_longue_recoupee_sous_400():
    long = ", ".join(f"le mot numéro {i} est suivi d'autres mots" for i in range(40)) + "."
    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", long)])])
    segs = normalize(doc, OPTS)[0].segments
    assert len(segs) > 1
    assert all(len(s.text) <= 400 for s in segs)
    assert segs[-1].pause_after_ms == 700
    assert all(s.pause_after_ms < 250 for s in segs[:-1])  # pause de virgule dans la même phrase


def test_puces_en_ligne_deviennent_des_elements():
    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", "Liste :\n• un\n• deux")])])
    assert [(s.text, s.pause_after_ms) for s in normalize(doc, OPTS)[0].segments] == [
        ("Liste :", 250), ("un", 250), ("deux", 700)]


def test_anglais():
    doc = Document("T", None, "en", [Chapter("CHAPTER I", [
        Block("paragraph", "Mr. Smith paid $5.50 on 13/03/2024. He walked 3.5 km."),
        Block("footnote", "See p. 4."),
    ])])
    out = normalize(doc, OPTS)[0]
    assert texts(out) == [
        "Chapter I",
        "Mister Smith paid 5 dollars 50 on 13 March 2024.",
        "He walked three point five kilometers.",
        "Note: See page 4.",
    ]


def test_langue_inconnue_traitee_comme_francais():
    doc = Document("T", None, "", [Chapter("", [Block("paragraph", "M. Dupont.")])])
    assert texts(normalize(doc, OPTS)[0]) == ["Monsieur Dupont."]


# --------------------------------------------------------------------------- relecture de textes réels

PRESSE = [
    "Selon M. Jean Dupont, maire de Lyon depuis le 3 juillet 2020, la ville a investi 12,5 M€ dans la "
    "rénovation de 48 écoles, soit 3,2 % de son budget annuel. « Nous avons dépassé nos objectifs », "
    "a-t-il déclaré mardi à 14h30, devant plus de 1 200 personnes. Mme Martin, adjointe à l'éducation, "
    "a précisé que les travaux, commencés en 2019, s'étaleront sur 5 ans (cf. le rapport p. 12).",
    "Le président de la Ve République a rappelé, lors d'un déplacement à Marseille le 12/09/2023, que le "
    "XXIe siècle serait celui de la transition écologique. Les températures ont atteint 38 °C, un record "
    "pour un mois de septembre ; les vents soufflaient à 90 km/h. Renseignements : 04 91 23 45 67 ou "
    "www.exemple.fr/info, contact@exemple.fr.",
]
PRESSE_ATTENDU = [
    "Selon monsieur Jean Dupont, maire de Lyon depuis le 3 juillet 2020, la ville a investi douze "
    "virgule cinq millions d'euros dans la rénovation de 48 écoles, soit trois virgule deux pour cent "
    "de son budget annuel.",
    '"Nous avons dépassé nos objectifs", a-t-il déclaré mardi à 14 heures 30, devant plus de 1200 '
    "personnes.",
    "Madame Martin, adjointe à l'éducation, a précisé que les travaux, commencés en 2019, "
    "s'étaleront sur 5 ans (confer le rapport page 12).",
    "Le président de la cinquième République a rappelé, lors d'un déplacement à Marseille le 12 "
    "septembre 2023, que le vingt et unième siècle serait celui de la transition écologique.",
    "Les températures ont atteint 38 degrés Celsius, un record pour un mois de septembre ; les vents "
    "soufflaient à 90 kilomètres par heure.",
    "Renseignements : zéro quatre, quatre-vingt-onze, vingt-trois, quarante-cinq, soixante-sept ou "
    "w w w point exemple point fr slash info, contact arobase exemple point fr.",
]

ADMIN = [
    "Vu l'article L. 123-4 du code de l'urbanisme ; vu le décret n° 2019-1234 du 5 novembre 2019 ; vu la "
    "loi n° 2004-801 du 6 août 2004, notamment son art. 12 et ses §§ 3 à 5, etc.",
    "Le montant de la subvention est fixé à 1 234 567,89 € (soit 15,5 % du coût total de l'opération, "
    "estimé à 8 000 000 €). Le bénéficiaire s'engage à verser 2 500 € avant le 01/03/2024, puis 750,50 € "
    "par trimestre, du 1er janvier au 31 décembre. Tout litige relève du tribunal de Paris "
    "(tél. : 01 42 00 00 00).",
]
ADMIN_ATTENDU = [
    "Vu l'article L. 123-4 du code de l'urbanisme ; vu le décret numéro 2019 tiret 1234 du 5 novembre 2019 ; "
    "vu la loi numéro 2004 tiret 801 du 6 août 2004, notamment son article 12 et ses paragraphes 3 à 5, et "
    "cetera.",
    "Le montant de la subvention est fixé à 1234567 euros 89 (soit quinze virgule cinq pour cent du coût "
    "total de l'opération, estimé à 8000000 euros).",
    "Le bénéficiaire s'engage à verser 2500 euros avant le premier mars 2024, puis 750 euros 50 par "
    "trimestre, du premier janvier au 31 décembre.",
    "Tout litige relève du tribunal de Paris (téléphone : zéro un, quarante-deux, zéro zéro, zéro zéro, "
    "zéro zéro).",
]

SCIENCE = [
    "La concentration passe de 0,05 à 0,5 mol/L à 25 °C. L'échantillon de 2,5 g a été chauffé pendant "
    "30 min, puis refroidi à -20 °C (± 0,5 °C). Les résultats (p < 0,05) sont donnés au tableau 3, p. 45.",
    "Selon Dr. A. Martin et al. [12], 45 % des 1 500 patients (âge moyen : 54,3 ans) ont présenté une "
    "amélioration en 3 à 6 mois. Voir aussi Louis XIV, chap. IV, et les travaux du XIXe siècle, p. ex. "
    "ceux de Pasteur (1822-1895).",
]
SCIENCE_ATTENDU = [
    "La concentration passe de zéro virgule zéro cinq à zéro virgule cinq mol/L à 25 degrés Celsius.",
    "L'échantillon de deux virgule cinq grammes a été chauffé pendant 30 minutes, puis refroidi à moins "
    "20 degrés Celsius (plus ou moins zéro virgule cinq degré Celsius).",
    "Les résultats (p inférieur à zéro virgule zéro cinq) sont donnés au tableau 3, page 45.",
    "Selon docteur A. Martin et alii, 45 pour cent des 1500 patients (âge moyen : cinquante-quatre "
    "virgule trois ans) ont présenté une amélioration en 3 à 6 mois.",
    "Voir aussi Louis quatorze, chapitre quatre, et les travaux du dix-neuvième siècle, par exemple ceux "
    "de Pasteur (1822-1895).",
]


def _lire(paragraphes):
    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", p) for p in paragraphes])])
    return texts(normalize(doc, OPTS)[0])


def test_article_de_presse():
    assert _lire(PRESSE) == PRESSE_ATTENDU


def test_texte_administratif():
    assert _lire(ADMIN) == ADMIN_ATTENDU


def test_texte_scientifique():
    assert _lire(SCIENCE) == SCIENCE_ATTENDU


def test_aucun_chiffre_ou_mot_perdu_sur_texte_sans_regle():
    """Un texte sans rien à réécrire ressort mot pour mot."""
    brut = ("Il était une fois un petit village au bord de la mer. Chaque matin, les pêcheurs partaient "
            "à l'aube ; chaque soir, ils rentraient avec leurs filets pleins. Personne ne savait pourquoi.")
    assert " ".join(_lire([brut])) == brut


def test_pas_de_reste_de_motif_brut():
    sortie = " ".join(_lire(PRESSE + ADMIN + SCIENCE))
    assert not re.search(r"[€%§°]|\bn°|\bp\.\s?\d|\bart\.", sortie)
