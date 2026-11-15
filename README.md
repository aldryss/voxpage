# Voxpage

Voxpage convertit un document (fichier PDF ou fichier texte) en fichier audio, au format MP3 ou WAV. La lecture est faite par une voix de synthèse qui fonctionne entièrement sur votre ordinateur : aucun document et aucun texte ne sont envoyés sur Internet.

Voxpage est destiné aux personnes malvoyantes ou aveugles, qui veulent écouter un document sur n'importe quel lecteur audio. Il est conçu pour s'utiliser entièrement au clavier et avec un lecteur d'écran (NVDA, JAWS, Narrateur).

Voxpage est en cours de développement. Ce guide décrit la version en préparation.

## Télécharger et lancer

Voxpage fonctionne sous Windows (64 bits). Rien n'est à installer, il n'y a pas de droits administrateur à donner et aucune connexion Internet n'est nécessaire.

1. Ouvrez la page « Releases » du dépôt GitHub du projet : https://github.com/aldryss/voxpage/releases
2. Téléchargez le fichier zip « Voxpage-<version>-win64-portable.zip ».
3. Décompressez le zip où vous voulez : sur le disque, sur le bureau ou sur une clé USB. Gardez le dossier complet, avec tout ce qu'il contient : Voxpage.exe a besoin des dossiers « _internal » et « voices » qui se trouvent à côté de lui.
4. Ouvrez le dossier « Voxpage » et double-cliquez sur Voxpage.exe.

Avertissement de Windows. Voxpage n'est pas signé numériquement, donc Windows peut afficher « Windows a protégé votre ordinateur » au premier lancement. Choisissez « Informations complémentaires », puis « Exécuter quand même ».

Vérifier le téléchargement (facultatif). Une somme SHA-256 est publiée à côté du zip. Pour la comparer, ouvrez l'invite de commandes dans le dossier du zip et tapez : certutil -hashfile Voxpage-<version>-win64-portable.zip SHA256

## Utiliser la fenêtre

Pour convertir un document :

1. Choisissez le document. Le bouton « Parcourir » (Alt+P) ou le raccourci Ctrl+O ouvre la fenêtre de choix de fichier. Vous pouvez aussi glisser le fichier sur la fenêtre. Les formats acceptés sont le PDF et le TXT.
2. Vérifiez le fichier de sortie. Voxpage propose un fichier placé à côté du document, avec le même nom et l'extension du format (par exemple « livre.mp3 »). Pour choisir un autre emplacement, utilisez « Choisir la sortie » (Alt+H). Si le fichier existe déjà, Voxpage demande s'il faut le remplacer. Avec le découpage « Un fichier par chapitre », ce bouton demande un dossier parent : le dossier de sortie prend alors le nom du document.
3. Réglez les options : voix (Alt+V), locuteur (Alt+L, seulement pour les voix à plusieurs locuteurs), vitesse (Alt+T), format (Alt+M), découpage (Alt+D), notes de bas de page (Alt+N) et reconnaissance de texte OCR (Alt+O). Les détails sont dans la section « Réglages ».
4. Pour entendre un court extrait avec la voix et la vitesse choisies, utilisez « Écouter un extrait » (Alt+U). Le bouton devient alors « Arrêter l'extrait » ; appuyez de nouveau dessus pour arrêter.
5. Lancez la conversion avec « Convertir » (Alt+C) ou Ctrl+Entrée. La barre de progression et la zone « Résultat » indiquent l'avancement.
6. Pour annuler une conversion en cours, appuyez sur Échap ou utilisez « Annuler » (Alt+A). Si vous fermez la fenêtre pendant une conversion, Voxpage demande une confirmation puis annule la conversion.
7. À la fin, la zone « Résultat » indique le ou les fichiers produits, la durée de l'audio et les avertissements éventuels. « Ouvrir le dossier » (Alt+I) ouvre le dossier qui contient les fichiers.

La zone « Résultat » est annoncée par le lecteur d'écran. Après une conversion, le focus est placé sur cette zone.

### Raccourcis clavier

- Ctrl+O : choisir le fichier à convertir.
- Ctrl+Entrée : lancer la conversion (Ctrl+Entrée sur le pavé numérique fonctionne aussi). La conversion n'est lancée que si un fichier et une voix sont choisis.
- Échap : annuler la conversion ou l'export de texte en cours.
- F1 : afficher l'aide des raccourcis.
- Tab et Maj+Tab : passer d'un contrôle à l'autre.
- Alt suivi d'une lettre : aller directement au contrôle ou au bouton dont la lettre est soulignée.

Lettres des contrôles :

