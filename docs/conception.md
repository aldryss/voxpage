# Voxpage — conception

Voxpage convertit un document (PDF aujourd'hui, d'autres formats demain) en fichier audio, pour des
personnes malvoyantes. Windows, portable (un dossier à dézipper, rien à installer), 100 % local.

## Priorités, dans l'ordre

1. **Fidélité de la transcription** : ce qui est lu doit être le texte du document, dans le bon ordre,
   sans bruit (en-têtes, numéros de page, césures) et sans rien inventer ni perdre.
2. **Accessibilité** : l'interface s'utilise entièrement au clavier et avec un lecteur d'écran (NVDA, JAWS,
   Narrateur). Contrôles natifs uniquement, chaque contrôle a un libellé.
3. **Tout en local** : aucun appel réseau à l'exécution. Les modèles sont livrés dans le zip.
4. **Portable** : aucun installeur, aucune écriture hors du dossier de l'application (repli sur
   `%APPDATA%\Voxpage` seulement si le dossier n'est pas inscriptible).

## Choix techniques

| Sujet | Choix | Raison |
|---|---|---|
| Langage | Python 3.12 | meilleur outillage PDF et TTS ; cœur testable sous Linux |
| Interface | wxPython (contrôles Win32 natifs) | bien supporté par les lecteurs d'écran (NVDA est écrit avec) |
| Texte PDF | pdfminer.six (mise en page, polices) + pypdfium2 (signets, rendu des pages) | licences permissives (pas de PyMuPDF : AGPL) |
| OCR (pages scannées) | RapidOCR (onnxruntime) + modèles PP-OCR, voir [ocr.md](ocr.md) | choisi par mesure sur du français (CER, WER, accents, espaces) ; wheels Windows disponibles ; modèles livrés dans `ocr/` |
| Synthèse vocale | sherpa-onnx épinglé `>=1.13,<2` + voix Piper (ONNX) | locale, rapide sur CPU, voix françaises claires ; la 2.x n'embarque plus espeak-ng (phonémisation des voix Piper), la 1.13.x oui et a une wheel Windows cp312 |
| Encodage | lameenc (MP3), module `wave` (WAV), mutagen (tags, chapitres) | pas de ffmpeg à livrer |
| Livrable | PyInstaller `--onedir`, zippé, construit sur `windows-latest` par GitHub Actions | pas de compilation croisée fiable depuis Linux |

Développement : tout passe par le conteneur (`./dev <commande>`, voir `Dockerfile.dev`). La machine hôte
n'a que Python 3.8.

## Chaîne de traitement

```
fichier ──▶ Extractor ──▶ Document ──▶ normalize ──▶ SpeechChapter[] ──▶ TtsEngine ──▶ AudioWriter ──▶ MP3/WAV
            (par format)   (structure)   (texte à dire)                   (PCM par segment)  (flux, chapitres)
```

L'audio est produit et encodé **en flux**, segment par segment : un livre de 500 pages ne doit jamais
tenir en mémoire.

## Interfaces (contrat entre modules — ne pas les changer sans mettre à jour ce document)

