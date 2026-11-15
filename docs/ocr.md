# OCR des pages scannées

Voxpage lit les pages sans texte (scans, photos de pages) par reconnaissance de caractères, **en local**, avec
des modèles livrés dans le zip. Ce document explique le choix du moteur (par mesure), le fonctionnement, et
ce qu'il ne sait pas faire.

## Décision

**RapidOCR (onnxruntime) avec les modèles PP-OCRv5** (détection « mobile » 4,8 Mo, reconnaissance « latin »
7,9 Mo), précédé d'un prétraitement maison (fond uniformisé, redressement).

| Critère (dans l'ordre) | RapidOCR + PP-OCRv5 | Tesseract 5.5 (`fra` best) |
|---|---|---|
| Fidélité sur pages propres, 300 dpi | CER 0,00 % | CER 0,04 % |
| Fidélité sur pages dégradées (150 dpi, flou, bruit, contraste faible) | CER 0,7 % | CER 8,7 %, 15 erreurs d'espace pour 1 000 caractères |
| Pages réelles du domaine public (scans de livres anciens) | CER 2,0 %, WER 5,4 % | CER 2,3 %, WER 6,5 % |
| Embarquement dans le zip Windows | wheels `win_amd64` cp312 (onnxruntime, OpenCV, Shapely, pyclipper), licences Apache-2.0 / MIT / BSD | pas de wheel : binaire à extraire d'un installateur tiers (NSIS), plus fragile |
| Taille ajoutée au zip | +64 Mo (281,8 → 346,3 Mo, mesuré) | non construit (binaire, DLL et `fra` 4 Mo) |
| Vitesse | 4 à 7 s par page, 4 cœurs (voir « Temps par page ») | environ 2 s par page |

Tesseract est légèrement plus rapide et aussi bon sur les pages parfaites, mais il décroche dès que la
numérisation se dégrade (lignes entières ignorées, mots collés ou coupés), et ce sont justement les pages où
l'auditeur ne peut rien vérifier. À fidélité égale ou meilleure, RapidOCR s'embarque proprement. Les erreurs
restantes de RapidOCR sont décrites dans « Limites ».

Aucune option n'atteint 0 % sur de vrais scans anciens (2 % de caractères faux, soit environ un mot sur 18) :
**la lecture d'une page scannée peut contenir des erreurs**, et Voxpage le dit à la fin de la conversion. Sur
des pages propres à 300 dpi, tous les candidats retenus sont très en dessous du seuil de 2 %.

## Méthode

Banc d'essai : `tools/ocr_bench.py` (versionné, reproductible, graine fixe), textes dans
`tools/ocr_bench_texts.py`.

- **12 pages de vérité terrain connue** : 10 textes français originaux (roman, presse, article scientifique,
  lettre de 1912, recette, conditions de vente, dialogue, histoire, notice technique, deux colonnes) avec
  accents, majuscules accentuées, œ, ç, apostrophes droites et courbes, guillemets « », tirets de dialogue,
  nombres (4 250 000 €, 37,52 %, 1914-1918), sigles, ponctuation variée, en Times, Helvetica et corps 10 à
  13 ; et 2 pages de la Constitution du corpus (`tests/corpus/reels`). Chaque page est rendue en image à
  300 dpi puis dégradée de 5 façons :

  | Condition | Traitement |
  |---|---|
  | `propre-300` | rendu net à 300 dpi |
  | `propre-150` | même page à 150 dpi |
  | `mauvais-300` | flou, bruit, contraste faible (noir à 55, blanc à 195), éclairage inégal, rotation 1,5°, JPEG qualité 45 |
  | `mauvais-150` | idem à 150 dpi |
  | `incline-300` | rotation de −2° seule, JPEG qualité 70 |

- **12 pages réelles du domaine public** (condition `réel`) : pages numérisées de *Tartarin de Tarascon*
  (Daudet, 1872), *Bouvard et Pécuchet* (Flaubert, 1910), *Contes à Ninon* (Zola, 1864) et *Autour de la
  Lune* (Verne), avec la transcription relue et validée de Wikisource (niveau « validé », pages sans note
  ni modèle particulier ; l'en-tête courant imprimé est ajouté à la vérité terrain). Elles sont récupérées à
  la demande par `ocr_bench.py fetch-real`, non versionnées.

- **Mesures** : taux d'erreur de caractères (CER) et de mots (WER) sur le texte aplati (retours à la ligne
  ramenés à une espace, césures de fin de ligne recollées avec les règles de l'extracteur, apostrophes,
  guillemets, tirets et espaces avant la ponctuation haute ramenés à une forme commune, car la synthèse
  vocale les dit de la même façon) ; erreurs d'accent (opérations d'édition qui touchent une lettre
  accentuée) et d'espacement (celles qui touchent une espace), pour 1 000 caractères ; temps par page.