- Alt+F : Fichier à convertir
- Alt+P : Parcourir
- Alt+S : Fichier de sortie
- Alt+H : Choisir la sortie
- Alt+V : Voix
- Alt+L : Locuteur
- Alt+T : Vitesse
- Alt+M : Format
- Alt+D : Découpage
- Alt+N : Notes de bas de page
- Alt+O : Reconnaissance de texte (OCR)
- Alt+U : Écouter un extrait
- Alt+C : Convertir
- Alt+A : Annuler
- Alt+X : Exporter le texte
- Alt+I : Ouvrir le dossier
- Alt+R : Résultat

## Réglages

Les réglages sont enregistrés automatiquement dans le fichier settings.json, à côté de Voxpage.exe, dès que vous les modifiez. Pour revenir aux réglages d'origine, supprimez ce fichier. Si le dossier de Voxpage ne peut pas être modifié (disque protégé en écriture), Voxpage utilise le dossier %APPDATA%\Voxpage.

Voix. Voxpage affiche les voix présentes dans le dossier « voices » au démarrage. Trois voix sont livrées : une voix française féminine, une voix française à deux locuteurs (0 : Jessica, féminine ; 1 : Pierre, masculin) et une voix anglaise britannique féminine. Le choix « Locuteur » n'apparaît que pour une voix à plusieurs locuteurs.

Vitesse. De 0,5 à 2,0, par pas de 0,1. La valeur par défaut est 1,0. Elle se règle avec le curseur, au clavier comme à la souris.

Format. MP3 (par défaut) ou WAV. Le MP3 est encodé en mono à 64 kbit/s dans la fenêtre ; le débit ne se modifie qu'en ligne de commande (option --debit). Un fichier WAV ne peut pas dépasser 4 Gio.

Découpage. « Un seul fichier » produit un fichier unique ; en MP3, les chapitres y sont repérés. « Un fichier par chapitre » crée un dossier contenant un fichier par chapitre, numéroté, et une liste de lecture (.m3u8). Les chapitres sont pris dans les signets du PDF s'il en a ; sinon, ce sont les titres du document.

Notes de bas de page. « Ignorer » (par défaut), « Lire dans le texte » ou « Lire en fin de chapitre ».

OCR. « Automatique » (par défaut) ne tente la reconnaissance de texte que sur les pages qui n'ont pas de texte exploitable. « Jamais » et « Toujours » forcent le comportement. Les pages reconnues par OCR peuvent contenir des erreurs : voir « Limites connues ».

Réglages disponibles seulement en ligne de commande ou dans settings.json : les pages à lire (option --pages), la non-annonce des titres (option --sans-titres) et les durées de pause entre phrases, paragraphes et titres.

## Vérifier le texte avant d'écouter

Le bouton « Exporter le texte » (Alt+X) enregistre dans un fichier .txt le texte qui serait lu, sans produire d'audio. Vous pouvez ainsi vérifier l'ordre de lecture, les en-têtes, les notes et les titres avant de lancer la conversion. Dans le fichier, chaque segment de texte est sur une ligne, et chaque titre de chapitre apparaît sous la forme « == Titre == ».

## Ligne de commande

La version console est voxpage-cli.exe, livrée dans le même dossier que Voxpage.exe. Voxpage.exe suivi d'arguments se comporte de la même façon.

Syntaxe :

voxpage-cli.exe ENTREE [options]

Si -o n'est pas indiqué, le fichier audio est créé à côté du document, avec l'extension du format. Les options non précisées reprennent les réglages enregistrés par l'application.

Options :

- ENTREE : le document à convertir (PDF ou TXT).
- -o SORTIE, --sortie SORTIE : fichier audio produit.
- --voix ID : identifiant de la voix (voir --liste-voix).
- --locuteur N : numéro du locuteur, pour une voix à plusieurs locuteurs.
- --vitesse V : vitesse de lecture, de 0.5 à 2.0 (défaut : 1.0).
- --format {mp3,wav} : format audio.
- --debit KBPS : débit MP3, de 8 à 320 kbit/s (défaut : 64).
- --decoupage {unique,chapitres} : un seul fichier, ou un fichier par chapitre dans un dossier.
- --pages PAGES : pages à lire, par exemple "1-10,15".
- --notes {ignorer,texte,fin} : notes de bas de page.
- --ocr {auto,jamais,toujours} : reconnaissance de texte des pages scannées.
- --sans-titres : ne pas annoncer les titres.
- --texte FICHIER.txt : exporter le texte qui serait lu, au lieu de l'audio.
- --liste-voix : afficher les voix disponibles, puis quitter.
- --diagnostic : vérifier l'installation, puis quitter.
- --silencieux : ne pas afficher la progression.
- --version : afficher la version, puis quitter.
- --help : afficher l'aide des options, puis quitter.