```python
# voxpage/document.py
BlockKind = Literal["heading", "paragraph", "list_item", "table", "footnote", "caption"]

@dataclass
class Block:
    kind: BlockKind
    text: str                 # texte brut du document, non normalisé pour la voix
    level: int = 0            # niveau de titre (1 = plus haut) ; 0 sinon
    page: int | None = None   # page d'origine, à partir de 1
    loose: bool = False       # table seulement : zone tabulaire ou graphique sans structure fiable (lignes lues telles quelles)

@dataclass
class Chapter:
    title: str                # "" si le document n'a pas de chapitres
    blocks: list[Block]

@dataclass
class Document:
    title: str
    author: str | None
    lang: str                 # "fr" ou "en" (langue dominante détectée)
    chapters: list[Chapter]
    warnings: list[str]       # messages lisibles par l'utilisateur (ex. « pages 4 à 9 : texte reconnu par OCR »)

# voxpage/progress.py
ProgressCb = Callable[[str, float], None]     # (étape lisible, fraction 0..1)
class Cancelled(Exception): ...
class CancelToken:                            # .cancel(), .cancelled, .raise_if_cancelled()

# voxpage/extract/base.py
@dataclass
class ExtractOptions:
    ocr: Literal["auto", "never", "always"] = "auto"
    footnotes: Literal["skip", "inline", "end_of_chapter"] = "skip"
    pages: str | None = None                  # "1-10,15" ; None = tout

class Extractor(Protocol):
    extensions: tuple[str, ...]               # (".pdf",)
    def extract(self, path: Path, options: ExtractOptions,
                progress: ProgressCb | None = None, cancel: CancelToken | None = None) -> Document: ...

# voxpage/extract/base.py : class UnsupportedFormat(Exception)
# voxpage/extract/base.py : class ExtractError(Exception)   # document illisible (protégé, endommagé, vide,
#                           sélection de pages invalide) ; message en français destiné à l'utilisateur

# voxpage/extract/ocr.py — appelé par l'extracteur PDF quand available() est vrai (moteur importable et
# modèles dans ocr/) ; sinon l'extracteur garde son comportement sans OCR :
def available() -> bool
def recognize(pdf_path: Path, page_index: int, lang: str | None) -> OcrPage   # page_index à partir de 0
@dataclass OcrPage: width, height (points), lines: list[OcrLine(text, x0, top, x1, bottom, score)]
# voxpage/lang.py
def detect_lang(text: str) -> Literal["fr", "en"]    # mots-outils ; "fr" si égalité ou texte vide

# voxpage/extract/__init__.py  (l'extracteur .txt y est enregistré par défaut)
def register(extractor: Extractor) -> None
def extractor_for(path: Path) -> Extractor    # lève UnsupportedFormat
def supported_extensions() -> list[str]

# voxpage/normalize/__init__.py
@dataclass
class Segment:
    text: str                 # une phrase prête à être dite
    pause_after_ms: int
@dataclass
class SpeechChapter:
    title: str
    segments: list[Segment]
@dataclass
class NormalizeOptions:
    announce_headings: bool = True
    sentence_pause_ms: int = 250
    paragraph_pause_ms: int = 700
    heading_pause_ms: int = 1200
def normalize(doc: Document, options: NormalizeOptions,
              lexicon: Lexicon | None = None) -> list[SpeechChapter]   # lexicon : dictionnaire de prononciation de la langue du document
def spoken_title(title: str, lang: str, options=None, lexicon: Lexicon | None = None) -> list[str]

# voxpage/normalize/lexicon.py — dictionnaire de prononciation « écrit = dit » (issue #13), voir plus bas
class Lexicon:                # dictionnaire fusionné pour une langue
    def __init__(self, mapping: dict[str, str] | None = None, lang: str = "fr")
    def apply(text) -> str    # écrits connus -> repères opaques (protégés des règles suivantes)
    def restore(text) -> str  # repères -> « dit » ; say() = restore(apply())
@dataclass LexiconSource:     # d'où vient le dictionnaire d'une conversion
    user_path: Path | None = None; shipped: bool = True; user: bool = True
    def load(lang) -> LoadedLexicon      # .lexicon, .user_path, .user_entries, .shipped_entries, .problems, .warnings()
class LexiconFile:            # fichier de l'utilisateur, modifié ligne à ligne (commentaires et ordre conservés)
    add / update / remove / save ; entries, problems
def parse(text) -> (list[Entry], list[Problem]) ; def read_entries(path) ; def merge(*sources, lang) -> dict

# voxpage/tts/base.py
@dataclass
class Voice:
    id: str                   # nom du dossier dans voices/, ex. "fr_FR-siwis-medium"
    name: str                 # nom affiché, ex. « Français — Siwis (femme) »
    lang: str                 # "fr", "en"
    speakers: list[str]       # [] si mono-locuteur
class TtsEngine(Protocol):
    def list_voices(self) -> list[Voice]: ...
    def synthesize(self, text: str, voice_id: str, speaker: int = 0,
                   speed: float = 1.0) -> tuple[np.ndarray, int]: ...   # (int16 mono, fréquence)

# voxpage/audio/__init__.py
@dataclass
class AudioOptions:
    format: Literal["mp3", "wav"] = "mp3"
    bitrate_kbps: int = 64                    # voix mono : 64 kbit/s suffit
    split: Literal["single", "chapters"] = "single"
class AudioWriter:                            # utilisable avec `with` (close() si tout va bien, abort() sur exception)
    def __init__(self, output: Path, options: AudioOptions, title: str, author: str | None): ...
    def start_chapter(self, title: str) -> None
    def write(self, samples: np.ndarray, sample_rate: int) -> None   # int16 mono ; 1re fréquence = celle de la sortie, les autres sont rééchantillonnées
    def write_silence(self, ms: int) -> None  # ignoré en tête de chapitre
    def close(self) -> list[Path]             # fichiers produits (+ .m3u8 en mode "chapters") ; [] si aucun son
    def abort(self) -> None                   # supprime tout ce qui a été produit, sans toucher aux fichiers préexistants
    duration_s: float                         # propriété : durée totale écrite
class AudioError(Exception)                   # message en français (destination non inscriptible, disque plein…)
# "single" : un fichier, chapitres en trames ID3 CHAP/CTOC (mp3).
# "chapters" : dossier `output` (sans extension) contenant 001 - Titre.mp3, … et une liste de lecture .m3u8.
# Écriture : fichiers `.part` renommés à close() ; une sortie existante n'est remplacée qu'à la fermeture réussie.
# MP3 : CBR mono avec trame « Info » (durée exacte, lecture sans blanc). Limite WAV : 4 Gio par fichier.

# voxpage/settings.py
@dataclass
class Settings:                               # sérialisé en JSON à côté de l'exécutable
    voice_id: str = ""; speaker: int = 0; speed: float = 1.0
    extract: ExtractOptions; normalize: NormalizeOptions; audio: AudioOptions   # valeurs par défaut des dataclasses
def load() -> Settings ; def save(s: Settings) -> None ; def app_dir() -> Path ; def voices_dir() -> Path
def pronunciations_path() -> Path ; def pronunciations_read_path() -> Path | None   # prononciations.txt, voir « Prononciations »
# settings.json : dans app_dir() (dossier de l'exe si gelé, sinon racine du dépôt) ; si non inscriptible,
# repli sur %APPDATA%\Voxpage (Windows) ou ~/.config/voxpage. load() ignore clés inconnues et valeurs invalides.
# voices_dir() = app_dir()/voices, surchargeable par la variable d'environnement VOXPAGE_VOICES.

# voxpage/pipeline.py
def convert(input: Path, output: Path, settings: Settings,
            progress: ProgressCb | None = None, cancel: CancelToken | None = None,
            engine: TtsEngine | None = None,
            pronunciations: LexiconSource | None = None) -> ConvertResult   # engine : injection pour les tests
@dataclass
class ConvertResult:
    files: list[Path]; duration_s: float; warnings: list[str]
def extract_text(input: Path, settings: Settings,
                 progress: ProgressCb | None = None, cancel: CancelToken | None = None,
                 warnings: list[str] | None = None,
                 pronunciations: LexiconSource | None = None) -> str   # « exporter le texte »
class ConversionError(Exception): ...   # erreur prévue, message en français (aucun texte lisible, voix introuvable, sortie non inscriptible…)
# Toute erreur remonte en ConversionError (ou Cancelled) et laisse le disque propre. Voix vide = voix par défaut de la
# langue du document (Siwis en français, voir tts/base.default_voice ; à défaut la première voix de cette langue) ; voix d'une autre langue = avertissement, pas de changement. Segment en échec : une nouvelle
# tentative, puis erreur citant le passage. extract_text : un segment par ligne, titres de chapitre sous la forme « == Titre == ».
```

