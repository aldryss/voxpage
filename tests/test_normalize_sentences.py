import pytest

from voxpage.normalize.sentences import split_long, split_sentences

FR = [
    ("Il est venu. Il est reparti.", ["Il est venu.", "Il est reparti."]),
    ("M. Dupont est arrivé. Mme Martin aussi.", ["M. Dupont est arrivé.", "Mme Martin aussi."]),
    ("Le Dr. Durand et le Pr. Petit sont là.", ["Le Dr. Durand et le Pr. Petit sont là."]),
    ("Voir l'art. 12 et cf. Dupont, p. 45. Fin.", ["Voir l'art. 12 et cf. Dupont, p. 45.", "Fin."]),
    ("Il a acheté des pommes, des poires, etc. Puis il est parti.",
     ["Il a acheté des pommes, des poires, etc.", "Puis il est parti."]),
    ("Il a acheté des pommes, etc. et des poires.", ["Il a acheté des pommes, etc. et des poires."]),
    ("Elle est née en 50 av. J.-C. Puis elle a voyagé.",
     ["Elle est née en 50 av. J.-C.", "Puis elle a voyagé."]),
    ("Le prix est de 3.50 euros. C'est cher.", ["Le prix est de 3.50 euros.", "C'est cher."]),
    ("Pi vaut 3,14. Et e vaut 2,71.", ["Pi vaut 3,14.", "Et e vaut 2,71."]),
    ("Il hésita... Puis il parla.", ["Il hésita...", "Puis il parla."]),
    ("Il hésita... puis il parla.", ["Il hésita... puis il parla."]),
    ("Il attendit… Elle arriva.", ["Il attendit…", "Elle arriva."]),
    ("Il dit : « Venez. » Puis il sortit.", ["Il dit : « Venez. »", "Puis il sortit."]),
    ("Vraiment ? Oui ! Bien sûr.", ["Vraiment ?", "Oui !", "Bien sûr."]),
    ("« Quoi ? » dit-il. Rien.", ["« Quoi ? » dit-il.", "Rien."]),
    ("Voir (fig. 2). La suite.", ["Voir (fig. 2).", "La suite."]),
    ("J. Dupont et A. B. Martin sont venus. Ils partent.",
     ["J. Dupont et A. B. Martin sont venus.", "Ils partent."]),
    ("La S.N.C.F. est en grève. Les trains sont annulés.",
     ["La S.N.C.F. est en grève.", "Les trains sont annulés."]),
    ("Contactez-nous au n° 5 ou au 01 23 45 67 89. Merci.",
     ["Contactez-nous au n° 5 ou au 01 23 45 67 89.", "Merci."]),
    ("Écrire à jean@exemple.fr. Merci.", ["Écrire à jean@exemple.fr.", "Merci."]),
    ("Visitez www.exemple.fr. Bonne visite.", ["Visitez www.exemple.fr.", "Bonne visite."]),
    ("", []),
    ("   ", []),
    ("Sans point final", ["Sans point final"]),
    ("Au XIXe siècle. Puis le XXe.", ["Au XIXe siècle.", "Puis le XXe."]),
]

EN = [
    ("Mr. Smith met Dr. Jones. They talked.", ["Mr. Smith met Dr. Jones.", "They talked."]),
    ("Use fruit, e.g. apples. Then stop.", ["Use fruit, e.g. apples.", "Then stop."]),
    ("See Fig. 3 and p. 12. Done.", ["See Fig. 3 and p. 12.", "Done."]),
    ("It costs 3.5 dollars. Cheap.", ["It costs 3.5 dollars.", "Cheap."]),
]


@pytest.mark.parametrize("text, expected", FR)
def test_phrases_fr(text, expected):
    assert split_sentences(text, "fr") == expected


@pytest.mark.parametrize("text, expected", EN)
def test_phrases_en(text, expected):
    assert split_sentences(text, "en") == expected


def test_recoupage_phrase_longue_a_la_virgule():
    sentence = ", ".join(f"mot{i} suivi de quelques autres mots" for i in range(30)) + "."
    assert len(sentence) > 400
    pieces = split_long(sentence)
    assert len(pieces) > 1
    assert all(len(p) <= 400 for p in pieces)
    assert all(p.endswith(",") for p in pieces[:-1])
    assert " ".join(pieces) == sentence


def test_recoupage_sans_virgule_coupe_a_un_espace():
    sentence = " ".join(["mot"] * 300)
    pieces = split_long(sentence)
    assert all(len(p) <= 400 for p in pieces)
    assert " ".join(pieces) == sentence


def test_phrase_courte_inchangee():
    assert split_long("Courte phrase.") == ["Courte phrase."]
