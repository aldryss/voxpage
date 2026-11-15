"""Tables de cas : entrée -> sortie exacte (speak) et cas « ne pas toucher »."""

import pytest

from voxpage.normalize.text import clean_block, decaps, speak

TEL = "zéro un, vingt-trois, quarante-cinq, soixante-sept, quatre-vingt-neuf"

FR = [
    # abréviations
    ("M. Dupont est là.", "Monsieur Dupont est là."),
    ("Bonjour Mme Martin et Mlle Roy.", "Bonjour madame Martin et mademoiselle Roy."),
    ("MM. Durand et Petit", "Messieurs Durand et Petit"),
    ("Le Dr Durand", "Le docteur Durand"),
    ("Le Dr. Durand", "Le docteur Durand"),
    ("Pommes, poires, etc.", "Pommes, poires, et cetera."),
    ("Pommes, etc., puis poires", "Pommes, et cetera, puis poires"),
    ("cf. Dupont", "confer Dupont"),
    ("Voir cf. la note", "Voir confer la note"),
    ("n° 5 et N° 6", "numéro 5 et Numéro 6"),
    ("les n°s 5 et 6", "les numéros 5 et 6"),
    ("§ 3 et §§ 4", "paragraphe 3 et paragraphes 4"),
    ("p. 12", "page 12"),
    ("pp. 12-15", "pages 12 à 15"),
    ("l'art. 12 et les arts. 13", "l'article 12 et les articles 13"),
    ("Voir al. 2 du chap. 3, fig. 4.", "Voir alinéa 2 du chapitre 3, figure 4."),
    ("par ex. p. ex. chez", "par ex. par exemple chez"),
    ("en 50 av. J.-C.", "en 50 avant Jésus-Christ"),
    ("en 70 apr. J.-C.", "en 70 après Jésus-Christ"),
    ("c.-à-d. ceci", "c'est-à-dire ceci"),
    ("Tél. : 01 23 45 67 89", "Téléphone : " + TEL),
    # nombres
    ("1 234 567 habitants", "1234567 habitants"),
    ("1 234 567 habitants", "1234567 habitants"),
    ("1 234 habitants", "1234 habitants"),
    ("1.234.567 habitants", "1234567 habitants"),
    ("1 234 € de frais", "1234 euros de frais"),
    ("3,14", "trois virgule quatorze"),
    ("0,05", "zéro virgule zéro cinq"),
    ("2,5 millions", "deux virgule cinq millions"),
    ("3,14159", "trois virgule un quatre un cinq neuf"),
    ("50 %", "50 pour cent"),
    ("12,5%", "douze virgule cinq pour cent"),
    ("le 1er mai", "le premier mai"),
    ("la 1re fois", "la première fois"),
    ("la 2e fois, le 21e jour, les 3es", "la deuxième fois, le vingt et unième jour, les troisièmes"),
    ("le 80e", "le quatre-vingtième"),
    ("2ème étage", "deuxième étage"),
    ("de 10-15 ans", "de 10 à 15 ans"),
    ("pages 10-15", "pages 10 à 15"),
    ("le 3/4 de la somme", "le trois quarts de la somme"),
    ("les 3/4 des élèves", "les trois quarts des élèves"),
    ("1/2 des élèves", "la moitié des élèves"),
    ("½ litre", "un demi litre"),
    ("01 23 45 67 89", TEL),
    ("01.23.45.67.89", TEL),
    ("+33 1 23 45 67 89", "plus trente-trois, un, " + TEL.split(", ", 1)[1]),
    ("06 12 34 56 78", "zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit"),
    # dates et heures
    ("le 12/03/2024", "le 12 mars 2024"),
    ("le 01/03/2024", "le premier mars 2024"),
    ("le 5.11.2023", "le 5 novembre 2023"),
    ("le 2024-03-12", "le 12 mars 2024"),
    ("à 14h30", "à 14 heures 30"),
    ("à 14 h 30", "à 14 heures 30"),
    ("à 14h", "à 14 heures"),
    ("à 1h05", "à 1 heure 5"),
    ("à 14h00", "à 14 heures"),
    ("rendez-vous à 14:30", "rendez-vous à 14 heures 30"),
    ("de 9:00 à 17:30", "de 9 heures à 17 heures 30"),
    # monnaies
    ("12,50 €", "12 euros 50"),
    ("12 €", "12 euros"),
    ("1 €", "1 euro"),
    ("0,50 €", "0 euro 50"),
    ("12,5 €", "12 euros 50"),
    ("$5", "5 dollars"),
    ("5 $", "5 dollars"),
    ("£3,20", "3 livres sterling 20"),
    ("1,5 M€", "un virgule cinq million d'euros"),
    ("3 M€", "3 millions d'euros"),
    ("1,5 million €", "un virgule cinq million d'euros"),
    # unités
    ("12 km", "12 kilomètres"),
    ("1 km", "1 kilomètre"),
    ("1,5 km", "un virgule cinq kilomètre"),
    ("70 kg", "70 kilogrammes"),
    ("50 m²", "50 mètres carrés"),
    ("20 °C", "20 degrés Celsius"),
    ("20°C", "20 degrés Celsius"),
    ("-5 °C", "moins 5 degrés Celsius"),
    ("45°", "45 degrés"),
    ("90 km/h", "90 kilomètres par heure"),
    ("5 Mo, 2 Go", "5 mégaoctets, 2 gigaoctets"),
    ("100 MHz", "100 mégahertz"),
    # romains
    ("au XIXe siècle", "au dix-neuvième siècle"),
    ("le XXIe siècle", "le vingt et unième siècle"),
    ("la Ve République", "la cinquième République"),
    ("Louis XIV", "Louis quatorze"),
    ("Charles V", "Charles cinq"),
    ("Jean XXIII", "Jean vingt-trois"),
    ("François Ier", "François premier"),
    ("chapitre IV", "chapitre quatre"),
    ("Tome II", "Tome deux"),
    # symboles
    ("A & B", "A et B"),
    ("2 + 2 = 4", "2 plus 2 égale 4"),
    ("3 × 4", "3 fois 4"),
    ("a ≥ b", "a supérieur ou égal à b"),
    ("a → b", "a flèche b"),
    ("© 2024 Éditions", "copyright 2024 Éditions"),
    ("Windows™", "Windows marque commerciale"),
    ("jean.dupont@exemple.fr", "jean point dupont arobase exemple point fr"),
    ("https://www.exemple.fr/page-1", "w w w point exemple point fr slash page tiret 1"),
    ("Voir http://exemple.fr.", "Voir exemple point fr."),
    # recette sur documents réels (issue #11)
    ("En 2024, 663 000 bébés sont nés.", "En 2024, 663000 bébés sont nés."),  # Insee : chiffres lus un à un
    ("soit +1,1 % par rapport à 2023", "soit plus un virgule un pour cent par rapport à 2023"),
    ("(-3 %) et -84 et −6,6 %", "(moins 3 pour cent) et moins 84 et moins six virgule six pour cent"),
    ("Pyramides des âges, janvier 2025e.", "Pyramides des âges, janvier 2025e."),  # lettre de référence
    ("1° ont en France leur foyer ;", "premièrement, ont en France leur foyer ;"),  # impôts 2041-E
    ("2° exercent en France une activité", "deuxièmement, exercent en France une activité"),
    ("12° à l'ombre", "12 degrés à l'ombre"),
    ("(cf paragraphe 1)", "(confer paragraphe 1)"),
    ("Je laissai à M. le curé les francs.", "Je laissai à monsieur le curé les francs."),  # Maupassant
    ("Voici M. de Villefort", "Voici monsieur de Villefort"),
    # Cour des comptes, RPA 2023
    ("(+ 5,7 % en valeur)", "(plus cinq virgule sept pour cent en valeur)"),
    ("inférieur de - 0,3 % à 2019", "inférieur de moins zéro virgule trois pour cent à 2019"),
    ("Baisse du taux d'IS; - 2,9", "Baisse du taux d'IS; moins deux virgule neuf"),
    ("(hors effet CICE, Md€)", "(hors effet CICE, milliards d'euros)"),
]

