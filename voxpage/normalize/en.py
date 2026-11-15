"""Tables et règles propres à l'anglais."""

import re

LANG = "en"

NO_BREAK = {
    "mr", "mrs", "ms", "dr", "prof", "st", "vs", "e.g", "i.e", "no", "nos", "fig", "figs", "approx",
    "inc", "ltd", "co", "jr", "sr", "cf", "al", "p", "pp", "vol", "ch", "sec", "eq", "ed", "eds",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "gen", "col",
    "lt", "sgt", "capt", "rev", "hon", "ca", "est", "dept", "min", "max", "ref", "refs", "u.s", "u.k",
}
CAN_END = {"etc", "al", "approx"}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]

ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(p), r)
    for p, r in [
        (r"\be\.g\.", "for example"),
        (r"\bi\.e\.", "that is"),
        (r"\bMr\.(?=\s+[A-Z])", "mister"),
        (r"\bMrs\.(?=\s+[A-Z])", "missus"),
        (r"\bDr\.?(?=\s+[A-Z])", "doctor"),
        (r"\bProf\.(?=\s+[A-Z])", "professor"),
        (r"\bcf\.", "compare"),
        (r"\bNo\.\s?(?=\d)", "number "),
        (r"\bno\.\s?(?=\d)", "number "),
        (r"\bNos\.\s?(?=\d)", "numbers "),
        (r"§§\s?", "sections "),
        (r"§\s?", "section "),
        (r"\bpp\.\s?(?=\d)", "pages "),
        (r"\bp\.\s?(?=\d)", "page "),
        (r"\bFigs?\.\s?(?=\d)", "figure "),
        (r"\bfigs?\.\s?(?=\d)", "figure "),
        (r"\bvs\.", "versus"),
        (r"\bVol\.\s?(?=\d|[IVX]{2,}\b)", "Volume "),
        (r"\bet al\.", "et al"),
        (r"\bN\.B\.", "nota bene"),
    ]
]

ETC = "et cetera"

SYMBOLS: list[tuple[re.Pattern, str]] = [
    (re.compile(p), r)
    for p, r in [
        (r"(?<=\s)&(?=\s)", "and"),
        (r"(?<=\s)\+(?=\s)", "plus"),
        (r"(?<![\w+])\+(?=\d)", "plus "),
        (r"(?<=\s)=(?=\s)", "equals"),
        (r"(?<=\s)×(?=\s)", "times"),
        (r"(?<=\d)×(?=\d)", " times "),
        (r"\s?≥\s?", " greater than or equal to "),
        (r"\s?≤\s?", " less than or equal to "),
        (r"\s?≠\s?", " not equal to "),
        (r"\s?≈\s?", " approximately equal to "),
        (r"\s?±\s?", " plus or minus "),
        (r"(?<=\s)÷(?=\s)", "divided by"),
        (r"(?<=\s)−(?=\s)", "minus"),
        (r"(?<=\s)>(?=\s)", "greater than"),
        (r"(?<=\s)<(?=\s)", "less than"),
        (r"\s?→\s?", " arrow "),
        (r"\s?←\s?", " left arrow "),
        (r"\s?↔\s?", " double arrow "),
        (r"\s?[☎☏✆📞]\s?", " telephone "),
        (r"\s?[✉📧]\ufe0f?\s?", " mail "),
        (r"\s?[⚠⛔]\ufe0f?\s?", " warning "),
        (r"\s?[✓✔☑✅]\ufe0f?\s?", " checked "),
        (r"\s?[✗✘✕✖☒❌]\ufe0f?\s?", " cross "),
        (r"\s?[★⭐]\s?", " star "),
        (r"\s?[►▶▸➤➢]\s?", " arrow "),
        (r"©\s?", "copyright "),
        (r"®", " registered trademark"),
        (r"™", " trademark"),
        (r"∞", "infinity"),
        (r"‰", " per mille"),
        (r"(?<![\w])%", "percent"),
        (r"€", "euros"),
    ]
]

PERCENT = "percent"
POINT = "point"
AT = "at"
URL_SEP = {
    ".": "dot", "/": "slash", "-": "dash", "_": "underscore", "?": "question mark", "=": "equals",
    "&": "ampersand", "#": "hash", "~": "tilde", ":": "colon", "@": "at", "+": "plus", "%": "percent",
}
URL_WWW = "w w w"

