"""Dictionnaire de prononciation (issue #13) : lecture, correspondance, fusion, écriture."""

import time

import pytest

from voxpage.document import Block, Chapter, Document
from voxpage.normalize import NormalizeOptions, normalize
from voxpage.normalize.lexicon import (
    Entry,
    Lexicon,
    LexiconError,
    LexiconFile,
    LexiconSource,
    merge,
    parse,
    read_entries,
    shipped_entries,
)


def say(text: str, mapping: dict[str, str], lang: str = "fr") -> str:
    return Lexicon(mapping, lang).say(text)


# --------------------------------------------------------------------------- lecture du fichier


def test_lecture_simple():
    entries, problems = parse("INRIA = inria\nEDF = eu dé effe\n")
    assert [(e.written, e.spoken, e.lang, e.line) for e in entries] == [
        ("INRIA", "inria", "", 1),
        ("EDF", "eu dé effe", "", 2),
    ]
    assert problems == []


@pytest.mark.parametrize(
    "text",
    [
        "# commentaire\n\n   \nEDF = eu dé effe\n",
        "﻿EDF = eu dé effe\n",  # BOM
        "EDF = eu dé effe\r\n",  # fins de ligne Windows
        "\r\n# x\r\n\r\nEDF=eu dé effe",  # sans espaces, sans fin de ligne
        "  EDF   =   eu dé effe   \n",
    ],
)
def test_lecture_tolerante(text):
    entries, problems = parse(text)
    assert [(e.written, e.spoken) for e in entries] == [("EDF", "eu dé effe")]
    assert problems == []


def test_le_dit_peut_contenir_un_egal_ou_un_diese():
    entries, _ = parse("a=b = c\nC# = c dièse\n")
    assert [(e.written, e.spoken) for e in entries] == [("a", "b = c"), ("C#", "c dièse")]


def test_dit_vide_annule():
    entries, problems = parse("EDF =\n")
    assert [(e.written, e.spoken) for e in entries] == [("EDF", "")]
    assert problems == []


@pytest.mark.parametrize(
    "text, line, fragment",
    [
        ("EDF eu dé effe\n", 1, "signe « = » absent"),
        ("# ok\nEDF = x\n= rien\n", 3, "rien avant"),
        ("\n\n[espagnol]\n", 3, "section"),
    ],
)
def test_lignes_invalides_signalees_avec_leur_numero(text, line, fragment):
    _, problems = parse(text)
    assert [p.line for p in problems] == [line]
    assert fragment in problems[0].message
    assert f"ligne {line} ignorée" in str(problems[0])


def test_une_ligne_invalide_n_empeche_pas_les_autres():
    entries, problems = parse("A1 = a un\nn'importe quoi\nB2 = b deux\n")
    assert [e.written for e in entries] == ["A1", "B2"]
    assert len(problems) == 1


def test_sections():
    entries, _ = parse("TOUS = t\n[fr]\nFR = f\n[en]\nEN = e\n[toutes]\nENCORE = t2\n[FR]\nMAJ = m\n")
    assert {e.written: e.lang for e in entries} == {
        "TOUS": "", "FR": "fr", "EN": "en", "ENCORE": "", "MAJ": "fr",
    }


def test_section_inconnue_ignore_ses_entrees():
    entries, problems = parse("[es]\nHOLA = ola\n[fr]\nOK = ok\n")
    assert [e.written for e in entries] == ["OK"]
    assert len(problems) == 1


def test_fichier_absent_ou_non_utf8(tmp_path):
    assert read_entries(tmp_path / "absent.txt") == ([], [])
    ansi = tmp_path / "ansi.txt"
    ansi.write_bytes("Hcéres = ache cé eu\n".encode("cp1252"))
    entries, problems = read_entries(ansi)
    assert [e.written for e in entries] == ["Hcéres"]
    assert problems and "UTF-8" in problems[0].message


# --------------------------------------------------------------------------- correspondance

