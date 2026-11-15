"""Génère le corpus de PDF de test et le texte attendu.

    ./dev python tests/corpus/build.py

Les PDF produits (déterministes : `invariant=1`) et les fichiers `*.expected.json` sont versionnés : les
tests n'ont pas besoin de reportlab. Chaque fichier attendu contient une liste de cas
`{"options": {...}, "document": {...}}` ou `{"options": {...}, "error": "fragment du message"}`.

Dans les textes sources, « | » marque une coupure de mot autorisée (césure avec trait d'union si le mot
ne tient pas en fin de ligne) ; il disparaît du texte attendu.
"""

import io
import json
import os
from pathlib import Path

import reportlab
from PIL import Image
from reportlab.lib.colors import black, whitesmoke
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

HERE = Path(__file__).parent
W, H = A4
FONTS = Path(reportlab.__file__).parent / "fonts"
for name, file in (
    ("Vera", "Vera.ttf"),
    ("VeraBd", "VeraBd.ttf"),
    ("VeraIt", "VeraIt.ttf"),
    ("VeraBI", "VeraBI.ttf"),
):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))

R, B, IT = "Vera", "VeraBd", "VeraIt"


def new_canvas(name: str, title: str | None = None, author: str | None = None, **kw) -> canvas.Canvas:
    c = canvas.Canvas(str(HERE / name), pagesize=A4, invariant=1, **kw)
    c.setTitle(title or "")
    c.setAuthor(author or "")
    c.setCreator("voxpage tests/corpus/build.py")
    return c


