# Recette de bout en bout (issue #11)

Recette menée le 15 novembre 2026 sur la branche `main` (série de commits à partir de `23f2c83`). But :
vérifier la chaîne complète PDF → texte dit → audio sur de vrais documents, la fidélité d'abord (ce qui
est dit est le texte du document, dans l'ordre, sans bruit, sans perte ni invention).

Méthode : `./dev python -m voxpage <pdf> --texte <sortie.txt>` (texte tel qu'il sera **dit**, après
normalisation), comparé au PDF (texte brut pdfium et pdfminer) : en entier pour l'Insee, la Constitution,
l'article HAL et la notice des impôts, par larges extraits pour Maupassant (début, milieu et fin), la notice
de théière et le rapport de la Cour des comptes (60 premières pages et sommaire) ; chaque défaut corrigé
dans le module responsable avec un test de non-régression ; intelligibilité vérifiée par aller-retour
synthèse → reconnaissance vocale ; conversion complète d'un document de 572 pages.

## Documents testés

| Document | Genre | Pages | Source | Licence | Dans le dépôt |
|---|---|---|---|---|---|
| Insee Première n° 2033, « Bilan démographique 2024 » | étude statistique (3 colonnes, encadrés, tableaux, graphiques) | 4 | voir `tests/corpus/reels/SOURCES.md` | Licence Ouverte 2.0 | oui (déjà) |
| Constitution du 4 octobre 1958 (Conseil constitutionnel) | texte juridique | 28 | voir `tests/corpus/reels/SOURCES.md` | texte officiel | oui (déjà) |
| Maupassant, *Contes de la bécasse*, édition Bibebook | livre (17 nouvelles), domaine public | 141 | https://applications.ac-normandie.fr/pmb/docnum/commun/pdf/maupassant_guy_de_-_contes_de_la_becasse.pdf | texte domaine public, édition CC BY-SA 3.0 | non (950 Ko) |
| Schöpfel, Prost, Jacquemin, Kergosien, Thiault, « La valorisation de HAL. Finalités, outils et process », prépublication hal-04450898, 2024 | article scientifique (LaTeX, tableaux, figures, bibliographie) | 29 | https://www.enssib.fr/bibliotheque-numerique/documents/71867-la-valorisation-de-hal.pdf | CC BY 4.0 | non |
| DGFiP, notice n° 2041-E « Impôt sur les revenus 2025, personnes fiscalement domiciliées hors de France » (Cerfa 50318#29) | courrier et notice administrative (listes numérotées, tableaux, renvois juridiques) | 16 | https://www.impots.gouv.fr/sites/default/files/formulaires/2041-e/2026/2041-e_5471.pdf | document administratif public | non |
| Riviera-et-Bar, notice d'utilisation de la théière BTA 850 « Cha Dao Expert » | mode d'emploi (pictogrammes, tableaux, étapes numérotées) | 28 | https://www.riviera-et-bar.fr/cdn/shop/files/notice_BTA850_fr.pdf | droits réservés (fabricant) | non |
| Cour des comptes, *Rapport public annuel 2023* | rapport long (document long de la recette) | 572 | https://www.vie-publique.fr/files/rapport/pdf/288563.pdf | document administratif public | non (7,6 Mo) |

Aucun document n'a été ajouté au dépôt : les défauts trouvés sont reproduits par de petits PDF générés dans
les tests (`tests/test_extract_pdf_recette.py`), ce qui garde le dépôt léger et les tests rapides.

## Défauts trouvés et corrigés

Gravité : **G** = perte ou altération du sens, **M** = bruit gênant ou fréquent, **m** = mineur.

### Extraction (`voxpage/extract/`)

| # | Gr. | Défaut (document) | Correction |
|---|---|---|---|
| 1 | G | Lettrine sur trois lignes rangée avec la 3e ligne (sa ligne de base) : les trois premières lignes de chaque conte étaient lues dans le désordre (« L paralysie des jambes… des Ravots avait été… ») (Bibebook, 17 contes sur 17) | `pdf_layout._rows_of` : une lettrine (même quand sa boîte déborde sur le retrait des lignes suivantes) prend la ligne de base de la première ligne à sa droite ; recollée au mot si celui-ci suit sans blanc |
| 2 | G | En-tête de page « 6 COUR DES COMPTES » lu à chaque page paire (250 fois) : maquette A5 centrée sur une page A4, en-tête à 17 % du haut, hors de la marge de 15 % (RPA 2023) | `pdf_furniture` : la marge se mesure aussi depuis le cadre habituel du texte (médianes des pages) |
| 3 | M | Élément de liste numéroté dont la suite revient à la marge coupé en deux blocs, et souvent en deux chapitres : « la Nouvelle- » / « Calédonie et les TAAF… » (notice 2041-E) | `pdf_structure.Builder` : une ligne pleine qui ne termine pas la phrase continue l'élément |
| 4 | M | « (SU- » / « 089) ; » : la fin d'une référence coupée prise pour un nouvel élément numéroté, dit « 89, » (article HAL) | pas de numéro après une coupure à trait d'union ni avec un zéro initial |
| 5 | M | Titres de figures numérotées (« 1. Évolution de la population… ») devenus des chapitres (Insee : 6 faux chapitres) | `demote_figure_titles` : titre numéroté parmi des titres non numérotés et suivi d'étiquettes ou de chiffres → légende (toujours lue) |
| 6 | M | Libellés d'icônes « STOP » en corps 2,7 intercalés lettre à lettre dans le texte (« l'eSaTOPu ») (notice théière, 143 occurrences, 29 restantes en corps 3 à 5) | `pdf_layout._drop_microtext` : suites d'au moins 3 caractères de moins de 3 pt écartées |
| 7 | M | Appels de note après une année ou une parenthèse pris pour des exposants (« en 2018⁶ », « acquise »)⁴ ») | `pdf_structure._exponent_base` |
| 8 | m | Fleuron décoratif lu « n » en fin de chaque conte (Bibebook) | bloc réduit à une minuscule isolée écarté |
| 8 bis | M | Chapitres mal découpés : 6 signets de premier niveau pour 572 pages, dont un chapitre de 514 pages (un fichier de ~17 h en mode « chapitres ») (RPA 2023) | `_chapter_openers` : un chapitre de plus de 80 pages est découpé au niveau de signets inférieur ; 20 chapitres |