BOUNDARIES = [
    # (texte, attendu) avec UE = « u eu »
    ("l'UE", "l'u eu"),
    ("d’UE", "d’u eu"),
    ("(UE)", "(u eu)"),
    ("UE.", "u eu."),
    ("UE, et", "u eu, et"),
    ("« UE »", "« u eu »"),
    ("pro-UE", "pro-u eu"),
    ("UE-27", "u eu-27"),
    ("de l'UE à 27", "de l'u eu à 27"),
    ("la QUEUE", "la QUEUE"),
    ("bleue", "bleue"),
    ("UE27", "UE27"),
    ("UEFA", "UEFA"),
    ("RUE", "RUE"),
    ("ue", "ue"),  # entrée sensible à la casse
    ("sous l'égide de l'UE; puis", "sous l'égide de l'u eu; puis"),
    ("UE UE", "u eu u eu"),
    ("UE\nUE", "u eu\nu eu"),
]


@pytest.mark.parametrize("text, expected", BOUNDARIES)
def test_frontieres_de_mots(text, expected):
    assert say(text, {"UE": "u eu"}) == expected


def test_apostrophe_collee_a_un_mot_n_est_pas_une_frontiere():
    # « O'Neil » : « Neil » n'est pas un mot seul ; « l'Neil » (élision) l'est
    m = {"Neil": "nile"}
    assert say("O'Neil et Neil", m) == "O'Neil et nile"
    assert say("l'Neil", m) == "l'nile"
    assert say("O'Neil", m, "en") == "O'Neil"
    assert say("l'Neil", m, "en") == "l'Neil"


CASE = [
    # (entrée, texte, attendu)
    ("inria", "INRIA", "x"),
    ("inria", "Inria", "x"),
    ("inria", "inria", "x"),
    ("INRIA", "INRIA", "x"),
    ("INRIA", "Inria", "Inria"),
    ("INRIA", "inria", "inria"),
    ("Nguyen", "Nguyen", "x"),
    ("Nguyen", "nguyen", "nguyen"),
    ("Nguyen", "NGUYEN", "NGUYEN"),
    ("hcéres", "HCÉRES", "x"),
    ("hcéres", "Hcéres", "x"),
]


@pytest.mark.parametrize("entry, text, expected", CASE)
def test_casse(entry, text, expected):
    assert say(text, {entry: "x"}) == expected


def test_la_casse_exacte_l_emporte_sur_l_entree_insensible():
    m = {"edf": "bas", "EDF": "haut"}
    assert say("EDF edf Edf", m) == "haut bas bas"


EXPRESSIONS = [
    ("c.-à-d. ceci", {"c.-à-d.": "c'est-à-dire"}, "c'est-à-dire ceci"),
    ("Jean   Dupont est là", {"Jean Dupont": "jan dupon"}, "jan dupon est là"),
    ("Jean\nDupont", {"Jean Dupont": "jan dupon"}, "jan dupon"),
    ("Jean Dupont-Martin", {"Jean Dupont": "jan dupon"}, "jan dupon-Martin"),
    ("Jean Dupontel", {"Jean Dupont": "jan dupon"}, "Jean Dupontel"),
    ("Jean", {"Jean Dupont": "jan dupon"}, "Jean"),
    ("Saint-Jean-de-Luz", {"Saint-Jean-de-Luz": "sin jan de luz"}, "sin jan de luz"),
    ("c’est-à-dire", {"c'est-à-dire": "ceste a dire"}, "ceste a dire"),
    ("A.B.C.", {"A.B.C.": "a bé cé"}, "a bé cé"),
]


@pytest.mark.parametrize("text, mapping, expected", EXPRESSIONS)
def test_expressions(text, mapping, expected):
    assert say(text, mapping) == expected


def test_la_plus_longue_l_emporte():
    m = {"Jean": "jan", "Jean Dupont": "jan dupon", "Jean Dupont Martin": "jan dupon martin"}
    assert say("Jean, Jean Dupont, Jean Dupont Martin et Jean Dupont Durand", m) == (
        "jan, jan dupon, jan dupon martin et jan dupon Durand"
    )


def test_le_pluriel_n_est_pas_devine():
    assert say("des CDIs et un CDI", {"CDI": "cé dé i"}) == "des CDIs et un cé dé i"
    assert say("des CDIs", {"CDI": "cé dé i", "CDIs": "cé dé i"}) == "des cé dé i"


def test_le_dit_n_est_pas_retraite_par_les_entrees():
    # pas de récursion : le dit d'une entrée n'est pas lui-même remplacé
    assert say("A", {"A": "B", "B": "C"}) == "B"
    assert say("A B", {"A": "B", "B": "C"}) == "B C"


