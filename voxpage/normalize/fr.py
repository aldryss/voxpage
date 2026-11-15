"""Tables et règles propres au français."""

import re

LANG = "fr"

# Abréviations après lesquelles un point n'termine PAS la phrase (comparées en minuscules, sans point).
NO_BREAK = {
    "m", "mm", "mme", "mmes", "mlle", "mlles", "dr", "drs", "pr", "prof", "me", "mgr", "st", "ste",
    "cf", "art", "arts", "al", "p", "pp", "vol", "tel", "tél", "ch", "chap", "fig", "éd", "éds",
    "env", "ex", "av", "apr", "vs", "cie", "sté", "bd", "fbg", "p.ex", "c.-à-d", "i.e", "e.g",
    "no", "nos", "ibid", "op", "cit", "col", "sq", "sqq", "suiv",
    "approx", "max", "min", "réf", "ref", "janv", "févr", "avr", "juill", "sept", "oct", "nov", "déc",
    "lt", "gén", "cdt", "hon", "illust", "trad", "dir", "coll", "t", "tt", "r", "fasc",
}
# Abréviations qui peuvent terminer une phrase.
CAN_END = {"etc", "j.-c", "sq", "sqq", "suiv", "cit", "env", "ibid"}

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
          "octobre", "novembre", "décembre"]

# (motif, remplacement) appliqués dans l'ordre sur chaque phrase.
ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, flags), r)
    for p, r, flags in [
        (r"\bav\.\s?J\.?-?C\.?", "avant Jésus-Christ", 0),
        (r"\bapr\.\s?J\.?-?C\.?", "après Jésus-Christ", 0),
        (r"\bJ\.-C\.", "Jésus-Christ", 0),
        (r"\bp\.\s?ex\.", "par exemple", 0),
        (r"\bc\.-à-d\.", "c'est-à-dire", 0),
        (r"\bi\.e\.", "c'est-à-dire", 0),
        (r"\be\.g\.", "par exemple", 0),
        (r"\bN\.B\.", "nota bene", 0),
        (r"\bMM\.(?=\s+[A-ZÀ-ÖØ-Þ])", "messieurs", 0),
        (r"\bM\.(?=\s+[A-ZÀ-ÖØ-Þ])", "monsieur", 0),
        (r"\bMmes\b\.?", "mesdames", 0),
        (r"\bMme\b\.?", "madame", 0),
        (r"\bMlles\b\.?", "mesdemoiselles", 0),
        (r"\bMlle\b\.?", "mademoiselle", 0),
        (r"\bDrs\.(?=\s+[A-ZÀ-ÖØ-Þ])", "docteurs", 0),
        (r"\bDr\.?(?=\s+[A-ZÀ-ÖØ-Þ])", "docteur", 0),
        (r"\bPr\.(?=\s+[A-ZÀ-ÖØ-Þ])", "professeur", 0),
        (r"\bProf\.(?=\s+[A-ZÀ-ÖØ-Þ])", "professeur", 0),
        (r"\bcf\.", "confer", 0),
        (r"\bcf\b(?=\s)", "confer", 0),
        (r"\bN[°º]\s?(?=\d)", "Numéro ", 0),
        (r"\bn[°º]s\s?(?=\d)", "numéros ", 0),
        (r"\bn[°º]\s?(?=\d)", "numéro ", 0),
        (r"\bN[°º](?=\s)", "Numéro", 0),
        (r"\bn[°º](?=\s)", "numéro", 0),
        (r"§§\s?", "paragraphes ", 0),
        (r"§\s?", "paragraphe ", 0),
        (r"\bpp\.\s?(?=\d)", "pages ", 0),
        (r"\bp\.\s?(?=\d)", "page ", 0),
        (r"\barts\.\s?(?=\d)", "articles ", 0),
        (r"\bart\.\s?(?=\d)", "article ", 0),
        (r"\bal\.\s?(?=\d)", "alinéa ", 0),
        (r"\bchap\.\s?(?=\d|[IVX]+\b)", "chapitre ", 0),
        (r"\bfig\.\s?(?=\d)", "figure ", 0),
        (r"\bvol\.\s?(?=\d|[IVX]+\b)", "volume ", 0),
        (r"\bt\.\s?(?=\d|[IVX]+\b)", "tome ", 0),
        (r"\b[Tt]él\.\s?(?=[:\d+(])", "téléphone ", 0),
        (r"\bet al\.", "et alii", 0),
    ]
]

# Fin de phrase : « etc. » seul est traité à part (voir text.py).
ETC = "et cetera"