# cas « ne pas toucher » : l'ambiguïté impose de laisser le texte tel quel
FR_INTACT = [
    "Chapitre premier",
    "La loi 2004-801 et la décision 12-15 du conseil.",
    "Jean 3:16",
    "Il a 3 ans",
    "En 2024, 1789 et 12345 sont des nombres.",
    "Je vais au 1/2 finale",
    "Il mange 1/2 de litre.",
    "le Ve",
    "Il a dit I et V.",
    "Pierre V. Martin",
    "C++ et R&D",
    "page 12 345 mots",
    "version 1.2.3",
    "192.168.1.1",
    "Le 31/02/2024 n'existe pas.",
    "Pas de 25h99.",
    "Le Dr est là.",
    "1, 2, 3 soleil",
    "pages 12, 345 et 400",
    "1, 234 personnes",
    "de 2010 - 2020",
    "A - Une activité",
    "La loi 99-209 et le COVID-19",
    "Le chat boit du lait.",
    "Elle a mangé 5 s.",
    "Une phrase simple.",
]


@pytest.mark.parametrize("text, expected", FR)
def test_speak_fr(text, expected):
    assert speak(text, "fr") == expected


@pytest.mark.parametrize("text", FR_INTACT)
def test_speak_fr_ne_touche_pas(text):
    assert speak(text, "fr") == text