### Normalisation (`voxpage/normalize/`)

| # | Gr. | Défaut (document) | Correction |
|---|---|---|---|
| 9 | G | « baisse de -3 % », « -84 » : le signe moins n'était pas dit (vérifié par reconnaissance : « baisse de 3 % ») ; « +1,1 % » devenait « +un virgule un » (Insee) | signe attaché : « moins » / « plus » |
| 10 | G | Signe séparé de son nombre : « (+ 5,7 %) », « inférieur de - 0,3 % », cellule « - 2,9 » (RPA 2023, des dizaines d'occurrences) | `_spaced_sign`, jamais entre deux nombres ni après un tiret de titre |
| 11 | G | « 1° ont en France leur foyer » lu « 1 degré ont… » ; « au 2° du 3 de l'article 158 » lu « 2 degrés » (notice 2041-E) | énumération en tête de phrase : « premièrement, … » ; renvoi : « au 2 du 3 » ; « 12° à l'ombre » reste « 12 degrés » |
| 12 | G | « janvier 2025e. » (référence bibliographique 2025a…2025e) lu « deux mille vingt-cinquième » (Insee) | année suivie d'une lettre de référence laissée telle quelle |
| 13 | M | « M. le curé », « M. de Villefort » : « M » épelé (vérifié par reconnaissance) (Maupassant) | « monsieur » devant le, la, de, du, des, d', l' |
| 14 | M | « (hors effet CICE, Md€) » → « Mdeuros » ; de même « M€ », « k€ » sans montant (RPA 2023) | « milliards / millions / milliers d'euros » |
| 15 | M | Appels de note entre parenthèses collés au mot : « distribués(3) », « TAAF)(1) » (notice 2041-E) | retirés comme les autres appels de note |
| 16 | M | Points de conduite des sommaires : « Délibéré........ 5 » (RPA 2023) | une pause : « Délibéré, 5 » |
| 17 | m | « 663 000 bébés » après « En 2024, » non recollé (pris pour une liste de nombres) ; la voix le lisait pourtant bien | recollé (cohérence avec les autres nombres) |
| 18 | m | « cf » sans point non développé ; « BIS » laissé en capitales dans un titre en capitales | « confer » ; « bis », « ter » parmi les mots courts |
| 19 | m | « 60-65 °C » : plage non reconnue devant °C (notice théière) | « 60 à 65 degrés Celsius » |
| 20 | M | « loi n° 88-1028 » entendu « 80.1028 » (aller-retour, Constitution) | « numéro 88 tiret 1028 », restitué exactement |