Ajouter un format d'entrée = écrire un `Extractor` et l'enregistrer ; rien d'autre ne change.

Extracteur PDF (`voxpage/extract/pdf.py` et `pdf_*.py`) : caractères (pdfminer) → fragments de ligne →
retrait des en-têtes, pieds et numéros de page → notes de bas de page → tableaux et encadrés (filets, fonds) →
ordre de lecture par découpage XY avec détection des gouttières → paragraphes (césures recollées selon les
règles documentées dans `pdf_text.py`) → titres (signets du PDF, sinon taille et graisse), listes, légendes →
chapitres. Les pages sans texte exploitable sont confiées à `ocr.recognize` si le moteur est disponible ;
sinon un avertissement les nomme. Les lignes reconnues deviennent des `PageData` et suivent la même chaîne que
le texte natif (voir [ocr.md](ocr.md)).

Repérages prudents (`pdf_tabular.py`, sans perte de texte) : au moins 4 lignes consécutives « Titre ……… 12 »
forment un sommaire, réduit à ses titres (ni points de conduite ni numéros de page) ; au moins 6 lignes très
courtes, majoritairement numériques et alignées forment un bloc `table` marqué `loose`, annoncé à l'auditeur
« Tableau ou graphique, lu tel quel. » et signalé dans `Document.warnings`. Les tableaux structurés sont
annoncés « Tableau. » / « Fin du tableau. » et lus « en-tête : valeur » quand la première ligne est un
en-tête sûr. Les sigles qui ne se prononcent pas comme un mot sont épelés par `normalize/acronyms.py`
(lettres séparées par une espace, forme que les voix disent le mieux ; liste de sigles lus comme des mots).