def test_lexique_vide():
    lex = Lexicon()
    assert not lex and len(lex) == 0
    assert lex.say("EDF") == "EDF"


def test_entrees_comptees():
    assert len(Lexicon({"EDF": "a", "edf ": "b", "Nguyen": "n", "vide": ""})) == 3  # « vide » ignoré


def test_performance_sur_un_livre():
    mapping = {f"MOT{i}": f"mot {i}" for i in range(500)} | {"EDF": "eu dé effe", "l'inria": "x"}
    text = ("Le rapport d'EDF et de la SNCF, selon M. Dupont, l'UE et le MOT42 aujourd'hui. " * 14000)
    lex = Lexicon(mapping)
    start = time.perf_counter()
    out = lex.say(text)
    assert time.perf_counter() - start < 5
    assert out.count("eu dé effe") == 14000 and out.count("mot 42") == 14000


# --------------------------------------------------------------------------- fusion livré / utilisateur

E = Entry


def test_l_utilisateur_l_emporte_sur_le_livre():
    shipped = [E("EDF", "eu dé effe"), E("UE", "u eu")]
    user = [E("EDF", "e d f")]
    assert merge(shipped, user, lang="fr") == {"EDF": "e d f", "UE": "u eu"}


def test_entree_vide_annule_le_livre():
    shipped = [E("EDF", "eu dé effe"), E("UE", "u eu")]
    user = [E("EDF", "")]
    assert merge(shipped, user, lang="fr") == {"UE": "u eu"}
    assert say("EDF et UE", merge(shipped, user, lang="fr")) == "EDF et u eu"


def test_annulation_inexistante_sans_effet():
    assert merge([E("UE", "u eu")], [E("XYZ", "")], lang="fr") == {"UE": "u eu"}


def test_cle_exacte_pour_l_annulation():
    # « edf » (insensible) n'annule pas « EDF » (sensible) : ce sont deux entrées distinctes
    assert merge([E("EDF", "x")], [E("edf", "")], lang="fr") == {"EDF": "x"}


def test_sections_de_langue_dans_la_fusion():
    entries, _ = parse("TOUS = t\n[fr]\nCHAT = chat\n[en]\nCHAT = cat\nCOW = cow\n")
    assert merge(entries, lang="fr") == {"TOUS": "t", "CHAT": "chat"}
    assert merge(entries, lang="en") == {"TOUS": "t", "CHAT": "cat", "COW": "cow"}


def test_la_langue_precise_l_emporte_sur_toutes_les_langues_dans_un_fichier():
    entries, _ = parse("[fr]\nX = fr\n[toutes]\nX = tous\n")
    assert merge(entries, lang="fr") == {"X": "fr"}


def test_normalisation_des_cles():
    assert merge([E("c’est  ça", "x")], [E("c'est ça", "y")], lang="fr") == {"c'est ça": "y"}


# --------------------------------------------------------------------------- source (livré + utilisateur)


def test_source_utilisateur_explicite(tmp_path):
    f = tmp_path / "dico.txt"
    f.write_text("Zorglub = zorglube\n[en]\nWord = ouerd\n", encoding="utf-8")
    fr = LexiconSource(user_path=f).load("fr")
    en = LexiconSource(user_path=f).load("en")
    assert fr.lexicon.say("Zorglub Word") == "zorglube Word"
    assert en.lexicon.say("Zorglub Word") == "zorglube ouerd"
    assert (fr.user_entries, fr.user_active, en.user_active) == (2, 1, 2)
    assert fr.user_path == f


def test_source_sans_dictionnaires(tmp_path):
    f = tmp_path / "dico.txt"
    f.write_text("Zorglub = zorglube\n", encoding="utf-8")
    loaded = LexiconSource(user_path=f, shipped=False, user=False).load("fr")
    assert not loaded.lexicon and loaded.user_path is None


def test_source_signale_les_lignes_invalides(tmp_path):
    f = tmp_path / "dico.txt"
    f.write_text("OK = ok\nn'importe quoi\n", encoding="utf-8")
    loaded = LexiconSource(user_path=f, shipped=False).load("fr")
    assert loaded.lexicon.say("OK") == "ok"
    (warning,) = loaded.warnings()
    assert "dico.txt" in warning and "ligne 2 ignorée" in warning