def sw(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def plain(text: str) -> str:
    return text.replace("|", "")


# ---------------------------------------------------------------------------------------------------------
# Mise en page minimale


def wrap(text: str, font: str, size: float, widths) -> list[tuple[str, bool]]:
    """Coupe `text` en lignes ; `widths(i)` donne la largeur de la ligne i. Renvoie (ligne, dernière ?)."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    i = 0
    while words:
        word = words[0]
        cand = (cur + " " + plain(word)) if cur else plain(word)
        if sw(cand, font, size) <= widths(len(lines)):
            cur = cand
            words.pop(0)
            continue
        # césure autorisée ?
        parts = word.split("|")
        done = False
        for k in range(len(parts) - 1, 0, -1):
            head = "".join(parts[:k]) + "-"
            cand = (cur + " " + head) if cur else head
            if sw(cand, font, size) <= widths(len(lines)):
                lines.append(cand)
                words[0] = "|".join(parts[k:])
                cur = ""
                done = True
                break
        if done:
            continue
        if not cur:
            cur = plain(word)
            words.pop(0)
        lines.append(cur)
        cur = ""
        i += 1
    if cur:
        lines.append(cur)
    return [(ln, k == len(lines) - 1) for k, ln in enumerate(lines)]


def draw_line(c, x, y, text, font, size, width=None, justify=False, words_mode=False):
    assert width is None or sw(text, font, size) <= width + 0.01, f"ligne trop longue : {text!r}"
    c.setFont(font, size)
    if not words_mode and not justify:
        c.drawString(x, y, text)
        return
    words = text.split(" ")
    total = sum(sw(w, font, size) for w in words)
    if justify and len(words) > 1 and width:
        gap = (width - total) / (len(words) - 1)
    else:
        gap = sw(" ", font, size)
    pos = x
    for w in words:
        c.drawString(pos, y, w)
        pos += sw(w, font, size) + gap


class Flow:
    """Coule des paragraphes dans une suite de cadres (x, haut, largeur, bas, page)."""

    def __init__(
        self,
        c,
        frames,
        font=R,
        size=11,
        leading=14,
        indent=0.0,
        par_space=0.0,
        justify=False,
        words_mode=False,
    ):
        self.c = c
        self.frames = frames
        self.font, self.size, self.leading = font, size, leading
        self.indent, self.par_space = indent, par_space
        self.justify, self.words_mode = justify, words_mode
        self.fi = 0
        self.y = frames[0][1] - size
        self.page = frames[0][4]

    def _next_frame(self):
        self.fi += 1
        x, top, width, bottom, page = self.frames[self.fi]
        while self.page < page:
            self.c.showPage()
            self.page += 1
        self.y = top - self.size

    def paragraph(self, text, indent=None, font=None, size=None, leading=None, first=False):
        font = font or self.font
        size = size or self.size
        leading = leading or self.leading
        indent = self.indent if indent is None else indent
        if not first:
            self.y -= self.par_space
        x0, _top, width, bottom, _page = self.frames[self.fi]
        state = {"n": 0}

        def widths(i):
            return self.frames[self.fi][2] - (indent if i == 0 else 0)

        lines = wrap(text, font, size, widths)
        for k, (ln, last) in enumerate(lines):
            if self.y < self.frames[self.fi][3]:
                self._next_frame()
            x0, _top, width, bottom, _page = self.frames[self.fi]
            x = x0 + (indent if k == 0 else 0)
            w = width - (indent if k == 0 else 0)
            draw_line(self.c, x, self.y, ln, font, size, w, self.justify and not last, self.words_mode)
            self.y -= leading
            state["n"] += 1

    def skip(self, amount):
        self.y -= amount


def balanced_bottom(paragraphs, k, top, width, font, size, leading, indent):
    """Bas des cadres pour répartir `paragraphs` sur `k` colonnes de hauteur égale."""
    n = 0
    for j, p in enumerate(paragraphs):
        ind = 0 if j == 0 else indent
        n += len(wrap(p, font, size, lambda i, ind=ind: width - (ind if i == 0 else 0)))
    per = -(-n // k)
    return top - size - (per - 1) * leading - 1


def write_expected(name: str, cases: list[dict]) -> None:
    path = HERE / f"{name}.expected.json"
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def doc(title, author, lang, chapters, warnings=()):
    return {
        "title": title,
        "author": author,
        "lang": lang,
        "chapters": [{"title": t, "blocks": [list(b) for b in blocks]} for t, blocks in chapters],
        "warnings": list(warnings),
    }


def P(text):
    return ["paragraph", 0, plain(text)]


def Hd(text, level):
    return ["heading", level, text]


def Li(text):
    return ["list_item", 0, text]


# ---------------------------------------------------------------------------------------------------------
# 1. Une colonne simple

SIMPLE = [
    "Le phare de Kerbrat se dresse à la pointe d’un cap battu par les vents. Depuis plus d’un siècle, "
    "il guide les bateaux de pêche qui rentrent au port à la nuit tombée, et les anciens du village "
    "racontent encore les tempêtes où sa lumière fut le seul repère des marins.",
    "Le gardien, Yves Le Goff, monte chaque soir les cent douze marches de l’escalier en colimaçon. "
    "Il vérifie la lampe, nettoie la lentille et note dans un grand cahier l’état du ciel et de la "
    "mer. «\u00a0Un phare, dit-il, c’est une promesse faite à ceux qu’on ne verra jamais.\u00a0»",
    "Aujourd’hui, la lumière est automatisée, mais le cahier continue d’être tenu, par habitude et "
    "par fidélité.",
]


def build_simple():
    c = new_canvas("simple.pdf", "Le phare de Kerbrat", "Anne Morvan")
    c.setFont(B, 18)
    c.drawString(72, H - 90, "Le phare de Kerbrat")
    f = Flow(c, [(72, H - 120, 451, 72, 1)], size=11, leading=15, indent=16)
    for k, p in enumerate(SIMPLE):
        f.paragraph(p, indent=0 if k == 0 else None, first=k == 0)
    c.showPage()
    c.save()
    blocks = [Hd("Le phare de Kerbrat", 1)] + [P(p.replace("\u00a0", " ")) for p in SIMPLE]
    write_expected(
        "simple",
        [{"options": {}, "document": doc("Le phare de Kerbrat", "Anne Morvan", "fr", [("", blocks)])}],
    )


# ---------------------------------------------------------------------------------------------------------
# 2. Colonnes : titre pleine largeur, deux colonnes, puis trois colonnes et un encadré

COL_TITLE = "La lecture à voix haute"
COL_LEAD = (
    "Lire à voix haute est une pratique ancienne qui retrouve aujourd’hui une place nouvelle, grâce aux "
    "livres audio et aux outils de synthèse vocale. Ce dossier en retrace l’histoire et en présente les "
    "usages actuels, en particulier pour les personnes malvoyantes."
)
COL_2 = [
    "Dans l’Antiquité, la lecture silencieuse était rare : on lisait en prononçant les mots, seul ou "
    "devant un auditoire. Les copistes eux-mêmes murmuraient les textes qu’ils recopiaient, et les "
    "bibliothèques étaient des lieux bruyants où chacun suivait sa propre lecture.",
    "Au Moyen Âge, les monastères organisaient des lectures pendant les repas. Un moine lisait un texte "
    "édifiant tandis que les autres mangeaient en silence. Cette tradition a laissé des traces dans la "
    "manière dont les textes étaient ponctués, pour guider la respiration du lecteur et l’intonation "
    "des phrases les plus longues, que l’on découpait en segments faciles à dire.",
    "Avec l’imprimerie, la lecture devient progressivement une activité privée. Pourtant, la lecture "
    "collective ne disparaît pas : dans les ateliers, les cafés ou les veillées, un lecteur partage le "
    "journal ou le roman du moment avec ceux qui ne savent pas lire, ou qui préfèrent écouter.",
    "Aujourd’hui, la synthèse vocale permet à chacun d’écouter n’importe quel texte. Sa qualité dépend "
    "toutefois de la fidélité de la transcrip|tion : un en-tête lu au milieu d’une phrase ou une note "
    "mal placée suffit à rendre un passage incompréhensible.",
]
COL_H2 = "Deuxième partie"
COL_3 = [
    "Les premiers appareils de lecture automatique datent des années soixante-dix. Ils étaient lourds, "
    "coûteux et réservés à quelques bibliothèques spécialisées, mais ils ont ouvert la voie aux outils "
    "que nous connaissons.",
    "Les voix de synthèse ont longtemps paru mécaniques. Les progrès récents les rendent plus naturelles, "
    "au point qu’il devient possible d’écouter un roman entier sans fatigue, à condition que le texte "
    "lu soit propre.",
    "La préparation du texte reste donc essentielle : ordre de lecture, suppression des éléments "
    "répétés, recollage des mots coupés en fin de ligne et traitement des notes sont autant d’étapes "
    "indispensables pour obtenir une écoute agréable.",
]
COL_BOX_TITLE = "À retenir"
COL_BOX = (
    "Un texte bien préparé se lit dans l’ordre voulu par l’auteur, sans numéros de page ni en-têtes, "
    "et sans mots coupés."
)


def build_colonnes():
    c = new_canvas("colonnes.pdf", "La lecture à voix haute", "Collectif")
    c.setFont(B, 20)
    c.drawString(60, H - 80, COL_TITLE)
    lead = Flow(c, [(60, H - 105, 475, 60, 1)], font=IT, size=12, leading=16)
    lead.paragraph(COL_LEAD, first=True)
    top = lead.y - 10
    gutter, cw = 21, (475 - 21) / 2
    bottom = balanced_bottom(COL_2, 2, top, cw, R, 10, 13, 12)
    frames = [(60, top, cw, bottom, 1), (60 + cw + gutter, top, cw, bottom, 1)]
    f = Flow(c, frames, size=10, leading=13, indent=12, justify=True, words_mode=True)
    for k, p in enumerate(COL_2):
        f.paragraph(p, indent=0 if k == 0 else None, first=k == 0)
    c.showPage()
    c.setFont(B, 16)
    c.drawString(60, H - 80, COL_H2)
    gutter, cw = 15, (475 - 30) / 3
    bottom = balanced_bottom(COL_3, 3, H - 100, cw, R, 10, 13, 10)
    frames = [(60 + k * (cw + gutter), H - 100, cw, bottom, 1) for k in range(3)]
    f = Flow(c, frames, size=10, leading=13, indent=10, justify=True, words_mode=False)
    for k, p in enumerate(COL_3):
        f.paragraph(p, indent=0 if k == 0 else None, first=k == 0)
    # encadré
    c.setLineWidth(0.8)
    c.rect(60, 90, 475, 110, stroke=1, fill=0)
    c.setFont(B, 10)
    c.drawString(72, 180, COL_BOX_TITLE)
    box = Flow(c, [(72, 170, 451, 95, 1)], size=10, leading=13)
    box.paragraph(COL_BOX, first=True)
    c.showPage()
    c.save()
    blocks = (
        [Hd(COL_TITLE, 1), P(COL_LEAD)]
        + [P(p) for p in COL_2]
        + [Hd(COL_H2, 2)]
        + [P(p) for p in COL_3]
        + [Hd(COL_BOX_TITLE, 3), P(COL_BOX)]
    )
    write_expected(
        "colonnes", [{"options": {}, "document": doc(COL_TITLE, "Collectif", "fr", [("", blocks)])}]
    )


# ---------------------------------------------------------------------------------------------------------
# 3. En-têtes, pieds de page et numéros alternés (pages paires / impaires)

HF_TITLE = "Les essais"
HF_PARS = [
    "Ce guide accompagne les premiers essais du logiciel. Il décrit les étapes à suivre, les réglages "
    "conseillés et les erreurs les plus fréquentes, afin que chacun puisse convertir ses documents sans "
    "aide extérieure.",
    "La première étape consiste à choisir le fichier. Un document bien structuré, avec des titres et des "
    "paragraphes clairement séparés, donnera toujours un meilleur résultat qu’une simple image de page. "
    "Il est conseillé de vérifier que le texte peut être sélectionné dans un lecteur de PDF ordinaire, "
    "car c’est le signe qu’il pourra être extrait.",
    "La deuxième étape consiste à choisir la voix. Plusieurs voix sont livrées avec le logiciel ; elles "
    "diffèrent par leur timbre et leur débit, et chacun trouvera celle qui lui convient le mieux après "
    "quelques essais. La vitesse de lecture peut être réglée à tout moment.",
    "Le chiffre à retenir est le suivant.",
    "1789",
    "Guide d’essai de Voxpage",
    "La troisième étape est la conversion elle-même. Elle peut prendre quelques minutes pour un long "
    "document. Une barre de progression indique l’avancement, et la conversion peut être annulée à tout "
    "instant sans laisser de fichier incomplet sur le disque.",
    "Enfin, le fichier audio produit peut être copié sur un téléphone, un baladeur ou une clé USB. Les "
    "chapitres du document deviennent des chapitres du fichier, ce qui permet de naviguer facilement "
    "d’une partie à l’autre, comme dans un livre audio du commerce.",
    "Ces quelques étapes suffisent dans la plupart des cas. Pour les documents difficiles, comme les "
    "journaux à plusieurs colonnes ou les livres anciens numérisés, des réglages supplémentaires sont "
    "décrits dans la suite de ce guide, chapitre par chapitre, avec de nombreux exemples commentés.",
    "Les exemples ont été choisis pour représenter la variété des documents que l’on rencontre au "
    "quotidien : courriers, notices, articles de presse, rapports et romans. Chacun d’eux est accompagné "
    "du fichier audio obtenu, afin que l’on puisse comparer le résultat avec le document d’origine et "
    "repérer les éventuelles différences.",
    "Lorsque le résultat n’est pas satisfaisant, il est utile de noter la page concernée et de décrire le "
    "problème rencontré : un mot mal prononcé, une phrase coupée, un titre lu au mauvais endroit ou un "
    "tableau difficile à suivre. Ces remarques permettent d’améliorer le logiciel d’une version à "
    "l’autre, au bénéfice de tous les utilisateurs.",
    "Les réglages avancés ne sont pas nécessaires pour commencer. Ils permettent toutefois d’adapter la "
    "lecture aux habitudes de chacun : annonce des titres, durée des pauses entre les paragraphes, "
    "traitement des notes de bas de page et découpage du fichier audio par chapitre.",
    "Bonne écoute !",
]


def build_entetes():
    c = new_canvas("entetes.pdf", "Guide d’essai de Voxpage", "Équipe Voxpage")
    npages = 5

    def furniture(page):
        c.setFont(R, 9)
        if page > 1:
            if page % 2 == 0:
                c.drawString(72, H - 50, "Guide d’essai de Voxpage")
            else:
                c.drawRightString(W - 72, H - 50, "Chapitre premier : les essais")
            c.setLineWidth(0.5)
            c.line(72, H - 56, W - 72, H - 56)
        if page % 2 == 0:
            c.drawString(72, 40, str(page))
        else:
            c.drawRightString(W - 72, 40, str(page))

    frames = [
        (72, H - 110, 451, 600, 1),
        (72, H - 80, 451, 610, 2),
        (72, H - 80, 451, 590, 3),
        (72, H - 80, 451, 640, 4),
        (72, H - 80, 451, 72, 5),
    ]

    orig_show = c.showPage
    state = {"page": 1}

    def show():
        furniture(state["page"])
        state["page"] += 1
        orig_show()

    c.showPage = show
    c.setFont(B, 16)
    c.drawString(72, H - 90, HF_TITLE)
    f = Flow(c, frames, size=11, leading=15, indent=18, justify=True, words_mode=True)
    for k, p in enumerate(HF_PARS):
        f.paragraph(p, indent=0 if k == 0 else None, first=k == 0)
    while state["page"] <= npages:
        c.showPage()
    c.save()
    blocks = [Hd(HF_TITLE, 1)] + [P(p) for p in HF_PARS]
    write_expected(
        "entetes",
        [
            {
                "options": {},
                "document": doc("Guide d’essai de Voxpage", "Équipe Voxpage", "fr", [("", blocks)]),
            },
        ],
    )
    return f


# ---------------------------------------------------------------------------------------------------------
# 4. Césures : cas à recoller et cas à garder

CESURE_LINES = [
    "Le service de transcrip-",
    "tion fonctionne depuis peu et il est peut-",
    "être le plus utile de tous les services. Jean-",
    "Pierre l’utilise chaque jour, c’est-à-",
    "dire du matin au soir, sous un arc-en-",
    "ciel comme sous la pluie. « Venez », dit-",
    "il à ses voisins. Ce médicament anti-",
    "inflammatoire agit rapide-",
    "ment et sa por-",
    "tée est connue depuis le Moyen-",
    "Âge, ou du moins depuis 1914-",
    "1918 selon les historiens. Le week-",
    "end dernier, il a passé un week-end au calme pour",
    "ne contre-",
    "dire personne, car contredire fatigue, et pour trier un sac de bou-",
    "les de laine. Fin du premier paragraphe.",
]
CESURE_TEXT_1 = (
    "Le service de transcription fonctionne depuis peu et il est peut-être le plus utile de tous les "
    "services. Jean-Pierre l’utilise chaque jour, c’est-à-dire du matin au soir, sous un arc-en-ciel "
    "comme sous la pluie. « Venez », dit-il à ses voisins. Ce médicament anti-inflammatoire agit "
    "rapidement et sa portée est connue depuis le Moyen-Âge, ou du moins depuis 1914-1918 selon les "
    "historiens. Le week-end dernier, il a passé un week-end au calme pour ne contredire personne, car "
    "contredire fatigue, et pour trier un sac de boules de laine. Fin du premier paragraphe."
)
CESURE_LINES_2 = [
    "La biblio\u00ad",
    "thèque municipale ouvre à neuf heures —",
    "et ferme tard le jeudi. Son site, https://exemple.fr/",
    "horaires, donne le détail des ouvertures.",
]
CESURE_TEXT_2 = (
    "La bibliothèque municipale ouvre à neuf heures — et ferme tard le jeudi. Son site, "
    "https://exemple.fr/horaires, donne le détail des ouvertures."
)


def build_cesures():
    c = new_canvas("cesures.pdf", "Césures", None)
    y = H - 90
    for ln in CESURE_LINES:
        c.setFont(R, 11)
        c.drawString(72, y, ln)
        y -= 15
    y -= 15
    for k, ln in enumerate(CESURE_LINES_2):
        c.setFont(R, 11)
        c.drawString(72 + (16 if k == 0 else 0), y, ln)
        y -= 15
    c.showPage()
    c.save()
    write_expected(
        "cesures",
        [
            {
                "options": {},
                "document": doc(
                    "Césures",
                    None,
                    "fr",
                    [("", [["paragraph", 0, CESURE_TEXT_1], ["paragraph", 0, CESURE_TEXT_2]])],
                ),
            }
        ],
    )


# ---------------------------------------------------------------------------------------------------------
# 5. Paragraphe à cheval sur deux pages (avec césure au saut de page)

TWO_P1 = [
    "Les archives départementales conservent des milliers de registres paroissiaux.",
    "Ces documents, rédigés à la main pendant plusieurs siècles, permettent de retracer",
    "l’histoire des familles et des villages. Leur consultation, longtemps réservée aux",
    "chercheurs, est désormais ouverte à tous grâce à la numérisation, qui a deman-",
]
TWO_P2 = [
    "dé des années de travail et qui se poursuit encore aujourd’hui dans de nombreux",
    "départements, avec l’aide de bénévoles passionnés.",
]
TWO_P3 = [
    "Une seconde campagne commencera au printemps prochain.",
]
TWO_TEXT_1 = (
    "Les archives départementales conservent des milliers de registres paroissiaux. Ces documents, "
    "rédigés à la main pendant plusieurs siècles, permettent de retracer l’histoire des familles et des "
    "villages. Leur consultation, longtemps réservée aux chercheurs, est désormais ouverte à tous grâce à "
    "la numérisation, qui a demandé des années de travail et qui se poursuit encore aujourd’hui dans de "
    "nombreux départements, avec l’aide de bénévoles passionnés."
)


def build_deux_pages():
    c = new_canvas("deux_pages.pdf", "Les registres paroissiaux", None)
    for page, lines_list in ((1, [TWO_P1]), (2, [TWO_P2, TWO_P3])):
        y = H - 700 if page == 1 else H - 72
        for k, lines in enumerate(lines_list):
            for j, ln in enumerate(lines):
                x = 72 + (18 if (page == 2 and k == 1 and j == 0) else 0)
                draw_line(c, x, y, ln, R, 10, 451 - (x - 72), justify=(ln is not lines[-1]), words_mode=True)
                y -= 13
        c.setFont(R, 9)
        c.drawCentredString(W / 2, 40, f"– {page} –")
        c.showPage()
    c.save()
    write_expected(
        "deux_pages",
        [
            {
                "options": {},
                "document": doc(
                    "Les registres paroissiaux",
                    None,
                    "fr",
                    [("", [["paragraph", 0, TWO_TEXT_1], ["paragraph", 0, TWO_P3[0]]])],
                ),
            }
        ],
    )


# ---------------------------------------------------------------------------------------------------------
# 6. Notes de bas de page

NOTE_1 = "Victor Hugo, Les Misérables, 1862."
NOTE_2 = "Le terme désigne ici l’ensemble des imprimés vendus par colportage."
NOTE_3 = (
    "Ce chiffre, souvent cité, provient d’une enquête menée auprès de deux cents lecteurs réguliers ; "
    "il doit être pris avec prudence."
)


def _draw_runs(c, x, y, runs, size=11):
    """runs : liste de (texte, style) ; style ∈ {"", "sup"}."""
    for text, style in runs:
        if style == "sup":
            t = c.beginText(x, y)
            t.setFont(R, size * 0.62)
            t.setRise(size * 0.36)
            t.textOut(text)
            t.setRise(0)
            c.drawText(t)
            x += sw(text, R, size * 0.62)
        else:
            c.setFont(R, size)
            c.drawString(x, y, text)
            x += sw(text, R, size)
    return x


def _draw_note(c, y, mark, lines):
    x = _draw_runs(c, 72, y, [(mark, "sup")], size=9)
    c.setFont(R, 9)
    c.drawString(x + 1, y, lines[0])
    for ln in lines[1:]:
        y -= 11
        c.drawString(72, y, ln)


def build_notes():
    c = new_canvas("notes.pdf", "Le roman populaire", "Claire Dumas")
    y = H - 90
    page1 = [
        [
            ("Le roman populaire connaît son âge d’or au XIX", ""),
            ("e", "sup"),
            (" siècle, lorsque des auteurs", ""),
        ],
        [
            ("comme Hugo", ""),
            ("1", "sup"),
            (" ou Dumas touchent un public immense grâce aux journaux et", ""),
        ],
        [
            ("aux livrets de colportage", ""),
            ("2", "sup"),
            (". Les feuilletons paraissent dès le 1", ""),
            ("er", "sup"),
            (" janvier de", ""),
        ],
        [("chaque année, et les lecteurs attendent la suite avec impatience.", "")],
    ]
    for runs in page1:
        _draw_runs(c, 72, y, runs)
        y -= 15
    y -= 8
    page1b = [
        [("Une salle de lecture de 20 m", ""), ("2", "sup"), (" suffisait alors à accueillir tout un", "")],
        [("quartier, qui venait écouter la lecture du feuilleton du jour.", "")],
    ]
    for runs in page1b:
        _draw_runs(c, 72 + (16 if runs is page1b[0] else 0), y, runs)
        y -= 15
    c.setLineWidth(0.5)
    c.line(72, 118, 172, 118)
    _draw_note(c, 104, "1", [NOTE_1])
    _draw_note(c, 90, "2", [NOTE_2])
    c.setFont(R, 9)
    c.drawCentredString(W / 2, 40, "1")
    c.showPage()
    y = H - 90
    page2 = [
        [
            ("On estime que chaque exemplaire était lu par une dizaine de personnes", ""),
            ("3", "sup"),
            (",", ""),
        ],
        [("ce qui multiplie d’autant l’influence de ces récits sur la société.", "")],
    ]
    for runs in page2:
        _draw_runs(c, 72, y, runs)
        y -= 15
    c.line(72, 118, 172, 118)
    _draw_note(
        c,
        104,
        "3",
        [
            "Ce chiffre, souvent cité, provient d’une enquête menée auprès de deux cents",
            "lecteurs réguliers ; il doit être pris avec prudence.",
        ],
    )
    c.setFont(R, 9)
    c.drawCentredString(W / 2, 40, "2")
    c.showPage()
    c.save()
    p1 = (
        "Le roman populaire connaît son âge d’or au XIXe siècle, lorsque des auteurs comme Hugo ou Dumas "
        "touchent un public immense grâce aux journaux et aux livrets de colportage. Les feuilletons "
        "paraissent dès le 1er janvier de chaque année, et les lecteurs attendent la suite avec impatience."
    )
    p2 = (
        "Une salle de lecture de 20 m² suffisait alors à accueillir tout un quartier, qui venait écouter la "
        "lecture du feuilleton du jour."
    )
    p3 = (
        "On estime que chaque exemplaire était lu par une dizaine de personnes, ce qui multiplie d’autant "
        "l’influence de ces récits sur la société."
    )
    n1, n2, n3 = (["footnote", 0, t] for t in (NOTE_1, NOTE_2, NOTE_3))
    meta = ("Le roman populaire", "Claire Dumas", "fr")
    write_expected(
        "notes",
        [
            {"options": {"footnotes": "skip"}, "document": doc(*meta, [("", [P(p1), P(p2), P(p3)])])},
            {
                "options": {"footnotes": "inline"},
                "document": doc(*meta, [("", [P(p1), n1, n2, P(p2), P(p3), n3])]),
            },
            {
                "options": {"footnotes": "end_of_chapter"},
                "document": doc(*meta, [("", [P(p1), P(p2), P(p3), n1, n2, n3])]),
            },
        ],
    )


# ---------------------------------------------------------------------------------------------------------
# 7. Listes

LIST_TITLE = "Préparer un voyage"
LIST_INTRO = "Avant de partir, vérifiez les points suivants :"
LIST_BULLETS = [
    "le passeport, valide au moins six mois après la date du retour ;",
    "les billets de train ou d’avion, imprimés ou enregistrés sur le téléphone, ainsi que les "
    "réservations d’hôtel et les coordonnées des personnes à prévenir en cas de besoin ;",
    "une trousse de premiers secours.",
]
LIST_MIDDLE = "Ensuite, organisez le départ dans l’ordre suivant :"
LIST_NUMBERS = [
    "Réserver un taxi pour la gare.",
    "Fermer l’eau, le gaz et toutes les fenêtres.",
    "Confier les clés à un voisin de confiance, qui pourra arroser les plantes et relever le courrier "
    "pendant toute la durée de l’absence.",
]
LIST_DASH_INTRO = "Dans le sac à dos :"
LIST_DASHES = ["une gourde ;", "un vêtement de pluie."]
LIST_END = "Bon voyage à tous !"


def build_listes():
    c = new_canvas("listes.pdf", "Préparer un voyage", None)
    c.setFont(B, 14)
    c.drawString(72, H - 90, LIST_TITLE)
    y = H - 120

    def para(text, x=72, width=451):
        nonlocal y
        for ln, _last in wrap(text, R, 11, lambda i: width):
            c.setFont(R, 11)
            c.drawString(x, y, ln)
            y -= 15

    def item(marker, text, mx=72, tx=88):
        nonlocal y
        c.setFont(R, 11)
        c.drawString(mx, y, marker)
        for ln, _last in wrap(text, R, 11, lambda i: 523 - tx):
            c.setFont(R, 11)
            c.drawString(tx, y, ln)
            y -= 15

    para(LIST_INTRO)
    y -= 4
    for t in LIST_BULLETS:
        item("•", t)
    y -= 6
    para(LIST_MIDDLE)
    y -= 4
    for k, t in enumerate(LIST_NUMBERS, start=1):
        item(f"{k}.", t)
    y -= 6
    para(LIST_DASH_INTRO)
    for t in LIST_DASHES:
        item("–", t)
    y -= 6
    para(LIST_END)
    c.showPage()
    c.save()
    blocks = (
        [Hd(LIST_TITLE, 1), P(LIST_INTRO)]
        + [Li(t) for t in LIST_BULLETS]
        + [P(LIST_MIDDLE)]
        + [Li(f"{k}. {t}") for k, t in enumerate(LIST_NUMBERS, start=1)]
        + [P(LIST_DASH_INTRO)]
        + [Li(t) for t in LIST_DASHES]
        + [P(LIST_END)]
    )
    write_expected("listes", [{"options": {}, "document": doc(LIST_TITLE, None, "fr", [("", blocks)])}])


# ---------------------------------------------------------------------------------------------------------
# 8. Tableaux (quadrillé, puis à filets horizontaux) et légendes

TAB_INTRO = (
    "Le tableau suivant présente la population des quatre plus grandes communes de France, selon le "
    "recensement le plus récent."
)
TAB_1 = [
    ["Commune", "Population", "Superficie (km²)", "Région"],
    ["Paris", "2\u00a0133\u00a0111", "105", "Île-de-France"],
    ["Marseille", "873\u00a0076", "241", "Provence-Alpes-Côte d’Azur"],
    ["Lyon", "522\u00a0250", "48", "Auvergne-Rhône-Alpes"],
    ["Toulouse", "504\u00a0078", "118", "Occitanie"],
]
TAB_CAPTION_1 = "Tableau 1 : population municipale en 2021 (source : Insee)."
TAB_MIDDLE = (
    "La fréquentation de la médiathèque, elle, progresse régulièrement depuis l’ouverture du nouveau "
    "bâtiment, comme le montre le second tableau."
)
TAB_CAPTION_2 = "Tableau 2 – Fréquentation de la médiathèque."
TAB_2 = [
    ["Année", "Lecteurs inscrits", "Livres prêtés"],
    ["2022", "3\u00a0410", "41\u00a0200"],
    ["2023", "3\u00a0980", "47\u00a0650"],
    ["2024", "4\u00a0215", "52\u00a0030"],
]
TAB_END = "Ces chiffres seront mis à jour chaque année."


def build_tableau():
    c = new_canvas("tableau.pdf", "Quelques chiffres", None)
    y = H - 90

    def para(text):
        nonlocal y
        for ln, _last in wrap(text, R, 11, lambda i: 451):
            c.setFont(R, 11)
            c.drawString(72, y, ln)
            y -= 15

    para(TAB_INTRO)
    t = Table(TAB_1, colWidths=[80, 80, 100, 170])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), R, 10),
                ("FONT", (0, 0), (-1, 0), B, 10),
                ("GRID", (0, 0), (-1, -1), 0.5, black),
                ("BACKGROUND", (0, 0), (-1, 0), whitesmoke),
            ]
        )
    )
    _w, h = t.wrapOn(c, 451, 400)
    y -= 10
    t.drawOn(c, 72, y - h + 10)
    y = y - h - 6
    c.setFont(IT, 9)
    c.drawString(72, y, TAB_CAPTION_1)
    y -= 30
    para(TAB_MIDDLE)
    y -= 10
    c.setFont(IT, 9)
    c.drawString(72, y, TAB_CAPTION_2)
    y -= 8
    t2 = Table(TAB_2, colWidths=[80, 120, 120])
    t2.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), R, 10),
                ("LINEABOVE", (0, 0), (-1, 0), 1, black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, black),
                ("LINEBELOW", (0, -1), (-1, -1), 1, black),
            ]
        )
    )
    _w, h = t2.wrapOn(c, 451, 400)
    t2.drawOn(c, 72, y - h)
    y = y - h - 30
    para(TAB_END)
    c.showPage()
    c.save()

    def tab(rows):
        return ["table", 0, "\n".join("; ".join(cell.replace("\u00a0", " ") for cell in r) for r in rows)]

    blocks = [
        P(TAB_INTRO),
        tab(TAB_1),
        ["caption", 0, TAB_CAPTION_1],
        P(TAB_MIDDLE),
        ["caption", 0, TAB_CAPTION_2],
        tab(TAB_2),
        P(TAB_END),
    ]
    write_expected(
        "tableau", [{"options": {}, "document": doc("Quelques chiffres", None, "fr", [("", blocks)])}]
    )


# ---------------------------------------------------------------------------------------------------------
# 9. Signets (plan du PDF)

SIG = [
    (
        "Chapitre 1 — Origines",
        [
            (
                "p",
                "Les signets d’un PDF forment une table des matières que les lecteurs d’écran savent "
                "parcourir. "
                "Ils sont la source la plus sûre pour découper un document en chapitres.",
            ),
            ("s", "1.1 Les premiers livres"),
            (
                "p",
                "Les premiers livres imprimés n’avaient ni table des matières ni numéros de page ; "
                "le lecteur "
                "se repérait aux lettrines et aux titres courants.",
            ),
        ],
    ),
    (
        "Chapitre 2 — Usages",
        [
            (
                "p",
                "Aujourd’hui, presque tous les logiciels de mise en page produisent des signets à partir des "
                "titres du document.",
            ),
            ("s", "2.1 Navigation"),
            ("p", "Dans un fichier audio, chaque chapitre devient un point de navigation."),
        ],
    ),
    (
        "Chapitre 3 — Limites",
        [
            (
                "p",
                "Certains documents n’ont aucun signet, ou des signets incomplets : il faut alors "
                "repérer les "
                "titres d’après leur taille et leur graisse.",
            ),
        ],
    ),
]


def build_signets():
    c = new_canvas("signets.pdf", "Petit traité des signets", None)
    for ci, (title, content) in enumerate(SIG):
        key = f"c{ci}"
        y = H - 90
        c.bookmarkPage(key, fit="XYZ", left=0, top=y + 20)
        c.addOutlineEntry(title, key, level=0)
        c.setFont(B, 16)
        c.drawString(72, y, title)
        y -= 34
        for si, (kind, text) in enumerate(content):
            if kind == "s":
                y -= 10
                skey = f"c{ci}s{si}"
                c.bookmarkPage(skey, fit="XYZ", left=0, top=y + 14)
                c.addOutlineEntry(text, skey, level=1)
                c.setFont(R, 11)
                c.drawString(72, y, text)
                y -= 25
            else:
                for ln, _last in wrap(text, R, 11, lambda i: 451):
                    c.setFont(R, 11)
                    c.drawString(72, y, ln)
                    y -= 15
                y -= 6
        c.showPage()
    c.save()
    chapters = []
    for title, content in SIG:
        blocks = [Hd(title, 1)] + [Hd(t, 2) if k == "s" else P(t) for k, t in content]
        chapters.append((title, blocks))
    write_expected(
        "signets",
        [
            {"options": {}, "document": doc("Petit traité des signets", None, "fr", chapters)},
            {
                "options": {"pages": "2-3"},
                "document": doc("Petit traité des signets", None, "fr", chapters[1:]),
            },
        ],
    )


# ---------------------------------------------------------------------------------------------------------
# 10. Ligatures, espaces spéciaux, crénage, faux gras

LIG_TITLE = "ÉCLATÉ PAR LE CRÉNAGE"


def build_ligatures():
    c = new_canvas("ligatures.pdf", "Typographie", None)
    t = c.beginText(72, H - 90)
    t.setFont(B, 14)
    t.setCharSpace(5)
    t.textOut(LIG_TITLE)
    t.setCharSpace(0)
    c.drawText(t)
    y = H - 125
    c.setFont(R, 11)
    # reportlab n’écrit pas de correspondance Unicode correcte pour ﬀ, ﬃ, ﬄ (ni pour les accents combinants
    # de Vera) : ces cas sont couverts par les tests unitaires de pdf_text.
    c.drawString(72, y, "Le \ufb01lm \ufb02otte au vent, la \ufb01n est proche.")
    y -= 26
    c.drawString(
        72, y, "Il dit\u00a0: «\u00a0bonjour\u00a0»\u00a0! Le mot anti\u00adconstitutionnel est long."
    )
    y -= 26
    # mots placés un à un, avec un blanc réduit entre les mots (crénage serré, sans caractère espace)
    x = 72
    for w in "Les mots sont serrés mais restent bien séparés.".split(" "):
        c.drawString(x, y, w)
        x += sw(w, R, 11) + 2.2
    y -= 26
    # lettres placées une à une avec de petits décalages irréguliers : aucun blanc ne doit apparaître
    x = 72
    for k, ch in enumerate("Chaque lettre est posée séparément."):
        c.drawString(x, y, ch)
        x += sw(ch, R, 11) + (0.25 if k % 3 == 0 else -0.15)
    y -= 26
    # texte interlettré (espacement des caractères), avec de vrais espaces
    t = c.beginText(72, y)
    t.setFont(R, 11)
    t.setCharSpace(1.5)
    t.textOut("Un texte légèrement interlettré reste lisible.")
    t.setCharSpace(0)
    c.drawText(t)
    y -= 26
    # faux gras : le même texte imprimé deux fois avec un léger décalage
    c.drawString(72, y, "Texte en faux gras imprimé deux fois.")
    c.drawString(72.3, y, "Texte en faux gras imprimé deux fois.")
    c.showPage()
    c.save()
    texts = [
        "Le film flotte au vent, la fin est proche.",
        "Il dit : « bonjour » ! Le mot anticonstitutionnel est long.",
        "Les mots sont serrés mais restent bien séparés.",
        "Chaque lettre est posée séparément.",
        "Un texte légèrement interlettré reste lisible.",
        "Texte en faux gras imprimé deux fois.",
    ]
    # interligne régulier (double) : aucun indice de changement de paragraphe, un seul bloc est attendu
    blocks = [Hd(LIG_TITLE, 1), P(" ".join(texts))]
    write_expected("ligatures", [{"options": {}, "document": doc("Typographie", None, "fr", [("", blocks)])}])


# ---------------------------------------------------------------------------------------------------------
# 11. Document anglais, sans titre dans les métadonnées

EN_TITLE = "A Short Guide to Reading Aloud"
EN_LINES = [
    "Reading aloud is a well-",
    "known way to share a story. It brings a trans-",
    "formation of the text into sound, and it is self-",
    "evident that the reader must understand what is being read. Good infor-",
    "mation about the context helps the listener follow the plot.",
]
EN_TEXT = (
    "Reading aloud is a well-known way to share a story. It brings a transformation of the text into "
    "sound, and it is self-evident that the reader must understand what is being read. Good information "
    "about the context helps the listener follow the plot."
)
EN_2 = "The rest of this guide gives practical advice for each kind of document."


def build_anglais():
    c = new_canvas("anglais.pdf", None, None)
    c.setFont(B, 18)
    c.drawString(72, H - 90, EN_TITLE)
    y = H - 125
    for ln in EN_LINES:
        c.setFont(R, 11)
        c.drawString(72, y, ln)
        y -= 15
    y -= 10
    c.drawString(72, y, EN_2)
    c.showPage()
    c.save()
    blocks = [Hd(EN_TITLE, 1), ["paragraph", 0, EN_TEXT], P(EN_2)]
    write_expected("anglais", [{"options": {}, "document": doc(EN_TITLE, None, "en", [("", blocks)])}])


# ---------------------------------------------------------------------------------------------------------
# 12. Cas d'erreur et page scannée


def build_errors():
    from reportlab.lib.pdfencrypt import StandardEncryption

    c = new_canvas("protege.pdf", "Secret", None, encrypt=StandardEncryption("motdepasse", canPrint=0))
    c.setFont(R, 11)
    c.drawString(72, H - 90, "Ce document est protégé.")
    c.showPage()
    c.save()
    write_expected("protege", [{"options": {}, "error": "protégé par un mot de passe"}])

    (HERE / "corrompu.pdf").write_bytes(
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Type /Catalog >>\ngarbage\n"
    )
    write_expected("corrompu", [{"options": {}, "error": "n'est pas un PDF valide"}])

    c = new_canvas("vide.pdf", None, None)
    c.showPage()
    c.save()
    write_expected("vide", [{"options": {}, "error": "ne contient aucun texte"}])

    # page 1 : texte ; page 2 : image seule (page scannée)
    c = new_canvas("scan.pdf", "Document mixte", None)
    c.setFont(R, 11)
    c.drawString(72, H - 90, "Cette première page contient du texte natif.")
    c.showPage()
    img = Image.new("L", (200, 280), 255)
    for yy in range(20, 260, 12):
        for xx in range(20, 180):
            if (xx // 7 + yy) % 5:
                img.putpixel((xx, yy), 0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(ImageReader(buf), 40, 40, W - 80, H - 80)
    c.showPage()
    c.save()
    warn = (
        "Page 2 : aucun texte exploitable (page scannée ?). La reconnaissance de caractères (OCR) n'est pas "
        "disponible : contenu ignoré."
    )
    write_expected(
        "scan",
        [
            {
                "options": {},
                "document": doc(
                    "Document mixte",
                    None,
                    "fr",
                    [("", [P("Cette première page contient du texte natif.")])],
                    [warn],
                ),
            },
            {"options": {"pages": "2"}, "error": "document scanné"},
        ],
    )


def main() -> None:
    os.chdir(HERE)
    build_simple()
    build_colonnes()
    build_entetes()
    build_cesures()
    build_deux_pages()
    build_notes()
    build_listes()
    build_tableau()
    build_signets()
    build_ligatures()
    build_anglais()
    build_errors()
    print("Corpus généré dans", HERE)


if __name__ == "__main__":
    main()