## Prononciations

Les voix disent mal certains sigles, noms propres et mots rares (mesures : `recette.md`). Le dictionnaire de
prononciation (`voxpage/normalize/lexicon.py`) permet de préciser comment les lire. Une entrée est
`écrit = dit` (`EDF = eu dé effe`, `Nguyen = nou-yène`, `c.-à-d. = c'est-à-dire`) ; le « dit » est du texte
ordinaire, lu tel quel (aucune phonétique à apprendre).

**Sources.** Deux dictionnaires sont fusionnés : celui livré par langue (`voxpage/normalize/data/
prononciations-fr.txt` et `-en.txt`, données du paquet, ajoutées à l'exécutable par `voxpage.spec`) et celui
de l'utilisateur, `prononciations.txt` à côté de `settings.json` (même dossier portable, même repli sur
`%APPDATA%\Voxpage`). L'utilisateur l'emporte ; une entrée utilisateur au dit vide (`mot =`) annule l'entrée
livrée de même écrit. Le pipeline charge le dictionnaire de la langue du document (`LexiconSource.load`).

**Fichier.** UTF-8 (BOM et fins de ligne Windows acceptés ; à défaut d'UTF-8 valide, lu en ANSI), une entrée
par ligne, `#` pour un commentaire en début de ligne, lignes vides ignorées, sections facultatives `[fr]`,
`[en]` et `[toutes]` (hors section : toutes les langues). La lecture est tolérante : une ligne invalide est
ignorée et signalée (« ligne 3 ignorée : … ») dans les avertissements de la conversion, sans l'empêcher. Dans un
même fichier, l'entrée propre à une langue l'emporte sur l'entrée « toutes langues ». Les écritures depuis
l'application (`LexiconFile`) modifient le fichier ligne à ligne : commentaires, lignes invalides et ordre sont
conservés, fins de ligne et BOM aussi, l'écriture passe par un fichier temporaire renommé.

**Correspondance.** Mots ou expressions entiers seulement : une frontière est tout caractère qui n'est pas
une lettre ou un chiffre (apostrophes, traits d'union, ponctuation, parenthèses : « l'INRIA », « (EDF) »,
« EDF. », « pro-UE »), mais jamais l'intérieur d'un mot (« UE » ne touche ni « QUEUE » ni « bleue »). Une
apostrophe précédant l'écrit n'est une frontière qu'après une élision (« l' », « d' », « qu' »… en français ;
jamais en anglais : « O'Neil »). Une entrée qui contient une majuscule est sensible à la casse, une entrée tout
en minuscules ne l'est pas (l'entrée à la casse exacte l'emporte). Les espaces d'une expression valent n'importe
quelle suite d'espaces ou de retours à la ligne, les deux apostrophes (`'` et `’`) sont équivalentes. La plus
longue entrée l'emporte. Le pluriel n'est pas deviné (« CDIs » demande sa propre entrée). Toutes les entrées
forment une seule expression régulière compilée (arbre de préfixes) : environ 0,2 s pour un livre de 800 000
caractères et 500 entrées.

**Place dans la chaîne.** Dans `_block_segments`, après le nettoyage du bloc et avant la remise en casse des
titres en capitales : `Lexicon.apply` remplace chaque écrit reconnu par un repère opaque (quatre capitales
mathématiques grasses, U+1D400…, qui sont des lettres majuscules pour la découpe en phrases et la remise en
casse mais ne ressemblent ni à un sigle, ni à un nombre, ni à un mot). Les règles suivantes (découpe en phrases,
URL, nombres, dates, abréviations, sigles, symboles) ne voient donc que le repère. Une fois la phrase réécrite
(`speak`), `Lexicon.restore` met le dit à la place. Le dit n'est ainsi retraité ni par les règles de sigles, ni
par les règles de nombres ou de casse.

**Interface.** Le bouton « Prononciations… » (Alt+P) ouvre `gui/pronunciation_dialog.py` (logique sans wx dans
`gui/pronunciations.py`) : liste des entrées de l'utilisateur (colonnes « Écrit », « Dit », « Langue »), champs
« Écrit » et « Dit », langue (toutes, français, anglais), Ajouter / Modifier / Supprimer (la touche Suppr
aussi, avec confirmation), « Écouter » (le dit, avec la voix de la fenêtre principale), « Écouter sans le
dictionnaire » (l'écrit tel que Voxpage le lirait sans entrée), « Ouvrir le fichier » (Bloc-notes ; la liste est
relue au retour si le fichier a changé), Fermer (Échap). Chaque modification est enregistrée aussitôt.
`--gui-self-test` couvre le dialogue (accessibilité, ajout, modification, suppression, écoute, relecture).
Le bouton « Parcourir » passe en Alt+I et « Ouvrir le dossier » en Alt+E pour laisser Alt+P à « Prononciations ».

**Ligne de commande.** `--prononciations FICHIER` remplace le fichier de l'utilisateur pour la conversion (le
dictionnaire livré reste appliqué) ; `--sans-prononciations` ignore le livré et celui de l'utilisateur ;
`--diagnostic` indique le chemin du fichier, le nombre d'entrées lues et le nombre d'entrées livrées par langue.

**Dictionnaire livré.** Chaque entrée de `prononciations-fr.txt` a été vérifiée par aller-retour synthèse →
reconnaissance (`tools/roundtrip.py --verifier-entrees`, deux voix, deux phrases) et n'est retenue que si elle
améliore la lecture ; mesures dans `recette.md`. Version 0.2.0.

## Voix

Les voix sont des dossiers dans `voices/` (modèle `.onnx`, `tokens.txt`, `espeak-ng-data/`, `voice.json`
avec nom affiché, langue, licence). Ajouter une voix = déposer un dossier. Le zip livre au moins une voix
française féminine, une masculine et une voix anglaise, dont la licence autorise la redistribution.

## Interface

Une seule fenêtre : choisir le fichier (ou le glisser), voix, vitesse, format et découpage, « Écouter un
extrait », « Convertir », barre de progression et zone d'état annoncée par le lecteur d'écran, « Annuler »,
« Exporter le texte », « Prononciations » (dialogue du dictionnaire, voir plus haut). Ligne de commande équivalente (`voxpage.exe entree.pdf -o sortie.mp3 …`), qui sert
aussi aux tests de la CI.

## Livrable

`Voxpage-<version>-win64-portable.zip` (plus un `.sha256`), construit par `.github/workflows/release.yml`
avec `packaging/voxpage.spec` (PyInstaller `--onedir`, sans UPX). Contenu du dossier `Voxpage/` :
`Voxpage.exe` (fenêtré ; avec arguments, délègue à la CLI), `voxpage-cli.exe` (console), `_internal/`
(Python et bibliothèques natives), `voices/` (3 voix + README), `LISEZMOI.txt`, `NOTICE.txt` (licences
tierces, généré par `packaging/make_notice.py`). `settings.json` est écrit à côté de l'exécutable, et
`prononciations.txt` (dictionnaire de l'utilisateur) au premier ajout d'une entrée.
Version unique : `pyproject.toml` (= `voxpage.__version__`, test à l'appui) ; le tag `vX.Y.Z` doit
correspondre. Le workflow teste l'exécutable construit (`packaging/test_release.py`) dans un dossier
décompressé hors du dépôt, au chemin avec espace et accent, avec un PATH réduit à Windows.
Sous Windows, eSpeak NG et onnxruntime lisent les chemins en ANSI : un chemin accentué est converti en nom
court 8.3 (ou copie temporaire) avant le chargement d'une voix (`ascii_voice_folder`).
`voxpage --diagnostic` vérifie les bibliothèques embarquées et l'écriture des réglages.
Exécutable non signé : avertissement SmartScreen, documenté dans `LISEZMOI.txt`.
Procédure : `docs/release.md`.

## Vérification

- Tests unitaires sur chaque module (pytest), exécutés sous Linux et Windows par la CI.
- Corpus de PDF de test (`tests/corpus/`) avec le texte attendu : colonnes, en-têtes et pieds, césures,
  notes, listes, tableaux, pages scannées.
- Le workflow de release lance l'exécutable construit sur un PDF du corpus et vérifie le MP3 produit.
- Recette de bout en bout sur des documents réels : `docs/recette.md`. Intelligibilité sans écoute :
  `tools/roundtrip.py` (synthèse puis reconnaissance Whisper, WER ; outil de développement, jamais livré).