def test_source_par_defaut_cherche_a_cote_des_reglages(tmp_path, monkeypatch):
    from voxpage import settings

    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path / "app")
    monkeypatch.setattr(settings, "fallback_dir", lambda: tmp_path / "fb")
    (tmp_path / "fb").mkdir()
    (tmp_path / "fb" / "prononciations.txt").write_text("Zorglub = zorglube\n", encoding="utf-8")
    loaded = LexiconSource(shipped=False).load("fr")
    assert loaded.lexicon.say("Zorglub") == "zorglube"
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "prononciations.txt").write_text("Zorglub = autre\n", encoding="utf-8")
    assert LexiconSource(shipped=False).load("fr").lexicon.say("Zorglub") == "autre"


def test_chemin_d_ecriture_repli(tmp_path, monkeypatch):
    from voxpage import settings

    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path / "absent")  # inexistant : non inscriptible
    monkeypatch.setattr(settings, "fallback_dir", lambda: tmp_path / "fb")
    assert settings.pronunciations_path() == tmp_path / "fb" / "prononciations.txt"
    (tmp_path / "app").mkdir()
    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path / "app")
    assert settings.pronunciations_path() == tmp_path / "app" / "prononciations.txt"


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_dictionnaires_livres_valides(lang):
    from voxpage.normalize.lexicon import shipped_path

    entries, problems = read_entries(shipped_path(lang))
    assert problems == []
    assert all(e.spoken and e.written for e in entries)
    keys = [e.key for e in entries]
    assert len(keys) == len(set(keys)), "entrée en double dans le dictionnaire livré"
    assert len(shipped_entries(lang)) == len(entries)


# --------------------------------------------------------------------------- dans la normalisation


def doc(*blocks: Block, lang: str = "fr", title: str = "") -> Document:
    return Document("", None, lang, [Chapter(title, list(blocks))], [])


def lines(document: Document, mapping: dict[str, str] | None = None, lang: str = "fr") -> list[str]:
    lex = Lexicon(mapping, lang) if mapping is not None else None
    return [s.text for ch in normalize(document, NormalizeOptions(), lex) for s in ch.segments]


INTEGRATION = [
    # Le dit échappe à l'épellation des sigles
    ("Selon EDF, c'est vrai.", {"EDF": "eu dé effe"}, "Selon eu dé effe, c'est vrai."),
    ("Selon EDF, c'est vrai.", {}, "Selon E D F, c'est vrai."),
    ("Le sigle INRIA est connu.", {"INRIA": "inria"}, "Le sigle inria est connu."),
    ("La CGT et la CFDT.", {"CGT": "cé gé té"}, "La cé gé té et la C F D T."),
    # … à la casse
    ("Un prix de l'UE.", {"UE": "u eu"}, "Un prix de l'u eu."),
    # … aux nombres et aux abréviations
    ("Voir R2D2 et M. Dupont.", {"R2D2": "r deux d deux"}, "Voir r deux d deux et monsieur Dupont."),
    ("Il a 3 ans (cf. 12 p.)", {"3 ans": "trois années"}, "Il a trois années (confer 12 p.)"),
    ("Voir c.-à-d. la suite.", {"c.-à-d.": "c'est-à-dire"}, "Voir c'est-à-dire la suite."),
    ("Un Nguyen, un autre.", {"Nguyen": "nou-yène"}, "Un nou-yène, un autre."),
    ("Le site www.exemple.fr.", {"www.exemple.fr": "exemple point fr"}, "Le site exemple point fr."),
    # Abréviations de titre devant un nom du dictionnaire
    ("Selon M. Nguyen, oui.", {"Nguyen": "nou-yène"}, ["Selon monsieur nou-yène, oui."]),
    ("Le Dr Nguyen et Mme Nguyen.", {"Nguyen": "nou-yène"}, ["Le docteur nou-yène et madame nou-yène."]),
    # Début de phrase : la coupe en phrases ne change pas
    ("Il part. EDF reste.", {"EDF": "eu dé effe"}, ["Il part.", "eu dé effe reste."]),
    ("Il part. Nguyen reste.", {"Nguyen": "nou-yène"}, ["Il part.", "nou-yène reste."]),
    # Ne pas toucher
    ("La queue est bleue.", {"UE": "u eu", "ue": "x"}, "La queue est bleue."),
    ("La reine.", {"UE": "u eu", "reine": "rène"}, "La rène."),
    ("Texte sans entrée connue.", {"UE": "u eu"}, "Texte sans entrée connue."),
]