### Pipeline, synthèse (`voxpage/pipeline.py`, `voxpage/tts/`)

| # | Gr. | Défaut | Correction |
|---|---|---|---|
| 21 | M | Titre de document dit deux fois quand il suit un surtitre (« Bilan démographique 2024 » puis le titre, puis le titre encore) (Insee) | le titre n'est pas annoncé s'il figure parmi les titres de tête du chapitre |
| 22 | m | (signalé) Erreur d'extraction : « Impossible de lire « x » : « x » est protégé… » | `ExtractError` remonte telle quelle |
| 23 | m | (signalé) `extract_text` : « == Titre == » puis le titre répété | la ligne « == Titre == » tient lieu de l'annonce du titre |
| 24 | M | (signalé) Segment muet ignoré silencieusement | un passage porteur de texte sans son produit est cité dans les avertissements du résultat ; vérifié sur les 320 segments courts (≤ 12 caractères) des documents de la recette : aucun n'est muet |
| 25 | m | (signalé) `test_speed_shortens_audio` instable | médianes de 5 tirages, seuils à plus de 4 écarts types ; bornage de la vitesse testé sans moteur |

Messages d'erreur vérifiés (CLI, code de sortie 1, aucun fichier laissé) : PDF vide « ne contient aucun
texte », PDF protégé « est protégé par un mot de passe : Voxpage ne peut pas l'ouvrir. Retirez la protection
puis réessayez. », PDF corrompu ou tronqué « n'est pas un PDF valide ou il est endommagé », PDF entièrement
scanné « ne contient pas de texte lisible : il s'agit probablement d'un document scanné… ».

### Derniers défauts de fidélité avant la première version (issue #12)

