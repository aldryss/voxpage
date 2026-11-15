"""Sigles : ceux qui ne se prononcent pas comme un mot sont épelés (issue #12).

Les voix (eSpeak NG + Piper) écorchent les sigles : « ICF » devient « lick », « PIB » « pi B », « SNCF »
« sans sauf ». Mesure par aller-retour synthèse -> reconnaissance (docs/recette.md) : les lettres séparées
par une espace (« I C F ») sont dites correctement bien plus souvent que le sigle brut ou les noms de
lettres écrits (« i cé effe »).

Critère (prudent : en cas de doute, on épelle) pour un mot de 2 à 5 lettres majuscules, dans l'ordre :

1. sigle de la liste « toujours épelé » (CD, CV, USA…) : épelé ;
2. sigle de la liste « se lit comme un mot » (ONU, OTAN, UNESCO, INSEE, CNIL, SMIC, OVNI…) : laissé tel quel ;
3. chiffre romain valide (XIV, MCM…) : laissé tel quel (déjà géré, ou titre de section) ;
4. mot ordinaire en capitales (« NON », « STOP », « ATTENTION ») : laissé tel quel ;
5. forme d'un mot prononçable (au moins deux syllabes consonne + voyelle, quatre lettres ou plus,
   « NOTE », « SIDA ») : laissé tel quel ;
6. sinon : épelé.
"""

import re

from . import numbers

_CONS = "BCDFGHJKLMNPQRSTVWXZ"
_VOW = "AEIOUYÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ"
_UP = "A-ZÀ-ÖØ-Þ"

# Se lisent comme des mots (liste de sigles connus).
WORD_ACRONYMS = {
    "fr": set(
        """ONU OTAN UNESCO INSEE CNIL SMIC OVNI SIDA UNICEF NASA OPEP ENA ADEME ARCEP URSSAF AFNOR INSERM
        INRIA INRAE HAL CERN PACS SAMU SMUR COVID EHPAD ZEP CAC GIEC ORSEC BAC CAPES ASSEDIC UNEDIC MEDEF
        FNAC IKEA LEGO AIDS LASER RADAR SONAR OGM RIB TER ROM RAM ISBN ISSN DOM TOM COM CIEL CNED CLEMI
        FIFA UEFA OPA OPEP ONERA CNES ANSES ARS APL AAH SEPA SMUR URSAF GAFA GAFAM NATO OTAN""".split()
    ),
    "en": set(
        """NASA NATO UNESCO UNICEF OPEC FIFA UEFA AIDS LASER RADAR SCUBA NAFTA COVID ISBN ISSN SWAT GIF
        JPEG PIN HAL CERN ASAP""".split()
    ),
}
# Toujours épelés, même si la forme ressemble à un mot ou à un chiffre romain.
SPELLED = {"CD", "CV", "DC", "CM", "MC", "USA", "UE", "TER", "SAS", "UK", "EU", "OK", "TV", "DVD", "PDF"}
# Mots ordinaires qu'on trouve en capitales (titres, consignes) et qui ne sont pas des sigles.
COMMON = {
    "fr": set(
        """non oui stop note notes attention important avertissement danger exemple avis fin suite
        sommaire annexe annexes résumé préface index table notice mode emploi nouveau nouvelle gratuit
        urgent interdit obligatoire conseil rappel remarque définition conclusion introduction""".split()
    ),
    "en": set(
        """yes no stop note notes warning caution danger important example summary preface index
        table notice new free urgent forbidden required tip reminder remark definition conclusion
        introduction abstract contents appendix chapter part""".split()
    ),
}
# Sigles écrits en casse mixte, épelés (aucun critère général ne les distingue d'un mot).
MIXED_CASE_SPELLED = {"fr": {"Hcéres": "H C E R E S", "Hceres": "H C E R E S"}, "en": {}}

_WORDLIKE = re.compile(rf"^[{_CONS}]{{0,2}}[{_VOW}]+[{_CONS}]{{1,2}}(?:[{_VOW}]+[{_CONS}]{{0,2}})+$")
_TOKEN = re.compile(rf"(?<![\w])([{_UP}]{{2,5}})(?![\w])")
_DOTTED = re.compile(rf"(?<![\w.])((?:[{_UP}]\.){{2,6}})(?![\w])")


def wordlike(token: str) -> bool:
    """Forme d'un mot prononçable : au moins deux syllabes (consonnes + voyelles), quatre lettres ou plus."""
    return len(token) >= 4 and bool(_WORDLIKE.match(token))


def is_spelled(token: str, lang: str, common: set[str] | None = None) -> bool:
    """Ce mot en capitales est-il un sigle à épeler ?"""
    lang = "en" if lang == "en" else "fr"
    if token in SPELLED:
        return True
    if token in WORD_ACRONYMS[lang]:
        return False
    if numbers.roman_to_int(token) is not None:
        return False
    if token.lower() in COMMON[lang] or token.lower() in (common or ()):
        return False
    return not wordlike(token)


def spell(token: str) -> str:
    """Lettres séparées par une espace (« ICF » -> « I C F »), forme que les voix disent correctement."""
    return " ".join(token)


def spell_acronyms(text: str, lang: str, common: set[str] | None = None) -> str:
    """Épelle les sigles (voir le critère en tête de module) ; le reste du texte est inchangé."""
    lang_key = "en" if lang == "en" else "fr"
    for word, spelled in MIXED_CASE_SPELLED[lang_key].items():
        text = re.sub(rf"(?<![\w]){word}(?![\w])", spelled, text)
    text = _DOTTED.sub(lambda m: " ".join(m.group(1).replace(".", "")), text)

    def one(m: re.Match) -> str:
        return spell(m.group(1)) if is_spelled(m.group(1), lang, common) else m.group(0)

    return _TOKEN.sub(one, text)
