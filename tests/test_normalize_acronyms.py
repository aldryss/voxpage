"""Sigles (issue #12) : épelés quand ils ne se prononcent pas comme un mot, laissés tels quels sinon."""

import pytest

from voxpage.normalize.acronyms import is_spelled, wordlike
from voxpage.normalize.text import decaps, speak

SPELLED_FR = [
    ("l'ICF", "l'I C F"), ("le PIB", "le P I B"), ("la SNCF", "la S N C F"), ("la RATP", "la R A T P"),
    ("le CNRS", "le C N R S"), ("EDF", "E D F"), ("la TVA", "la T V A"), ("le PDG", "le P D G"),
    ("un CDD", "un C D D"), ("le RSA", "le R S A"), ("la CAF", "la C A F"), ("le FMI", "le F M I"),
    ("l'OMS", "l'O M S"), ("l'UE", "l'U E"), ("les USA", "les U S A"), ("la HLM", "la H L M"),
    ("le TGV", "le T G V"), ("l'ADN", "l'A D N"), ("une IRM", "une I R M"), ("les PME", "les P M E"),
    ("la CGT", "la C G T"), ("le DGFIP", "le D G F I P"), ("un CD", "un C D"),
]


@pytest.mark.parametrize("text, expected", SPELLED_FR)
def test_sigles_epeles(text, expected):
    assert speak(text, "fr") == expected


def test_hceres_et_sigle_pointe():
    assert speak("évalué par le Hcéres.", "fr") == "évalué par le H C E R E S."
    assert speak("la S.N.C.F. et l'U.E.", "fr") == "la S N C F et l'U E"


WORD_ACRONYMS = ["ONU", "OTAN", "UNESCO", "INSEE", "CNIL", "SMIC", "OVNI", "SIDA", "UNICEF", "NASA", "URSSAF"]


@pytest.mark.parametrize("sigle", WORD_ACRONYMS)
def test_acronymes_qui_se_lisent_comme_un_mot_restent(sigle):
    assert speak(f"selon l'{sigle} et le {sigle}.", "fr") == f"selon l'{sigle} et le {sigle}."


NE_PAS_TOUCHER = [
    ("ATTENTION : ne pas ouvrir.", "ATTENTION : ne pas ouvrir."),  # mot ordinaire en capitales
    ("Réponse : NON.", "Réponse : NON."),
    ("STOP", "STOP"),
    ("Voir le chapitre XIV.", "Voir le chapitre quatorze."),  # chiffres romains déjà gérés
    ("Louis XIV", "Louis quatorze"),
    ("La MCM est un nombre romain.", "La MCM est un nombre romain."),
    ("ÉTAPE 3, TITRE II", "ÉTAPE 3, TITRE deux"),
    ("Un texte avec EXCEPTIONNELLEMENT de longs mots.", "Un texte avec EXCEPTIONNELLEMENT de longs mots."),
    ("CO2 et UE27 gardent leurs chiffres", "CO2 et UE27 gardent leurs chiffres"),  # collé à un chiffre
    ("Les ONGs, le PIBs", "Les ONGs, le PIBs"),  # pluriel collé : on n'y touche pas
    ("Un texte normal, sans sigle.", "Un texte normal, sans sigle."),
]


@pytest.mark.parametrize("text, expected", NE_PAS_TOUCHER)
def test_ne_pas_toucher(text, expected):
    assert speak(text, "fr") == expected


def test_titre_en_capitales_pas_epele():
    # le titre TOUT EN MAJUSCULES est ramené en casse normale avant les sigles ; le sigle y reste épelé
    t = decaps("LA SNCF ET L'ARRIVÉE DES TRAINS", "fr")
    assert speak(t, "fr") == "La S N C F et l'arrivée des trains"
    assert speak(decaps("LE ROI EST MORT", "fr"), "fr") == "Le roi est mort"


def test_anglais():
    assert speak("the FBI and the BBC", "en") == "the F B I and the B B C"
    assert speak("NASA and NATO", "en") == "NASA and NATO"


def test_critere():
    assert wordlike("NOTE") and wordlike("SIDA") and not wordlike("PIB") and not wordlike("RATP")
    assert is_spelled("ICF", "fr") and not is_spelled("ONU", "fr") and not is_spelled("XIV", "fr")