@pytest.mark.parametrize("text, mapping, expected", INTEGRATION)
def test_dans_normalize(text, mapping, expected):
    wanted = expected if isinstance(expected, list) else [expected]
    assert lines(doc(Block("paragraph", text)), mapping) == wanted


def test_normalize_sans_dictionnaire_inchange():
    d = doc(Block("paragraph", "Selon EDF, la CGT."))
    assert lines(d) == lines(d, {}) == ["Selon E D F, la C G T."]


def test_titre_en_capitales_et_dictionnaire():
    d = doc(Block("heading", "LE RAPPORT EDF", level=1))
    assert lines(d, {"EDF": "eu dé effe"}) == ["Le rapport eu dé effe"]


def test_titre_de_chapitre_annonce_avec_le_dictionnaire():
    d = doc(Block("paragraph", "Texte."), title="Les comptes d'EDF")
    assert lines(d, {"EDF": "eu dé effe"}) == ["Les comptes d'eu dé effe", "Texte."]


def test_tableau_liste_et_note():
    mapping = {"EDF": "eu dé effe"}
    table = doc(Block("table", "Société;Chiffre\nEDF;12"))
    assert any("eu dé effe : 12" in t or "eu dé effe" in t for t in lines(table, mapping))
    assert lines(doc(Block("list_item", "EDF et ses filiales")), mapping) == ["eu dé effe et ses filiales"]
    assert lines(doc(Block("footnote", "Source : EDF.")), mapping) == ["Note : Source : eu dé effe."]


def test_anglais():
    d = doc(Block("paragraph", "NASA and GCHQ."), lang="en")
    assert lines(d, {"GCHQ": "gee see aitch queue"}, "en") == ["NASA and gee see aitch queue."]


def test_plusieurs_occurrences_et_phrases_longues():
    text = " ".join(["EDF annonce une hausse, puis EDF revient sur sa décision"] * 40) + "."
    out = lines(doc(Block("paragraph", text)), {"EDF": "eu dé effe"})
    assert out and all("EDF" not in t for t in out)
    assert sum(t.count("eu dé effe") for t in out) == 80


def test_le_dit_ne_contient_aucun_repere():
    d = doc(Block("paragraph", "Voir EDF, UE, CGT, INRIA, HAL."))
    out = lines(d, {"EDF": "a", "UE": "b", "CGT": "c"})
    assert out == ["Voir a, b, c, INRIA, HAL."]
    assert all(ord(c) < 0x1D400 or ord(c) > 0x1D7FF for t in out for c in t)


# --------------------------------------------------------------------------- écriture du fichier

SAMPLE = """\
# Mon dictionnaire
# deuxième commentaire

EDF = eu dé effe
INRIA = inria

# anglais
[en]
GCHQ = gee see aitch queue
"""


def make(tmp_path, text=SAMPLE, newline="\n", bom=False):
    f = tmp_path / "p.txt"
    data = text.replace("\n", newline).encode("utf-8")
    f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return f