UNITS: dict[str, tuple[str, str]] = {
    "km/h": ("kilometer per hour", "kilometers per hour"),
    "mph": ("mile per hour", "miles per hour"),
    "m/s": ("meter per second", "meters per second"),
    "km²": ("square kilometer", "square kilometers"),
    "m²": ("square meter", "square meters"),
    "cm²": ("square centimeter", "square centimeters"),
    "m³": ("cubic meter", "cubic meters"),
    "km": ("kilometer", "kilometers"),
    "cm": ("centimeter", "centimeters"),
    "mm": ("millimeter", "millimeters"),
    "kg": ("kilogram", "kilograms"),
    "mg": ("milligram", "milligrams"),
    "lbs": ("pound", "pounds"),
    "lb": ("pound", "pounds"),
    "oz": ("ounce", "ounces"),
    "ft": ("foot", "feet"),
    "ml": ("milliliter", "milliliters"),
    "ms": ("millisecond", "milliseconds"),
    "KB": ("kilobyte", "kilobytes"),
    "MB": ("megabyte", "megabytes"),
    "GB": ("gigabyte", "gigabytes"),
    "TB": ("terabyte", "terabytes"),
    "Hz": ("hertz", "hertz"),
    "kHz": ("kilohertz", "kilohertz"),
    "MHz": ("megahertz", "megahertz"),
    "GHz": ("gigahertz", "gigahertz"),
    "kW": ("kilowatt", "kilowatts"),
    "kWh": ("kilowatt hour", "kilowatt hours"),
    "dB": ("decibel", "decibels"),
}
DEGREES = ("degree", "degrees")
CELSIUS = "Celsius"
FAHRENHEIT = "Fahrenheit"

CURRENCIES = {
    "€": ("euro", "euros"),
    "$": ("dollar", "dollars"),
    "£": ("pound", "pounds"),
    "¥": ("yen", "yen"),
}

RANGE_AFTER = (
    r"years?|days?|months?|weeks?|hours?|minutes?|seconds?|times|people|pages?|euros?|dollars?|"
    r"kilometers?|miles?|meters?|students?|participants?|%|percent|degrees?"
)
RANGE_BEFORE = r"pages?|chapters?|lines?|paragraphs?|verses?|articles?|figures?|volumes?|sections?"
RANGE_WORD = "to"

FRACTIONS = {
    (1, 2): ("one half", "one half"),
    (1, 3): ("one third", "one third"),
    (2, 3): ("two thirds", "two thirds"),
    (1, 4): ("one quarter", "one quarter"),
    (3, 4): ("three quarters", "three quarters"),
}
FRACTION_CHARS = {"½": "one half", "⅓": "one third", "⅔": "two thirds", "¼": "one quarter",
                  "¾": "three quarters"}
FRACTION_AFTER = (
    r"(?=\s(?:of|a|an|the|cups?|teaspoons?|tablespoons?|inch|inches|miles?|hours?)\b)"
)
FRACTION_BEFORE = r"(?:\b(?:the|about|nearly|almost|over|under|only)\s)"

ROMAN_KEYWORDS = r"chapter|volume|part|book|act|scene|section|appendix|article|title|plate"
ROMAN_ORDINAL_KEYWORDS = r"century|millennium|dynasty|Reich|Republic|Empire"
KING_NAMES = (
    "Henry|Louis|Charles|Edward|George|Richard|William|Elizabeth|James|John|Pope|Pius|Leo|Benedict|"
    "Gregory|Clement|Innocent|Urban|Napoleon|Philip|Frederick|Alexander|Nicholas|Peter|Paul|Albert|"
    "Ferdinand|Francis|Ramses|Ramesses|Thutmose|Ptolemy|Alfonso|Victor|Boniface|Stephen|Michael"
)

SHORT_WORDS = set("""
a an and are as at be but by can did do for get got had has her him his how if in is it its let may
me my new no not now of off old on one or our out own say see she so the to too two up us use was way
we who why yes yet you all any end war man men day days life love time year years home book work
world word words part page note part from with that this they them then than what when will your
been were have into over also only some such more most much many each both just like make made
said says very well even back down city king land last long look need part past rest side stop
""".split())