Codes de retour : 0 si la conversion réussit, 1 en cas d'erreur, 2 si les options sont incorrectes, 130 si la conversion est annulée (Ctrl+C).

Exemples :

Convertir un livre en MP3 avec une voix précise et une vitesse un peu plus rapide :

voxpage-cli.exe "C:\Documents\livre.pdf" -o "C:\Audio\livre.mp3" --voix fr_FR-siwis-medium --vitesse 1.1

Convertir les pages 1 à 10 et le passage 15 en WAV, avec un fichier par chapitre :

voxpage-cli.exe livre.pdf --pages "1-10,15" --format wav --decoupage chapitres

Pour afficher la liste des voix installées : voxpage-cli.exe --liste-voix

## Ajouter une voix

Une voix est un dossier placé dans le dossier « voices », à côté de Voxpage.exe. Pour ajouter une voix, déposez son dossier dans « voices » : Voxpage la proposera au prochain lancement.

Un dossier de voix contient le modèle de voix (fichier .onnx), le fichier tokens.txt, le dossier espeak-ng-data et le fichier voice.json, qui indique le nom affiché, la langue et la licence de la voix. Le détail est dans le fichier voices/README.md du dépôt. Avant de partager une voix, vérifiez que sa licence autorise la redistribution.

## Limites connues

- Tableaux : chaque tableau est annoncé (« Tableau. » au début, « Fin du tableau. » à la fin). Quand l'en-tête est identifiable, chaque ligne est lue sous la forme « en-tête : valeur » ; sinon les cellules sont lues à la suite, séparées par une pause. Un tableau très large ou complexe peut donc rester pénible à écouter.
- Graphiques et tableaux sans filets que Voxpage ne sait pas structurer (colonnes de nombres, graduations d'axes) : ces lignes sont regroupées et annoncées « Tableau ou graphique, lu tel quel. », et un avertissement indique les pages concernées dans la zone « Résultat ». Leur contenu est lu mais sans lien entre une valeur et sa colonne : vérifiez ces passages dans le document.
- Les images, schémas et pictogrammes dessinés (boutons d'un mode d'emploi, par exemple) ne sont pas du texte et ne sont pas lus. Quelques symboles courants dans le texte sont nommés (téléphone, attention, coché…).
- Sigles : ceux qui ne se prononcent pas comme un mot sont épelés lettre par lettre (« S N C F »). Les sigles qui se lisent comme un mot (ONU, OTAN, INSEE, SMIC…) sont dits tels quels ; un sigle rare qui ressemble à un mot peut être mal prononcé.
- Les sommaires sont lus sans leurs numéros de page lorsqu'ils sont reconnus avec certitude (au moins quatre lignes consécutives) ; sinon ils sont lus tels quels.
- Les mises en page de magazine complexes sont parfois mal ordonnées. Une page de garde en deux colonnes (par exemple anglais et français côte à côte) peut mêler les deux langues.
- Les formules mathématiques ne sont pas gérées.
- Pages scannées : la reconnaissance optique de caractères (OCR) est intégrée. Les pages sans texte exploitable sont reconnues automatiquement (réglage « Automatique »), ce qui prend plus de temps. La reconnaissance peut se tromper, surtout sur les scans de mauvaise qualité, les polices fantaisie ou les tableaux : un avertissement signale les pages concernées dans la zone « Résultat » ; vérifiez les passages importants.
- L'interface n'a pas encore été validée par des utilisateurs de lecteur d'écran. Vos retours sont les bienvenus : ouvrez une issue sur le dépôt GitHub du projet.

## Confidentialité

Tout est traité sur votre ordinateur. Voxpage n'envoie aucun document, ni aucun texte, sur Internet. Les voix de synthèse et les outils nécessaires sont livrés dans le zip, et le logiciel fonctionne sans connexion.

## Pour les développeurs

Les tests se lancent avec ./dev pytest -q. La commande ./dev exécute les outils dans un conteneur Docker (voir Dockerfile.dev) ; le réseau y est coupé par défaut.

L'architecture et les choix techniques sont décrits dans docs/conception.md. La procédure de publication est dans docs/release.md.

Pour ajouter un format d'entrée, écrivez un Extractor (voir voxpage/extract/base.py) et enregistrez-le ; le reste du traitement ne change pas.

## Composants et licences

Voxpage utilise notamment les composants suivants : sherpa-onnx et les voix Piper (synthèse vocale), eSpeak NG (phonémisation), pdfminer.six (lecture des PDF), PDFium (via pypdfium2, rendu et signets des PDF), wxPython (interface), LAME (encodage MP3, via lameenc) et mutagen (marques de chapitres et étiquettes).

La liste complète des composants et de leurs licences figure dans le fichier NOTICE.txt, livré dans le zip. Les licences des voix sont détaillées dans le fichier voices/README.md.