def test_ajout_conserve_commentaires_et_ordre(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    lf.add("UE", "u eu")
    lf.save()
    assert f.read_text(encoding="utf-8") == SAMPLE.replace("INRIA = inria\n", "INRIA = inria\nUE = u eu\n")


def test_ajout_dans_la_section_de_langue(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    lf.add("NSA", "en ess ay", "en")
    lf.add("SNCF", "esse enne cé effe", "fr")  # section absente : créée à la fin
    lf.save()
    text = f.read_text(encoding="utf-8")
    assert text.startswith(SAMPLE.replace("GCHQ = gee see aitch queue\n", ""))
    assert text.endswith("GCHQ = gee see aitch queue\nNSA = en ess ay\n\n[fr]\nSNCF = esse enne cé effe\n")
    entries = {(e.written, e.lang) for e in LexiconFile(f).entries}
    assert entries == {("EDF", ""), ("INRIA", ""), ("GCHQ", "en"), ("NSA", "en"), ("SNCF", "fr")}


def test_ajout_toutes_langues_avant_les_sections(tmp_path):
    f = make(tmp_path, "[fr]\nA1 = a\n")
    lf = LexiconFile(f)
    lf.add("Z9", "z", "")
    lf.save()
    assert f.read_text(encoding="utf-8") == "Z9 = z\n\n[fr]\nA1 = a\n"


def test_modification_en_place(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    edf = next(e for e in lf.entries if e.written == "EDF")
    lf.update(edf.line, "EDF", "e d f")
    lf.save()
    assert f.read_text(encoding="utf-8") == SAMPLE.replace("eu dé effe", "e d f")


def test_modification_de_langue_deplace_l_entree(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    edf = next(e for e in lf.entries if e.written == "EDF")
    lf.update(edf.line, "EDF", "eu dé effe", "en")
    lf.save()
    again = {(e.written, e.lang) for e in LexiconFile(f).entries}
    assert ("EDF", "en") in again and ("EDF", "") not in again
    assert f.read_text(encoding="utf-8").startswith("# Mon dictionnaire\n# deuxième commentaire\n")


def test_suppression(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    lf.remove(next(e for e in lf.entries if e.written == "INRIA").line)
    lf.save()
    assert f.read_text(encoding="utf-8") == SAMPLE.replace("INRIA = inria\n", "")


def test_les_lignes_invalides_sont_conservees_a_l_ecriture(tmp_path):
    f = make(tmp_path, "# c\nn'importe quoi\nA1 = a\n")
    lf = LexiconFile(f)
    assert len(lf.problems) == 1
    lf.add("B2", "b")
    lf.save()
    assert f.read_text(encoding="utf-8") == "# c\nn'importe quoi\nA1 = a\nB2 = b\n"


def test_fins_de_ligne_et_bom_conserves(tmp_path):
    f = make(tmp_path, newline="\r\n", bom=True)
    lf = LexiconFile(f)
    lf.add("UE", "u eu")
    lf.save()
    data = f.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    assert [e.written for e in LexiconFile(f).entries] == ["EDF", "INRIA", "UE", "GCHQ"]


def test_nouveau_fichier_avec_en_tete(tmp_path):
    f = tmp_path / "sous" / "dossier" / "p.txt"
    lf = LexiconFile(f)
    assert not lf.exists and lf.entries == []
    lf.add("EDF", "eu dé effe")
    lf.save()
    text = f.read_text(encoding="utf-8")
    assert text.startswith("# Dictionnaire de prononciation") and text.endswith("\nEDF = eu dé effe\n")
    assert [(e.written, e.spoken) for e in LexiconFile(f).entries] == [("EDF", "eu dé effe")]
    assert not list(f.parent.glob("*.tmp"))


def test_entree_vide_pour_annuler(tmp_path):
    f = make(tmp_path, "")
    lf = LexiconFile(f)
    lf.add("EDF", "")
    lf.save()
    assert "EDF =\n" in f.read_text(encoding="utf-8")
    assert [(e.written, e.spoken) for e in LexiconFile(f).entries] == [("EDF", "")]


@pytest.mark.parametrize(
    "written, spoken, fragment",
    [
        ("", "x", "Indiquez"),
        ("   ", "x", "Indiquez"),
        ("a=b", "x", "="),
        ("# note", "x", "#"),
        ("[fr]", "x", "section"),
        ("a\nb", "x", "une seule ligne"),
        ("a", "x\ny", "une seule ligne"),
    ],
)
def test_entrees_refusees(tmp_path, written, spoken, fragment):
    lf = LexiconFile(make(tmp_path))
    with pytest.raises(LexiconError, match=fragment):
        lf.add(written, spoken)


def test_doublon_refuse(tmp_path):
    lf = LexiconFile(make(tmp_path))
    with pytest.raises(LexiconError, match="existe déjà"):
        lf.add("EDF", "autre")
    lf.add("EDF", "autre", "fr")  # autre langue : permis
    with pytest.raises(LexiconError, match="existe déjà"):
        lf.add("EDF ", "encore", "fr")


def test_entree_disparue(tmp_path):
    lf = LexiconFile(make(tmp_path))
    with pytest.raises(LexiconError):
        lf.remove(99)
    with pytest.raises(LexiconError):
        lf.update(99, "A", "b")


def test_ecriture_atomique_et_relecture(tmp_path):
    f = make(tmp_path)
    lf = LexiconFile(f)
    lf.add("UE", "u eu")
    lf.save()
    other = LexiconFile(f)
    assert len(other.entries) == 4
    f.write_text("Z = z\n", encoding="utf-8")
    lf.reload()
    assert [e.written for e in lf.entries] == ["Z"]