SYMBOLS: list[tuple[re.Pattern, str]] = [
    (re.compile(p), r)
    for p, r in [
        (r"(?<=\s)&(?=\s)", "et"),
        (r"(?<=\s)\+(?=\s)", "plus"),
        (r"(?<![\w+])\+(?=\d)", "plus "),
        (r"(?<![\w+\-−.,/])[-−](?=\d)", "moins "),
        (r"(?<=\s)=(?=\s)", "égale"),
        (r"(?<=\s)×(?=\s)", "fois"),
        (r"(?<=\d)×(?=\d)", " fois "),
        (r"\s?≥\s?", " supérieur ou égal à "),
        (r"\s?≤\s?", " inférieur ou égal à "),
        (r"\s?≠\s?", " différent de "),
        (r"\s?≈\s?", " environ égal à "),
        (r"\s?±\s?", " plus ou moins "),
        (r"(?<=\s)÷(?=\s)", "divisé par"),
        (r"(?<=\s)−(?=\s)", "moins"),
        (r"(?<=\s)>(?=\s)", "supérieur à"),
        (r"(?<=\s)<(?=\s)", "inférieur à"),
        (r"\s?→\s?", " flèche "),
        (r"\s?←\s?", " flèche gauche "),
        (r"\s?↔\s?", " flèche double "),
        (r"©\s?", "copyright "),
        (r"®", " marque déposée"),
        (r"™", " marque commerciale"),
        (r"∞", "infini"),
        (r"‰", " pour mille"),
        (r"(?<![\w])%", "pour cent"),
        (r"€", "euros"),
    ]
]

PERCENT = "pour cent"
POINT = "point"
AT = "arobase"
URL_SEP = {
    ".": "point", "/": "slash", "-": "tiret", "_": "tiret bas", "?": "point d'interrogation",
    "=": "égale", "&": "et commercial", "#": "dièse", "~": "tilde", ":": "deux points",
    "@": "arobase", "+": "plus", "%": "pour cent",
}
URL_WWW = "w w w"

# symbole -> (singulier, pluriel)
UNITS: dict[str, tuple[str, str]] = {
    "km/h": ("kilomètre par heure", "kilomètres par heure"),
    "m/s": ("mètre par seconde", "mètres par seconde"),
    "tr/min": ("tour par minute", "tours par minute"),
    "km²": ("kilomètre carré", "kilomètres carrés"),
    "m²": ("mètre carré", "mètres carrés"),
    "cm²": ("centimètre carré", "centimètres carrés"),
    "mm²": ("millimètre carré", "millimètres carrés"),
    "m³": ("mètre cube", "mètres cubes"),
    "cm³": ("centimètre cube", "centimètres cubes"),
    "km": ("kilomètre", "kilomètres"),
    "cm": ("centimètre", "centimètres"),
    "mm": ("millimètre", "millimètres"),
    "µm": ("micromètre", "micromètres"),
    "m": ("mètre", "mètres"),
    "kg": ("kilogramme", "kilogrammes"),
    "mg": ("milligramme", "milligrammes"),
    "g": ("gramme", "grammes"),
    "ml": ("millilitre", "millilitres"),
    "cl": ("centilitre", "centilitres"),
    "dl": ("décilitre", "décilitres"),
    "L": ("litre", "litres"),
    "l": ("litre", "litres"),
    "ha": ("hectare", "hectares"),
    "ms": ("milliseconde", "millisecondes"),
    "min": ("minute", "minutes"),
    "Ko": ("kilooctet", "kilooctets"),
    "Mo": ("mégaoctet", "mégaoctets"),
    "Go": ("gigaoctet", "gigaoctets"),
    "To": ("téraoctet", "téraoctets"),
    "Hz": ("hertz", "hertz"),
    "kHz": ("kilohertz", "kilohertz"),
    "MHz": ("mégahertz", "mégahertz"),
    "GHz": ("gigahertz", "gigahertz"),
    "W": ("watt", "watts"),
    "kW": ("kilowatt", "kilowatts"),
    "kWh": ("kilowattheure", "kilowattheures"),
    "dB": ("décibel", "décibels"),
}
DEGREES = ("degré", "degrés")
CELSIUS = "Celsius"
FAHRENHEIT = "Fahrenheit"

CURRENCIES = {  # symbole -> (singulier, pluriel)
    "€": ("euro", "euros"),
    "$": ("dollar", "dollars"),
    "£": ("livre sterling", "livres sterling"),
    "¥": ("yen", "yen"),
}
CURRENCY_BIG = {"k€": ("mille euros",), "M€": ("million d'euros", "millions d'euros"),
                "Md€": ("milliard d'euros", "milliards d'euros")}