- **Réglages des moteurs** : tous sans seuil de confiance (rien n'est écarté). RapidOCR : image réduite à
  2 400 px de grand côté, `unclip_ratio` 1,6 (valeurs essayées : 1,0 à 1,6, voir plus bas) ; Tesseract :
  `--oem 1 --psm 3`. « +norm » désigne le prétraitement de `voxpage/extract/ocr_prep.py` (fond uniformisé puis
  redressement), appliqué à l'identique à chaque moteur pour la comparaison.

## Résultats

CER / WER en %, moyenne des 12 pages de chaque condition. (Exécutions concurrentes sur une machine chargée :
les temps par page ne sont pas comparables entre lignes.)

| Moteur | propre 300 | propre 150 | mauvais 300 | mauvais 150 | incliné 300 | réel |
|---|---|---|---|---|---|---|
| Tesseract best, image brute | 0,04 / 0,25 | 0,05 / 0,30 | **93,4** / 94,4 | **99,6** / 99,6 | **17,3** / 17,5 | 2,34 / 6,65 |
| Tesseract best +norm | 0,04 / 0,25 | 0,04 / 0,25 | 4,75 / 21,95 | 8,74 / 33,96 | 0,05 / 0,28 | 2,32 / 6,51 |
| Tesseract fast +norm | 0,08 / 0,45 | 0,07 / 0,42 | 7,55 / 23,99 | 11,16 / 34,66 | 0,09 / 0,49 | 2,71 / 8,29 |
| RapidOCR PP-OCRv4 (latin v3) +norm | — | — | — | — | — | 4,32 / 18,35 |
| RapidOCR PP-OCRv6 small, brut | 0,03 / 0,28 | 0,01 / 0,07 | 0,09 / 0,57 | 1,20 / 5,36 | 1,69 / 2,07 | 2,06 / 5,75 |
| RapidOCR PP-OCRv6 small +norm | 0,03 / 0,28 | 0,01 / 0,13 | 0,08 / 0,54 | 0,72 / 4,76 | 0,03 / 0,33 | 2,02 / 5,50 |
| RapidOCR PP-OCRv5 latin, brut | 0,00 / 0,00 | 0,01 / 0,04 | 0,11 / 0,70 | 4,57 / 8,63 | **22,6** / 26,7 | 2,00 / 5,43 |
| RapidOCR PP-OCRv5 latin +norm, unclip 1,3 | 0,01 / 0,04 | 0,01 / 0,04 | 0,07 / 0,41 | 0,75 / 4,53 | 0,01 / 0,04 | — |
| **RapidOCR PP-OCRv5 latin +norm, unclip 1,6 (retenu)** | **0,00 / 0,00** | 0,01 / 0,04 | **0,06 / 0,34** | **0,68 / 4,05** | **0,00 / 0,00** | 2,02 / 5,55 |
| **Chaîne Voxpage complète** (extracteur PDF, `ocr="always"`) | 0,02 / 0,06 | 0,01 / 0,07 | 0,08 / 0,44 | 0,68 / 4,01 | 0,02 / 0,10 | 2,22 / 5,27 |

Erreurs d'accent / d'espace pour 1 000 caractères, sur les pages `mauvais-150` et `réel` :

| Moteur | mauvais 150 | réel |
|---|---|---|
| Tesseract best +norm | 7,8 / 14,9 | 1,9 / 1,9 |
| Tesseract fast +norm | 11,5 / 14,6 | 2,6 / 1,9 |
| RapidOCR v6 small +norm | 2,0 / 1,1 | 1,5 / 1,5 |
| RapidOCR v5 latin brut | 3,9 / 5,4 | 1,6 / 1,7 |
| **RapidOCR v5 latin +norm (retenu)** | **0,9 / 0,4** | 1,6 / 1,8 |

Ce que les chiffres disent :

- **Le prétraitement compte autant que le moteur.** Sans redressement, RapidOCR perd 22 % des caractères sur
  une page inclinée de 2° ; sans uniformisation du fond, Tesseract ne lit presque rien d'une page à
  éclairage inégal (93 % d'erreurs). Les deux sont donc faits avant tout moteur (`ocr_prep.py`).
- **PP-OCRv5 latin bat PP-OCRv6 small** sur ces pages (0,00 contre 0,03 % de CER en propre, 0,68 contre
  0,72 % en dégradé) tout en pesant 12,7 Mo au lieu de 31 Mo ; sur une page en police sans empattement à
  200 dpi, v6 small collait des mots (`2024à`, `votéà`, CER 1,95 %, WER 17 %) là où v5 ne se trompe pas. Le
  modèle PP-OCRv6 « medium » (139 Mo) lit cette page sans erreur mais est environ huit fois plus lent sur la
  page testée : écarté.
- Le `unclip_ratio` (marge ajoutée autour des lignes détectées) de 1,6 est meilleur que 1,3 : sur v5, propre
  300 dpi 0,01 → 0,00 % de CER, mauvais 150 dpi 0,75 → 0,68 % ; sur v6 small, la page à police sans
  empattement passe de 1,95 à 0,33 % de CER.
- **Chaîne complète** : sur des pages isolées, elle égale ou dépasse le moteur seul (0,02 % en propre,
  0,68 % en dégradé 150 dpi) grâce au prétraitement et aux corrections `I`/`l`. Sur les pages réelles (2,22 %
  contre 2,02 %), les pages isolées d'*Autour de la Lune* perdent un peu : leur en-tête courant (« 22 AUTOUR DE
  LA LUNE. ») n'est supprimé que s'il se répète sur au moins deux pages, ce que le banc ne peut pas voir
  page par page.
- Sur les **pages réelles**, tous les moteurs plafonnent vers 2 % de CER (WER 5 à 6,5 %) : typographie
  ancienne, encre baveuse, coupures de mots. L'écart entre moteurs n'y est pas significatif ; l'avantage de
  RapidOCR tient à sa robustesse sur les mauvaises numérisations et à sa distribution.
- **PP-OCRv4** (modèle latin v3) est nettement moins bon (WER 18 %, accents ×7) : écarté.

## Distribution dans le zip Windows

- `rapidocr` 3.x, `onnxruntime` 1.32, `opencv-python-headless`, `shapely`, `pyclipper` : tous publient des
  wheels `win_amd64` pour Python 3.12 (vérifié par `pip download --platform win_amd64`). Licences :
  Apache-2.0 (RapidOCR, OpenCV, modèles PaddleOCR), MIT (onnxruntime, pyclipper), BSD-3 (Shapely, qui porte
  GEOS en LGPL-2.1) ; reprises dans `NOTICE.txt` (`packaging/make_notice.py`).
- **Pas de conflit entre les deux onnxruntime** : la wheel `sherpa-onnx` Windows lie onnxruntime en statique
  dans son `.pyd` ; la DLL du paquet `onnxruntime` est donc la seule du processus. Vérifié par l'exécutable
  construit, qui fait l'OCR puis la synthèse vocale dans un même processus.
- Les modèles ne sont **pas** dans l'exécutable : `tools/fetch_ocr.py` les télécharge au build (sommes SHA-256
  épinglées, deux nouvelles tentatives, cache GitHub Actions) dans `ocr/`, et `packaging/assemble.py` copie
  ce dossier à côté de `Voxpage.exe`. L'application ne télécharge rien et n'écrit rien hors de son dossier.
  `VOXPAGE_OCR` désigne un autre dossier (tests, développement).
