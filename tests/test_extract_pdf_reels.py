"""Extracteur PDF sur de vrais documents (voir tests/corpus/reels/SOURCES.md).

La sortie complète n'est pas figée (les graphiques et tableaux sans filets restent imparfaits) : on vérifie la
structure, l'absence de bruit et des passages précis, dont ceux qui exigent un bon ordre de lecture.
"""

import re
from pathlib import Path

import pytest

from voxpage.extract import ExtractOptions, extractor_for

REELS = Path(__file__).parent / "corpus" / "reels"


def extract(name: str):
    path = REELS / name
    return extractor_for(path).extract(path, ExtractOptions())


def texts(doc) -> list[str]:
    return [b.text for ch in doc.chapters for b in ch.blocks]


@pytest.fixture(scope="module")
def constitution():
    return extract("constitution-1958.pdf")


@pytest.fixture(scope="module")
def insee():
    return extract("insee-premiere-2033.pdf")


def test_constitution_structure(constitution):
    doc = constitution
    assert (doc.title, doc.author, doc.lang) == (
        "Constitution du 4 octobre 1958",
        "Conseil constitutionnel",
        "fr",
    )
    assert [ch.title for ch in doc.chapters] == [
        "Constitution du 4 octobre 1958",
        "Titre premier - DE LA SOUVERAINETÉ",
        "Titre II - LE PRÉSIDENT DE LA RÉPUBLIQUE",
        "Titre III - LE GOUVERNEMENT",
        "Titre IV - LE PARLEMENT",
        "Titre V - DES RAPPORTS ENTRE LE PARLEMENT ET LE GOUVERNEMENT",
        "Titre VI - DES TRAITÉS ET ACCORDS INTERNATIONAUX",
        "Titre VII - LE CONSEIL CONSTITUTIONNEL",
        "Titre VIII - DE L'AUTORITÉ JUDICIAIRE",
        "Titre IX - LA HAUTE COUR",
        "Titre X - DE LA RESPONSABILITÉ PÉNALE DES MEMBRES DU GOUVERNEMENT",
        "Titre XI - LE CONSEIL ÉCONOMIQUE, SOCIAL ET ENVIRONNEMENTAL",
        "Titre XI bis - LE DÉFENSEUR DES DROITS",
        "Titre XII - DES COLLECTIVITÉS TERRITORIALES",
        "Titre XIII - DISPOSITIONS TRANSITOIRES RELATIVES À LA NOUVELLE-CALÉDONIE",
        "Titre XIV - DE LA FRANCOPHONIE ET DES ACCORDS D'ASSOCIATION",
        "Titre XV - DE L'UNION EUROPÉENNE",
        "Titre XVI - DE LA RÉVISION",
        "Déclaration des Droits de l'Homme et du Citoyen de 1789",
        "Préambule de la Constitution du 27 octobre 1946",
        "Charte de l'environnement de 2004",
    ]
    first = [(b.kind, b.level, b.text) for b in doc.chapters[0].blocks[:3]]
    assert first == [
        ("heading", 1, "Constitution du 4 octobre 1958"),
        ("heading", 2, "Préambule"),
        (
            "paragraph",
            0,
            "Le peuple français proclame solennellement son attachement aux Droits de l'homme et aux "
            "principes de la souveraineté nationale tels qu'ils ont été définis par la Déclaration de "
            "1789, confirmée et complétée par le préambule de la Constitution de 1946, ainsi qu'aux "
            "droits et devoirs définis dans "
            "la Charte de l'environnement de 2004.",
        ),
    ]
    articles = [
        b for ch in doc.chapters for b in ch.blocks if b.kind == "heading" and b.text.startswith("Article")
    ]
    assert len(articles) > 100 and all(b.level == 2 for b in articles)
    last = doc.chapters[-1].blocks[-1]
    assert (last.kind, last.text, last.page) == (
        "paragraph",
        "La présente Charte inspire l'action européenne et internationale de la France.",
        28,
    )


def test_constitution_sans_entetes_ni_numeros(constitution):
    all_text = "\n".join(texts(constitution))
    assert "13/04/2023" not in all_text
    assert not re.search(r"\b\d{1,2}/28\b", all_text)
    assert all_text.count("Constitution du 4 octobre 1958") == 1
    assert "Le Président de la République est élu pour cinq ans au suffrage universel direct." in texts(
        constitution
    )


def test_insee_ordre_de_lecture(insee):
    doc = insee
    assert doc.title == "En 2024, la fécondité continue de diminuer, l’espérance de vie se stabilise"
    assert doc.lang == "fr"
    t = texts(doc)
    # encadré de synthèse, puis trois colonnes de la première page lues dans l'ordre
    assert "Le nombre de Pacs conclus diminue en 2023, mais reste au niveau élevé de 204 000." in t
    assert (
        "Au 1er janvier 2023, la France représentait 15 % de la population de l’Union européenne à 27 pays "
        "(UE27) et en était le deuxième pays le plus peuplé derrière l’Allemagne (19 %). Avec l’Italie, "
        "l’Espagne et la Pologne, pays les plus peuplés après eux, ils représentaient les deux tiers de la "
        "population de l’UE27."
    ) in t
    # paragraphe interrompu par des figures puis repris dans la colonne suivante
    joined = next(x for x in t if x.startswith("En 2022, dernière année disponible"))
    assert (
        "l’ICF s’établissait à 1,46 enfant par femme dans l’ensemble de l’UE27, après 1,53 en 2021." in joined
    )
    deces = next(x for x in t if x.startswith("En 2024, le nombre de décès en France"))
    assert "une durée habituellement observées avant la pandémie de Covid-19" in deces
    assert deces.endswith(
        "En 2024, le nombre de décès est supérieur de 5 % à son niveau pré-pandémique de 2019."
    )


def test_insee_bruit(insee):
    all_text = "\n".join(texts(insee))
    assert all_text.count("Insee Première • n° 2033") == 1  # en-tête de la première page seulement
    assert "1er janvier" in all_text and "1 janvier" not in all_text  # exposant « er » recollé
    titles = [ch.title for ch in insee.chapters]
    assert "Sources et méthode" in titles and "Définitions" in titles