HOUR = ("heure", "heures")

# Mots qui, après « 10-15 », rendent la plage sûre ; et mots qui, avant, la rendent sûre.
RANGE_AFTER = (
    r"ans?|jours?|mois|semaines?|heures?|minutes?|secondes?|fois|personnes?|pages?|euros?|"
    r"kilomètres?|mètres?|élèves?|participants?|%|pour cent|ème|degrés?"
)
RANGE_BEFORE = r"pages?|chapitres?|lignes?|paragraphes?|versets?|articles?|figures?|tomes?|volumes?"
RANGE_WORD = "à"

# Fractions écrites en ASCII : contexte exigé pour les lire.
FRACTIONS = {
    (1, 2): ("un demi", "la moitié"),
    (1, 3): ("un tiers", "un tiers"),
    (2, 3): ("deux tiers", "deux tiers"),
    (1, 4): ("un quart", "un quart"),
    (3, 4): ("trois quarts", "trois quarts"),
}
FRACTION_CHARS = {"½": "un demi", "⅓": "un tiers", "⅔": "deux tiers", "¼": "un quart", "¾": "trois quarts"}
FRACTION_AFTER = r"(?=\s(?:de|des|du)\b|\sd['’])"
FRACTION_BEFORE = r"(?:\b(?:les|la|environ|près de|presque|plus de|moins de|les|aux)\s)"

ROMAN_KEYWORDS = (
    r"chapitre|tome|livre|partie|acte|scène|volume|section|annexe|article|titre|planche|"
    r"volume|livre|fascicule"
)
ROMAN_ORDINAL_KEYWORDS = (
    r"siècles?|millénaires?|arrondissement|République|Internationale|dynastie|Dynastie|Reich|"
    r"Armée|Symphonie|Empire|Légion"
)
KING_NAMES = (
    "Louis|Charles|Henri|Philippe|François|Jean|Jean-Paul|Pie|Benoît|Clément|Grégoire|Léon|Urbain|"
    "Innocent|Napoléon|Édouard|Richard|Guillaume|Alexandre|Nicolas|Pierre|Paul|Boniface|Albert|Léopold|"
    "Baudouin|Jacques|Ramsès|Frédéric|Georges|Henry|Élisabeth|Elisabeth|Étienne|Jules|Sixte|Pépin|Robert|"
    "Hugues|Lothaire|Clovis|Childéric|Dagobert|Thutmôsis|Amenhotep|Ptolémée|Séleucos|Ferdinand|Philippe-Auguste"
)

# Mots courts (<= 4 lettres) qui sont de vrais mots et non des sigles, pour les textes TOUT EN MAJUSCULES.
SHORT_WORDS = set("""
a à ai as au aux ça ce ces cet ci car ceux chez dans de des du donc dont elle en es est et eux fut
il ils je la là le les leur lui ma mais me mes moi mon ne ni nos nous on ont or ou où par pas peu plus
pour que qui quoi sa sans se ses si son sont sur ta te tes toi ton tous tout très tu un une vers vos
vous y été être avec ainsi alors après aussi avant bien cela cette ceci deux dix fois fin huit lieu
loin même mois neuf nul pays sept sous trois tel tels vers voir
roi loi vie mer sol feu eau air mur nuit jour jeux jeu vue ère art âge âme bois cas cœur coup cour dos
don doit dit dire fait faut mort mots mot rue paix pain vin lit nom noms nord sud est ouest ville
villa rois lois vies mers monde terre ciel dieu homme femme fils fille père mère frère sœur enfant
amour guerre temps jours nuits an ans année siècle livre livres page pages texte lettre lettres
chap tome tomes part acte actes idée idées droit droits état États mal bon bons bonne bonnes beau
belle vrai vraie vrais grand grande petit petite haut haute bas basse long longue vieux vieil
neuve neuf nouveau nouvelle jeune jeunes seul seule autre autres tant très trop peut peux veut
doit dois fait faire dire mieux moins plus pire gens chef cher chère clé clef don feu fer fil fin
fou fous gaz jus lac lui mal mur nez œil œuf ours pas pic pie pis pli pot pré prix puits quai
raie rat rêve riz roc rôle sac sang sens seuil sol son sort sou soi sucre sur tas thé toit ton
tour trou type ton tue val vent ver vert verre vide vol voie voix vœu zèle zéro
""".split())