- Le zip exclut `opencv_videoio_ffmpeg*.dll` (31 Mo, lecture vidéo inutilisée) et les moteurs d'inférence
  non livrés de RapidOCR (PyTorch, PaddlePaddle, OpenVINO, TensorRT, MNN).
- **Taille** : le zip passe de 281,8 Mo à 346,3 Mo (artefact du workflow de release), soit +64,5 Mo
  (OpenCV et onnxruntime pour l'essentiel, modèles 12,7 Mo).

## Fonctionnement

1. **Quelles pages ?** `ExtractOptions.ocr` : `"auto"` (défaut) ne lit par OCR que les pages sans texte
   exploitable, `"always"` toutes les pages choisies, `"never"` aucune. Une page n'a pas de texte exploitable
   (`pdf.py : _has_usable_text`) si l'un de ces critères est vrai :
   1. plus de 30 % des caractères n'ont pas d'équivalent Unicode ;
   2. moins de 20 caractères alphanumériques alors qu'une image couvre au moins 30 % de la page ;
   3. **couche de texte incohérente** : au moins 20 mots dont plus de la moitié relèvent du charabia
      (`pdf_text.count_tokens` : lettres isolées, ponctuation seule, mots sans voyelle, encodage cassé
      « Ã© », « � »), typique d'un OCR d'origine raté ; les sigles, nombres et points de conduite sont
      neutres. Les critères sont testés dans `tests/test_ocr.py`.
2. **Rendu** : pypdfium2, 300 dpi, niveaux de gris (la résolution est réduite au-delà de 36 millions de
   pixels).
3. **Prétraitement** (`ocr_prep.py`) : division par le fond estimé (maximum local flouté), étirement du
   contraste, puis redressement jusqu'à ±5° par maximisation de la variance du profil de projection.
4. **Moteur** (`ocr.py`) : image réduite à 2 400 px de grand côté, détection et lecture des lignes, sans seuil
   de confiance : **aucun mot à faible confiance n'est supprimé**. Corrections ciblées des confusions « I »
   (i majuscule) / « l » (L minuscule) quand la forme est impossible en français (`Ie`, `Ia`, `I’hôtel`,
   `aIors`, `ll est`), jamais sur un mot valide (`Il`, `Ici`, `Italie`), et pas pour l'anglais.
5. **Structure** : les lignes reconnues deviennent des `PageData` (un fragment par ligne, hauteur de police
   régularisée) et suivent **la même chaîne que le texte natif** : en-têtes, pieds et numéros de page
   répétés supprimés (une page OCR compte comme les autres pour la répétition), colonnes (découpage XY),
   paragraphes, titres (lignes nettement plus hautes), césures recollées par `join_lines` et les statistiques
   de mots de l'extracteur. La taille de corps est alignée sur celle des pages natives du document.
6. **Repli** : bibliothèque ou modèles absents → `ocr.available()` est faux et l'extracteur garde son
   comportement sans OCR (avertissement qui nomme les pages sans texte, jamais d'exception). Une page dont la
   lecture échoue garde son contenu natif éventuel et est signalée.
7. **Avertissements** (`Document.warnings`) : « Pages 4 à 9 : texte reconnu par OCR, des erreurs de lecture
   sont possibles. », « Page 5 : lecture peu fiable (numérisation de mauvaise qualité), vérifiez ce
   passage. » (confiance moyenne sous 0,80), « Page 6 : aucun texte reconnu par l'OCR. », « Page 7 : la
   reconnaissance de caractères a échoué, contenu ignoré. ».
8. **Progression et annulation** : fraction de 0,15 à 0,90 répartie page par page (« Reconnaissance de
   caractères, page N »), annulation vérifiée avant chaque page. `voxpage --texte` affiche maintenant les
   avertissements.

## Limites connues

- **Vitesse** : plusieurs secondes par page (voir ci-dessous) ; une page n'est pas interruptible en cours de
  lecture, l'annulation prend effet à la page suivante. La barre de progression de la conversion complète ne
  réserve que 10 % à la lecture du document, elle paraît donc lente sur un gros scan.
- **Espaces et caractères** : le moteur perd parfois une espace entre deux mots (`2024à`) ou prend un `l`
  pour un `I` hors des cas corrigés ; sur les pages réelles, 1,7 erreur d'espace et 1,6 erreur d'accent pour
  1 000 caractères. Un mot collé est lu de travers par la synthèse vocale.
- **Mise en page** : colonnes simples seulement (tableaux, encadrés, notes de bas de page ne sont pas
  reconnus comme tels ; une note de bas de page est lue dans le corps). Un paragraphe coupé par un saut de
  page est recollé comme pour le texte natif, mais une coupure de mot en tout dernier de page reste coupée.
- **Orientation** : pas de détection des pages à l'envers ou tournées de 90° ; le redressement s'arrête à ±5°.
- **Écriture** : alphabet latin uniquement (pas de grec, cyrillique, arabe, CJK) ; pas d'écriture manuscrite ;
  pas de lecture des formules.
- **Langue** : les corrections de confusions sont propres au français ; les modèles lisent aussi l'anglais.
- **Mesures** : les pages dégradées du banc sont synthétiques ; les pages réelles (12) ne couvrent que des
  imprimés français du XIXe siècle, pas de photos de pages ni de scans de documents administratifs modernes.

## Reproduire

```sh
# dans un conteneur avec réseau (modèles, pages réelles) ; Tesseract : apt install tesseract-ocr tesseract-ocr-fra
python tools/ocr_bench.py gen /tmp/bench                  # pages de vérité terrain + dégradations
python tools/ocr_bench.py fetch-real /tmp/bench           # pages réelles (Wikisource)
python tools/ocr_bench.py run /tmp/bench "rapidocr-v5@long=2400,unclip=1.6+norm" tesseract-best+norm voxpage
```

Un moteur s'écrit `famille[-variante][@réglages][+norm]` (voir `make_engine`) ; `voxpage` mesure la chaîne
complète (extracteur PDF en mode `always` sur le PDF « scanné » de chaque page). Les modèles se placent avec
`python tools/fetch_ocr.py`.

## Temps par page

- **Exécutable Windows sur un runner GitHub (4 vCPU)**, démarrage du programme, chargement des modèles et
  normalisation du texte compris (`packaging/test_release.py`) : PDF scanné de 2 pages dont 1 par OCR (image
  à 200 dpi) 4,8 s ; page dense de 1 371 caractères (scan 150 dpi) 5,8 s ; PDF natif équivalent 0,5 s. Soit
  environ 4 à 5 s par page scannée.
- **Linux, conteneur limité à 4 CPU sur une machine déjà chargée** : rendu 0,2 à 0,3 s, prétraitement 1 à
  1,6 s, moteur 5 à 6 s, soit environ 7 s par page A4 à 300 dpi.
- Le moteur travaille sur 2 400 px de grand côté quelle que soit la résolution du scan : le temps dépend du
  nombre de lignes, pas de la définition. Un livre de 300 pages scannées demande de 20 à 35 minutes.