def test_plage_avec_contexte_sur():
    assert speak("Il y a 10-15 personnes.", "fr") == "Il y a 10 à 15 personnes."
    assert speak("Loi n° 2004-801.", "fr") == "Loi numéro 2004-801."


EN = [
    ("Mr. Smith and Mrs. Jones", "Mister Smith and missus Jones"),
    ("Dr. Who", "Doctor Who"),
    ("fruit, e.g. apples", "fruit, for example apples"),
    ("that is, i.e. this", "that is, that is this"),
    ("See p. 12 and pp. 3-5, Fig. 2", "See page 12 and pages 3 to 5, figure 2"),
    ("No. 5", "Number 5"),
    ("apples, pears, etc.", "apples, pears, et cetera."),
    ("1,234,567 people", "1234567 people"),
    ("3.14", "three point one four"),
    ("0.5", "zero point five"),
    ("50%", "50 percent"),
    ("$5", "5 dollars"),
    ("$5.50", "5 dollars 50"),
    ("$1.5 million", "one point five million dollars"),
    ("£3", "3 pounds"),
    ("12 km, 1 km, 70 kg", "12 kilometers, 1 kilometer, 70 kilograms"),
    ("20 °C", "20 degrees Celsius"),
    ("5 GB", "5 gigabytes"),
    ("13/03/2024", "13 March 2024"),
    ("03/13/2024", "March 13, 2024"),
    ("2024-03-12", "March 12, 2024"),
    ("Chapter IV", "Chapter four"),
    ("Henry VIII", "Henry the eighth"),
    ("A & B", "A and B"),
    ("2 × 3", "2 times 3"),
    ("john@example.com", "john at example dot com"),
]

EN_INTACT = [
    "Chapter I wrote this.",
    "The date is 03/04/2024.",
    "I think so.",
    "He is 5 in the morning.",
    "It is 1st and 2nd.",
    "Version 1.2.3",
]


@pytest.mark.parametrize("text, expected", EN)
def test_speak_en(text, expected):
    assert speak(text, "en") == expected


@pytest.mark.parametrize("text", EN_INTACT)
def test_speak_en_ne_touche_pas(text):
    assert speak(text, "en") == text


DECAPS = [
    ("INTRODUCTION", "Introduction", "fr"),
    ("LE ROI EST MORT", "Le roi est mort", "fr"),
    ("CHAPITRE IV", "Chapitre IV", "fr"),
    ("LA SNCF ET L'ARRIVÉE DES TRAINS", "La SNCF et l'arrivée des trains", "fr"),
    ("HISTOIRE DE FRANCE. PREMIÈRE PARTIE", "Histoire de france. Première partie", "fr"),
    ("SNCF", "SNCF", "fr"),
    ("ONU", "ONU", "fr"),
    ("THE END OF THE WORLD", "The end of the world", "en"),
    ("Le texte normal garde sa SNCF", "Le texte normal garde sa SNCF", "fr"),
    ("Bonjour", "Bonjour", "fr"),
    ("RAPPORT ANNUEL DU CNRS", "Rapport annuel du CNRS", "fr"),
    ("TITRE XI BIS - LE DÉFENSEUR DES DROITS", "Titre XI bis - le défenseur des droits", "fr"),
]


@pytest.mark.parametrize("text, expected, lang", DECAPS)
def test_decaps(text, expected, lang):
    assert decaps(text, lang) == expected


CLEAN = [
    ("Délibéré.................................. 5", "paragraph", "Délibéré, 5"),  # Cour des comptes
    ("Synthèse générale ……………… 61", "paragraph", "Synthèse générale, 61"),
    ("Il hésita... puis partit.", "paragraph", "Il hésita... puis partit."),
    ("• Premier point", "list_item", "Premier point"),
    ("- Premier point", "list_item", "Premier point"),
    ("– Premier point", "list_item", "Premier point"),
    ("1. Premier point", "list_item", "1, Premier point"),
    ("2) Second point", "list_item", "2, Second point"),
    ("a) Troisième", "list_item", "a, Troisième"),
    ("— Bonjour, dit-il.", "paragraph", "— Bonjour, dit-il."),
    ("Ligne un\nligne deux", "paragraph", "Ligne un ligne deux"),
    ("Mot­coupé et​ espace", "paragraph", "Motcoupé et espace"),
    ("Texte[1] avec renvoi[2,3] suite [3, 4] fin.", "paragraph", "Texte avec renvoi suite fin."),
    ("3. Titre de section", "paragraph", "3, Titre de section"),
    ("En 1789. La révolution", "paragraph", "En 1789. La révolution"),
]


@pytest.mark.parametrize("text, kind, expected", CLEAN)
def test_clean_block(text, kind, expected):
    assert clean_block(text, kind) == expected