| # | Gr. | Défaut | Correction |
|---|---|---|---|
| 26 | G | Sigles écorchés par la voix : « ICF » → « isof », « SNCF » → « cent soft », « PIB » → « Puy B », « EDF » → « d'œufs » | `normalize/acronyms.py` : un sigle de 2 à 5 majuscules qui ne se prononce pas comme un mot est épelé, lettres séparées par une espace (« I C F »). Sont laissés tels quels : les acronymes de la liste « se lit comme un mot » (ONU, OTAN, UNESCO, INSEE, CNIL, SMIC, OVNI, SIDA, NASA, URSSAF…), les chiffres romains valides, les mots ordinaires en capitales (NON, STOP, ATTENTION…), les formes prononçables (deux syllabes consonne + voyelle, quatre lettres ou plus : NOTE, SIDA), les mots collés à un chiffre ou à un « s » (UE27, ONGs). En cas de doute, épeler. « S.N.C.F. » → « S N C F » ; « Hcéres » → « H C E R E S » |
| 27 | G | Tableaux : rien n'indiquait à l'auditeur qu'un tableau commence ou finit ; valeurs lues en vrac | blocs `table` : « Tableau. » avant, « Fin du tableau. » après (anglais : « Table. » / « End of table. ») ; si la première ligne est un en-tête sûr (au moins deux libellés ou années, aucune valeur numérique, lignes de même largeur), chaque ligne est dite « en-tête : valeur » ; sinon les cellules se suivent séparées par une pause |
| 28 | G | Colonnes de nombres sans filets et graduations de graphiques mêlées au corps du texte (« 950 900 850 Naissances 800… ») | `extract/pdf_tabular.py` : au moins 6 lignes consécutives très courtes, majoritairement numériques (au moins 4 lignes de nombres) et alignées en colonne forment un bloc `table` marqué `loose`, dit « Tableau ou graphique, lu tel quel. … Fin du tableau ou graphique. » ; avertissement « Pages 1 à 3 : tableaux ou graphiques lus sans structure. » ; aucun texte supprimé |
| 29 | M | Sommaires lus avec points de conduite et numéros de page (« Délibéré, 5 ») | au moins 4 lignes consécutives « Titre ……… 12 » (ou « Titre 12 » avec numéros croissants alignés à droite, qui ne forment pas une numérotation 1, 2, 3…) : un élément de liste par titre, sans points ni numéro ; en dessous de 4 lignes, ou si les numéros ne se suivent pas dans l'ordre, rien n'est touché |
| 30 | m | « GUY de maupassant », « HORS de france » : remise en casse incohérente | prénoms courts reconnus (GUY → Guy), « hors » mot courant, mots prononçables de quatre lettres ramenés en minuscules, nom propre après une particule dans un nom court : « Guy de Maupassant », « Hors de France » ; les sigles et chiffres romains restent en capitales |
| 31 | M | Pictogrammes et symboles non dits (☎, ✉, ⚠, ✓, ✗, ★, ►) | nommés : « téléphone », « courrier », « attention », « coché », « croix », « étoile », « flèche » (anglais : telephone, mail, warning, checked, cross, star, arrow) ; ✓ et ✔ en tête d'une ligne de texte restent des puces, en tableau ce sont des valeurs ; fleurons et lignes purement décoratives (❦, ✦ ✦ ✦, * * *) toujours retirés |
| 32 | M | Voix par défaut : l'interface choisissait la première voix par ordre alphabétique, donc la voix anglaise (`en_GB`) sans réglage enregistré | `tts.base.default_voice` : sans réglage, Siwis (français) ou Cori (anglais) selon la langue du document, vitesse 1,0, locuteur 0 ; dans `fetch_voices.py` et `voice.json`, Jessica reste le locuteur 0 d'UPMC, avant Pierre (conservé) |
| 33 | G | Sigles et mots que la voix dit mal malgré l'épellation (EDF, CDI, UE, INRIA « Aria »…), sans recours pour l'utilisateur | dictionnaire de prononciation « écrit = dit » (`normalize/lexicon.py`, issue #13) : dictionnaire livré par langue (15 entrées françaises mesurées, voir ci-dessous) et dictionnaire de l'utilisateur (`prononciations.txt`, dialogue « Prononciations », `--prononciations`) ; le dit n'est retraité par aucune règle de sigle, de nombre ou de casse |

Mesure des sigles (issue #12). Phrase « Selon X, les chiffres ont baissé cette année. », 30 sigles français
courants à épeler (ICF, PIB, SNCF, Hcéres, CNRS, RATP, EDF, TVA, PDG, CDD, CDI, RSA, CAF, DGFIP, FMI, OMS, UE, USA,
SAS, HLM, TGV, RER, ADN, IRM, PME, CGT, PSG, BNP, AFP, IUT), deux synthèses chacun, 1×, transcrits par Whisper
small ; compté juste si la transcription contient les lettres du sigle :

| Voix | Avant (sigle brut) | Après (lettres séparées) |
|---|---|---|
| `fr_FR-siwis-medium` | 15/60 (25 %) | 39/60 (65 %) |
| `fr_FR-upmc-medium`, Jessica | 34/60 (57 %) | 44/60 (73 %) |

Écritures essayées (30 sigles, deux voix, une synthèse chacune ; le bruit de la synthèse et de la
reconnaissance est de ±3) : sigle brut 9 et 18 sur 30 ; lettres séparées par une espace 21 et 24 ; noms de lettres
écrits (« i cé effe ») 14 et 15 ; lettres séparées par des virgules 17 et 26 ; lettres pointées (« I. C. F. ») 1
et 0 ; avec trait d'union, minuscules, espaces insécables ou fines : équivalentes aux espaces simples (20 à 23).
Les espaces simples sont retenues (la plus simple, la meilleure pour Siwis, la voix par défaut). Restent mal
dits (« EDF » entendu « ODF », « CDI » « sédis », « UE » « eux », « HCERES »), à cause de lettres que les voix
prononcent mal isolées (E, U) : à écouter, pas de correction sûre. Les acronymes lus comme des mots ne sont pas
mesurés ici (la reconnaissance entend des homophones : « OTAN » → « autant ») ; INRIA, lu comme un mot, reste
entendu « Aria ».

### Dictionnaire de prononciation livré (issue #13)

Méthode (`tools/roundtrip.py --verifier-entrees`). Pour chaque écrit, la phrase est dite sans dictionnaire (ce
que fait l'application avant l'issue : sigle épelé « E D F », ou mot laissé tel quel pour INRIA, CNES, BAC…) puis
avec chaque « dit » candidat, par les voix Siwis et Jessica (`fr_FR-upmc-medium`, locuteur 0), vitesse 1,0, deux
synthèses par phrase et par voix, puis transcription Whisper small. Une synthèse est comptée juste si la
transcription contient les lettres de l'écrit (accents, espaces et ponctuation ignorés : « E.D.F. » = « edf »).
Le bruit de la synthèse et de la reconnaissance est important (± 3 sur 8) : une entrée n'est retenue que si elle
gagne au moins 3 réussites sur 8 à la première mesure **et** se confirme sur trois autres phrases (12 essais).

1. Première mesure : 75 candidats (63 sigles français usuels, dont les 30 de l'issue #12, et 12 mots ou sigles lus
   comme des mots : INRIA, INRAE, HAL, CNES, BAC, PACS…), 3 à 5 écritures chacun (noms de lettres séparés par des
   espaces, des virgules ou des traits d'union ; variantes phonétiques pour les mots), phrases « Selon X, les
   chiffres ont baissé cette année. » et « Le rapport de X a été publié hier. », 8 essais par écriture.
2. Confirmation des 26 meilleurs (gain d'au moins 2) sur trois autres phrases (« La direction de X a répondu aux
   questions. », « X est mentionné dans la note de service. », « Nous avons contacté X la semaine dernière. »),
   12 essais. 14 entrées confirmées ; SNCF (– 7 sur 12 : la première mesure était un coup de chance), DRH, BNP, CAF,
   CEA, AFNOR, DGFIP, OCDE, PACS… écartés.
3. EDF, UE et Hcéres (cités plus haut) : 6 écritures de plus chacun sur cinq phrases (20 essais). UE gagne avec
   « u euh » (9 → 14 sur 20, puis 9 → 12 sur 18 sur trois autres phrases, 18 → 26 sur 38 en tout). EDF : aucune
   écriture ne dépasse l'épellation (10 sur 20 ; « euh dé effe » 8, « e, dé, effe » 6, « e-d-f » 5, « eu-dé-effe »
   0). Hcéres : aucune écriture ne dépasse « H C E R E S » (3 sur 20 ; les autres 0) : pas d'entrée, la voix
   confond les lettres E et la reconnaissance transcrit mal ce nom.

Entrées livrées dans `prononciations-fr.txt` (15), réussites sur les essais de confirmation seuls (ils n'ont pas
servi à choisir l'écriture) :

| Écrit | Dit | Avant | Après |
|---|---|---|---|
| INRIA | inn ria | 0/12 | 11/12 |
| CNES | cnès | 0/12 | 6/12 |
| BAC | bak | 3/12 | 11/12 |
| CDI | cé-dé-i | 5/12 | 12/12 |
| CCI | cé-cé-i | 3/12 | 10/12 |
| CNRS | cé-enne-erre-esse | 6/12 | 12/12 |
| CAPES | kapesse | 2/12 | 5/12 |
| CERN | sèrne | 6/12 | 9/12 |
| QR | ku-erre | 6/12 | 10/12 |
| USB | u-esse-bé | 7/12 | 10/12 |
| IA | i, a | 6/12 | 10/12 |
| EHESS | e ache e esse esse | 0/12 | 4/12 |
| PIB | pé i bé | 7/12 | 10/12 |
| IUT | i, u, té | 6/12 | 8/12 |
| UE | u euh | 18/38 | 26/38 |
| **Total** | | **75/206 (36 %)** | **154/206 (75 %)** |

Limites : Whisper small n'est pas un auditeur (il rétablit parfois le mot attendu d'après le contexte) et les
écritures retenues ne sont pas toujours naturelles à lire (« inn ria », « cnès »), mais elles sont celles que la
voix dit le mieux. Les entrées sont sensibles à la casse (« BAC » mais pas « bac ») ; les sigles absents restent
épelés par les règles de #12. Le dictionnaire anglais est livré vide : aucune entrée n'a été mesurée (le
modèle de reconnaissance de l'outil est réglé sur le français). Les sigles que les voix disent le plus mal restent
EDF, Hcéres, ICF, SARL, ENS, ADEME, PACS : l'utilisateur peut les corriger lui-même dans le dialogue « Prononciations »
(par exemple `EDF = euh dé effe` si cette écriture lui convient mieux).

### Synthèse déterministe

Les voix Piper (VITS) tirent au hasard durées et timbre (`noise_scale` 0,667, `noise_scale_w` 0,8, valeurs
recommandées par les voix) : deux conversions du même document diffèrent (durée ± 2,5 % par phrase).
sherpa-onnx 1.13 n'expose pas de graine. Le seul réglage déterministe est `noise_scale = noise_scale_w = 0`,
qui aplatit la prosodie et le timbre : c'est une perte de qualité, donc **non retenu**. Le test de vitesse a
été rendu fiable en conséquence.

## Défauts restants

### Graves

- **Tableaux sans structure** : les zones numériques repérées (colonnes de valeurs, graduations) sont annoncées et
  signalées, mais leurs valeurs sont lues en colonne sans lien avec les en-têtes (« 2019 2020 2021… » puis
  « 67 258 67 442… »). Un tableau structuré (filets ou colonnes nettes) est lu « en-tête : valeur » seulement si
  la première ligne est un en-tête sûr ; sinon les cellules se suivent. Reconnaissance de la grille des tableaux
  sans filets : non faite.
- **Sigles** : l'épellation corrige la plupart des cas (Siwis 25 % → 65 %, Jessica 57 % → 73 %) mais certaines
  lettres isolées restent mal dites (E, U). Depuis #13, le dictionnaire de prononciation corrige INRIA (« Aria »
  → « inn ria »), CDI, UE… (36 % → 75 % sur 15 entrées) et laisse à l'utilisateur les autres (EDF, Hcéres, SARL…).
  Un sigle rare qui ressemble à un mot (voyelles et consonnes alternées, quatre lettres ou plus) est lu tel quel.
- **« Titre onze bis »** entendu « Citron se bise » avec la voix Siwis, à toutes les vitesses (enchaînement
  « titre onze » de la voix) : les intitulés de la Constitution sont mal compris avec cette voix.
- **Pictogrammes dessinés** : « appuyez sur le bouton ou jusqu'à… » (notice théière) : les boutons dessinés ne sont
  pas du texte ; la phrase dite est incomplète. Inhérent au document ; rien ne le signale à l'auditeur (seuls les
  symboles Unicode sont nommés).

