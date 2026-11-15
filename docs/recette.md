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

### Synthèse déterministe

Les voix Piper (VITS) tirent au hasard durées et timbre (`noise_scale` 0,667, `noise_scale_w` 0,8, valeurs
recommandées par les voix) : deux conversions du même document diffèrent (durée ± 2,5 % par phrase).
sherpa-onnx 1.13 n'expose pas de graine. Le seul réglage déterministe est `noise_scale = noise_scale_w = 0`,
qui aplatit la prosodie et le timbre : c'est une perte de qualité, donc **non retenu**. Le test de vitesse a
été rendu fiable en conséquence.

## Défauts restants

### Graves

- **Tableaux et graphiques** : les valeurs des tableaux sans filets sont lues en vrac (« 2019 2020 2021…
  67 258 67 442… »), les graduations des graphiques aussi (« 950 900 850 Naissances 800… »). Pour un
  auditeur, un tableau lu en vrac est inexploitable et peut induire en erreur (valeur associée à la mauvaise
  année). Correction lourde (reconnaissance de la grille, lecture « ligne : valeur ») : hors du périmètre de la
  recette. Contournement : l'avertir dans la documentation.
- **Sigles prononcés comme des mots ou écorchés par la voix** (eSpeak NG) : « ICF » entendu « l'HICF »,
  « Lick », « l'ic fait » ; « PIB » entendu « pi B » ; « Hcéres » entendu « SER », « Cère » ; « INRIA »
  entendu « Aria ». Pas de correction sûre et générale côté normalisation (épeler tous les sigles casserait
  « ONU », « INSEE », « HAL ») ; piste : un lexique de sigles courants à épeler.
- **« Titre onze bis »** entendu « Citron se bise » avec la voix Siwis, à toutes les vitesses (enchaînement
  « titre onze » de la voix) : les intitulés de la Constitution sont mal compris avec cette voix.
- **Pictogrammes** : « appuyez sur le bouton ou jusqu'à… » (notice théière) : les boutons dessinés ne sont pas
  du texte ; la phrase dite est incomplète. Inhérent au document ; rien ne le signale à l'auditeur.

### Moyens

- Page de garde HAL bilingue (deux colonnes anglais / français) lue ligne à ligne en mélangeant les deux
  langues : les colonnes sont fondues dans un même fragment dès la construction des lignes.
- Notice théière : police à petites capitales mal encodée (« DEsCRiPTion Du PRoDuiT ») — défaut du PDF, que
  la voix prononce mais de façon hachée ; ordre de lecture des étapes autour des illustrations (étapes 4-5
  lues après la 9) ; libellés « STOP » restants (corps 3 à 5 pt).
- Tables des matières lues avec leurs numéros de page (sommaire du RPA, table finale Bibebook « III 1 5 7 11
  17… »).
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
- « GUY de maupassant », « HORS de france » : casse partielle (sans effet audible).
- « ci- dessous », « trente- cinq », « 99- 209 » : espace présente dans le PDF après le trait d'union.
- Auteur (« Hélène Thélot (Insee) ») et mentions de couverture pris pour des chapitres.
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
- Sigles (« ICF », « Hcéres », « INRIA ») → restant (voir plus haut).
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
- Ce qui reste insuffisant pour un auditeur aveugle : les tableaux et graphiques (valeurs lues en vrac,
  impossibles à rattacher à leur ligne ou colonne), les sigles écorchés par la voix, et les pictogrammes non
  dits des modes d'emploi. L'auditeur ne peut pas savoir qu'il a manqué quelque chose : à défaut de lecture
  fidèle des tableaux, Voxpage devrait au moins l'annoncer (« tableau : lecture approximative »).
- Voix : préférer les deux voix féminines (Siwis, Jessica) ; la voix masculine Pierre est nettement moins
  intelligible. À 1,5×, l'intelligibilité baisse nettement (WER + 6 à 11 points) ; 0,8× ne coûte rien.

Priorités suggérées avant une version « stable » : lecture structurée ou signalement des tableaux, lexique de
sigles à épeler, avertissement sur les pages à pictogrammes, puis une seconde recette sur d'autres genres
(manuel scolaire, presse, documents bilingues).