### Moyens

- Page de garde HAL bilingue (deux colonnes anglais / français) lue ligne à ligne en mélangeant les deux
  langues : les colonnes sont fondues dans un même fragment dès la construction des lignes (non traité : risque
  de régression sur la mise en page).
- Notice théière : police à petites capitales mal encodée (« DEsCRiPTion Du PRoDuiT ») — défaut du PDF, que
  la voix prononce mais de façon hachée ; ordre de lecture des étapes autour des illustrations (étapes 4-5
  lues après la 9) ; libellés « STOP » restants (corps 3 à 5 pt).
- Tables des matières : les sommaires de quatre lignes consécutives ou plus sont nettoyés ; la table finale
  Bibebook (« III 1 5 7 11 17… », titres et numéros sur des lignes séparées) et les sommaires dont une entrée
  s'étale sur deux lignes ne sont pas reconnus (non revérifié sur le document) et sont lus tels quels.
- Paragraphes numérotés en gras pris pour des titres : la notice 2041-E fait 48 chapitres (sans perte de
  texte ; un fichier par chapitre en mode « chapitres »).
- Voix « Pierre » (`fr_FR-upmc-medium`, locuteur 1) nettement moins intelligible que les deux voix féminines
  (voir l'aller-retour).
- Mémoire : ≈ 1,1 Go pendant la synthèse (moteur ONNX, segments jusqu'à 400 caractères), quelle que soit
  la longueur du document ; à surveiller sur les PC modestes (4 Go). Piste : segments plus courts ou
  désactivation de l'arène mémoire d'onnxruntime, à mesurer.
- Vitesse 0,8× : l'audio ne dure que 11 % de plus qu'à 1× (attendu : 25 %) ; 1,5× : 25 % de moins (attendu :
  33 %). Le réglage agit sur la durée des phonèmes, pas sur les pauses.

### Mineurs

- Mots absents du PDF lui-même (fin du premier mot de chaque conte Bibebook, en police sans table Unicode :
  « L des Ravots » pour « Le vieux baron des Ravots », « ML une dame » pour « Mme Lefèvre était une dame ») :
  rien à faire sans OCR ; l'auditeur entend une phrase tronquée, mais l'avertissement « Page 7 : 11
  caractères illisibles ignorés » est donné pour chaque page concernée.
- Titre de nouvelle dit sous deux formes (« I La bécasse », signet, puis « La bécasse », titre de la page).
- Fleuron collé en fin de paragraphe (« depuis 2002. l », Insee).
- « ci- dessous », « trente- cinq », « 99- 209 » : espace présente dans le PDF après le trait d'union.
- Auteur (« Hélène Thélot (Insee) ») et mentions de couverture pris pour des chapitres (non traité).
- Valeurs de tableaux suffixées (« 646,0p », « 68 246p ») non normalisées.

## Aller-retour synthèse → reconnaissance

Outil : `tools/roundtrip.py` (développement uniquement, jamais livré). 23 phrases tirées des documents
ci-dessus (nombres décimaux, pourcentages, dates, téléphone, sigles, noms propres, abréviations, adresse web,
énumération juridique, titre en capitales), normalisées comme dans l'application, synthétisées par chaque voix
française et chaque locuteur, transcrites par Whisper small (sherpa-onnx, fp32) ; WER après minuscules, sans
ponctuation, nombres en lettres des deux côtés.

| Voix | 1× | 0,8× | 1,5× |
|---|---|---|---|
| `fr_FR-siwis-medium` (féminine) | 11,9 % | 11,6 % | 17,7 % |
| `fr_FR-upmc-medium`, locuteur 0 Jessica (féminine) | 12,3 % | 11,4 % | 22,9 % |
| `fr_FR-upmc-medium`, locuteur 1 Pierre (masculine) | 14,3 % | 17,9 % | 21,8 % |

WER sur 23 phrases (≈ 520 mots) par voix et par vitesse, après les corrections de cette recette. Avant les
corrections de normalisation (même outil, voix à 1×) : 11,2 % / 10,8 % / 14,5 % — les chiffres ne baissent
pas parce que le WER est dominé par les erreurs du modèle de reconnaissance sur les noms propres et les sigles,
et que la synthèse est aléatoire d'une exécution à l'autre ; les corrections, elles, ont été vérifiées phrase
par phrase (ci-dessous).

Lecture : le WER mesure surtout les limites de Whisper small sur les noms propres et sigles (« Coulhon et
Larrouturou » → « Coulomb et la route Urou ») ; il reste utile pour repérer ce que la voix dit mal.
Erreurs imputables à la voix ou au texte dit, et suites données :

- « -3 % » dit « 3 % » (signe perdu) → corrigé (#9) ; « M. le curé » dit « M le curé » → corrigé (#13) ;
  « 1° » dit « 1 degré » → corrigé (#11) ; « n° 88-1028 » entendu « 80.1028 » → corrigé (#20).
- Vitesse 1,5× : le WER monte de 6 à 11 points (fins de phrases avalées, « 40 ans » entendu « 41 ») ; 0,8×
  équivaut à 1× pour les voix féminines.
- Sigles (« ICF », « Hcéres », « INRIA ») → épelés (#26), voir la mesure avant/après ; INRIA reste dit comme un mot.
- Voix Pierre : « un virgule » entendu « un vieil gul », « par femme » entendu « barf femmes » — diction
  de la voix elle-même, pas de la normalisation.

Le détail par phrase (texte dit / transcription) se régénère avec
`./dev python tools/roundtrip.py --rapport sortie.md`.

## Document long

Cour des comptes, *Rapport public annuel 2023*, 572 pages, converti entièrement en MP3 par chapitres
(`--decoupage chapitres`, voix par défaut `fr_FR-siwis-medium`, 64 kbit/s), sur le serveur de développement
(12 cœurs, partagés avec un autre agent qui faisait tourner des mesures OCR au même moment : les temps sont
pessimistes).

| Mesure | Valeur |
|---|---|
| Temps total (extraction + synthèse + encodage) | 103,7 min, dont ≈ 4 min de lecture du PDF |
| Facteur temps réel | 9,8× (4 fils de synthèse) |
| Mémoire maximale (RSS) | 1 173 Mo ; extraction seule (`--texte`) : 113 Mo |
| Sortie | 6 fichiers MP3 + liste `.m3u8`, 487,9 Mo (64 kbit/s) |
| Durée audio | 16 h 55 min (1 015 min 24 s ; durée annoncée par la CLI = somme des durées des MP3) |
| Code de sortie, avertissements | 0, aucun |

La mémoire n'augmente pas avec la longueur du document : elle atteint ≈ 1 Go dès les premières phrases
longues (tampons du moteur ONNX pour des segments jusqu'à 400 caractères) puis reste stable (mesuré sur 600
phrases du rapport : 1 033 Mo à la 100e, 1 060 Mo à la 500e). L'audio est bien écrit en flux.

Cette conversion a été faite avant la correction #8 bis : 6 chapitres, dont un de 514 pages (≈ 15 h dans un
seul fichier). Avec la correction, le même document donne 20 chapitres.

Annulation en cours de route (Ctrl+C pendant la synthèse du chapitre 3 de *Contes de la bécasse*, mode
« chapitres ») : « Conversion annulée. », code 130, dossier de sortie et fichiers partiels supprimés, aucun
résidu.

## Avis

**Oui pour une première version publique annoncée comme préliminaire, à condition d'en documenter les
limites ; non pour des documents riches en tableaux et en sigles.**

- Sur la prose (Constitution, Maupassant, article HAL, corps de la notice des impôts et du rapport de la
  Cour des comptes), après corrections, la relecture du texte dit n'a révélé ni perte de texte ni inversion
  d'ordre ni invention (hors pages de garde et tableaux) : en-têtes, pieds, numéros de page, césures et
  appels de note sont traités ; les nombres, dates, pourcentages, signes et abréviations courantes sont dits
  correctement. La plupart des
  défauts graves trouvés (lettrines, signes moins, « 1° », en-têtes d'une maquette centrée) étaient
  fréquents dans leur genre de document : d'autres de ce type existent sûrement dans des genres non testés.
- Ce qui reste insuffisant pour un auditeur aveugle : les tableaux sans filets et les graphiques (désormais
  annoncés et signalés dans les avertissements, mais valeurs encore lues sans rattachement à leur colonne), les
  sigles que les voix prononcent encore mal malgré l'épellation, et les pictogrammes dessinés des modes d'emploi.
  L'auditeur sait au moins qu'un tableau ou un graphique commence et finit.
- Voix : préférer les deux voix féminines (Siwis, Jessica) ; la voix masculine Pierre est nettement moins
  intelligible. À 1,5×, l'intelligibilité baisse nettement (WER + 6 à 11 points) ; 0,8× ne coûte rien.

Priorités suggérées avant une version « stable » : reconnaissance de la grille des tableaux sans filets, avertissement
sur les pages à pictogrammes, page de garde bilingue, puis une seconde recette sur d'autres genres (manuel
scolaire, presse, documents bilingues).
