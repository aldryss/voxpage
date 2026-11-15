"""Textes français de vérité terrain du banc d'essai OCR (tools/ocr_bench.py).

Textes originaux rédigés pour le banc : accents, majuscules accentuées, œ/æ, ç, apostrophes droites et
courbes, guillemets « », tirets de dialogue, nombres, pourcentages, dates, sigles, ponctuation variée.
Chaque entrée : identifiant, police (Times-Roman, Helvetica, Courier), corps, colonnes, titre, paragraphes.
"""

TEXTS = [
    {
        "id": "roman-1",
        "font": "Times-Roman",
        "size": 12,
        "title": "Chapitre premier",
        "paragraphs": [
            "Il pleuvait depuis trois jours sur la vallée de l’Ill, et les chemins étaient devenus des "
            "ruisseaux de boue où s’enfonçaient les charrettes. Le vieux Mathias, qui n’avait pas quitté sa "
            "ferme depuis la Toussaint, regardait par la fenêtre l’eau gonfler les fossés. « Elle montera "
            "encore cette nuit, dit-il à sa fille. Va chercher les bêtes avant qu’il ne soit trop tard. »",
            "Hélène posa son tricot, enfila un manteau de laine et sortit sans répondre. Dans l’étable, les "
            "vaches s’agitaient ; l’une d’elles, la plus âgée, refusait de se lever. Il fallut la tirer, la "
            "pousser, lui parler doucement, comme on parle à une vieille amie. Quand elles furent enfin "
            "toutes à l’abri dans le grenier à foin, la nuit tombait déjà, et le vent du nord se mit à "
            "souffler en rafales.",
            "— Tu as vu le pont ? demanda Mathias en la voyant rentrer, trempée jusqu’aux os.",
            "— Il tient encore, père. Mais l’eau passe presque par-dessus. Si elle monte de quarante "
            "centimètres, nous serons coupés du village jusqu’à lundi, peut-être mardi.",
            "Le vieil homme hocha la tête. Il avait connu pire, en 1947 notamment, quand la crue avait "
            "emporté la moitié du moulin et deux maisons de la rue Haute. Mais il avait alors trente-cinq "
            "ans, des bras solides et un frère pour l’aider. Aujourd’hui, il n’avait plus que sa fille, "
            "ses rhumatismes et un vieux chien à moitié sourd qui dormait près du poêle.",
        ],
    },
    {
        "id": "journal-1",
        "font": "Helvetica",
        "size": 10,
        "title": "Le budget de la commune adopté à une courte majorité",
        "paragraphs": [
            "Le conseil municipal de Villeneuve-sur-Aube a adopté, jeudi soir, le budget 2025 par 14 voix "
            "contre 11. Le total s’élève à 18,7 millions d’euros, dont 4 250 000 € consacrés aux "
            "investissements, soit une hausse de 6,3 % par rapport à l’an dernier. L’opposition a dénoncé "
            "« un budget sans ambition » et réclamé, en vain, une baisse de la taxe foncière, fixée à "
            "37,52 %.",
            "Parmi les projets retenus figurent la rénovation de l’école Jules-Ferry (1 200 000 €), "
            "l’aménagement de la place de la Mairie et la création d’une piste cyclable de 3,4 km reliant "
            "le centre-ville à la zone d’activités. « Nous tenons nos engagements, a déclaré le maire, "
            "Mme Sophie Delcourt, sans augmenter les impôts ni creuser la dette. » L’endettement de la "
            "commune reste en effet stable, à 812 € par habitant.",
            "Les élus ont également voté une subvention de 35 000 € à l’association « Les Amis du "
            "patrimoine », chargée de restaurer la chapelle Saint-Éloi, classée monument historique en "
            "1987. Les travaux, estimés à 410 000 €, devraient débuter en septembre et durer dix-huit mois. "
            "La séance, ouverte à 20 h 30, s’est achevée peu après minuit.",
        ],
    },
    {
        "id": "science-1",
        "font": "Times-Roman",
        "size": 11,
        "title": "La photosynthèse",
        "paragraphs": [
            "La photosynthèse est le processus par lequel les plantes, les algues et certaines bactéries "
            "transforment l’énergie lumineuse en énergie chimique. Elle se déroule dans les chloroplastes, "
            "des organites riches en chlorophylle. À partir du dioxyde de carbone (CO2) et de l’eau, la "
            "cellule synthétise du glucose et libère de l’oxygène : c’est à ce mécanisme que nous devons "
            "environ 21 % de l’atmosphère terrestre.",
            "On distingue classiquement deux phases. La phase claire, qui exige de la lumière, a lieu dans "
            "les membranes des thylakoïdes ; elle produit de l’ATP et du NADPH. La phase sombre, ou cycle "
            "de Calvin, se déroule dans le stroma et utilise ces molécules pour fixer le carbone. Le "
            "rendement théorique maximal est de l’ordre de 4,6 % pour les plantes en C3, et peut dépasser "
            "6 % chez les plantes en C4, comme le maïs ou la canne à sucre.",
            "Les premières expériences datent du XVIIIe siècle : en 1771, Joseph Priestley observe qu’une "
            "plante enfermée avec une bougie éteinte « rétablit » l’air vicié. Jan Ingenhousz montre "
            "ensuite, en 1779, que la lumière est indispensable. Il faudra attendre les travaux de "
            "Melvin Calvin, récompensés par le prix Nobel de chimie en 1961, pour comprendre le détail des "
            "réactions. Aujourd’hui encore, l’efficacité de la photosynthèse inspire la recherche sur les "
            "cellules solaires artificielles.",
        ],
    },
    {
        "id": "lettre-1",
        "font": "Times-Roman",
        "size": 12,
        "title": "Paris, le 14 mars 1912",
        "paragraphs": [
            "Ma chère Marguerite,",
            "Je vous écris à la hâte, car le courrier part dans une heure et je ne voudrais pas que ma "
            "lettre manque le train de Lyon. Vous me demandez des nouvelles de notre voyage : il fut long, "
            "fatigant, "
            "mais en somme assez agréable. Nous avons quitté Marseille le 2, par un temps superbe, et nous "
            "sommes arrivés à Alger après trente-six heures de traversée. Maman a été souffrante la première "
            "nuit ; moi, pas du tout, ce qui m’a valu les plaisanteries de mon frère.",
            "La ville est charmante : des rues blanches qui montent vers la Casbah, des balcons fleuris, des "
            "marchands d’oranges et de dattes à chaque coin. Nous logeons dans une pension tenue par une "
            "veuve alsacienne, Mme Hirtz, qui nous traite comme ses enfants et prépare, le dimanche, une "
            "choucroute dont vous me diriez des nouvelles ! Les journées passent trop vite : promenades le "
            "matin, sieste l’après-midi, lecture le soir. J’ai déjà fini les deux volumes que vous m’aviez "
            "prêtés.",
            "Écrivez-moi vite, je vous en prie, et dites à votre père que je n’oublie pas sa commission. "
            "Je vous embrasse de tout cœur, ainsi que votre sœur Geneviève.",
            "Votre amie dévouée, Jeanne.",
        ],
    },
    {
        "id": "cuisine-1",
        "font": "Helvetica",
        "size": 11,
        "title": "Tarte aux pommes à l’alsacienne",
        "paragraphs": [
            "Préparation : 30 minutes. Cuisson : 45 minutes. Pour 6 personnes.",
            "Ingrédients : 250 g de farine, 125 g de beurre, 1 pincée de sel, 5 cl d’eau froide, 5 pommes "
            "(des reinettes de préférence), 2 œufs, 20 cl de crème fraîche, 80 g de sucre en poudre, "
            "1 sachet de sucre vanillé et un peu de cannelle.",
            "Étalez la pâte au rouleau sur un plan fariné, puis garnissez-en un moule de 28 cm de diamètre "
            "préalablement beurré. Piquez le fond à la fourchette. Pelez les pommes, ôtez les pépins et "
            "coupez-les en fines lamelles ; disposez-les en rosace, serrées les unes contre les autres.",
            "Dans un saladier, battez les œufs avec la crème, le sucre et la vanille. Versez cet appareil "
            "sur les pommes, saupoudrez de cannelle et enfournez à 180 °C (thermostat 6). La tarte est cuite "
            "lorsque la crème est dorée et légèrement gonflée. Laissez tiédir avant de démouler : elle se "
            "déguste aussi bien chaude que froide, avec une boule de glace à la vanille.",
        ],
    },
    {
        "id": "droit-1",
        "font": "Times-Roman",
        "size": 11,
        "title": "Conditions générales de vente",
        "paragraphs": [
            "Article 1er. — Objet. Les présentes conditions régissent les ventes conclues entre la société "
            "Lumière & Fils, dont le siège est situé au 24, rue de la République, 69002 Lyon, ci-après "
            "« le vendeur », et toute personne physique ou morale, ci-après « l’acheteur ».",
            "Article 2. — Prix. Les prix sont indiqués en euros, toutes taxes comprises (TVA à 20 %). Le "
            "vendeur se réserve le droit de les modifier à tout moment ; le prix applicable est celui en "
            "vigueur au jour de la commande. Les frais de livraison, de 7,90 € pour toute commande "
            "inférieure à 75 €, sont offerts au-delà.",
            "Article 3. — Droit de rétractation. Conformément aux articles L. 221-18 et suivants du code de "
            "la consommation, l’acheteur dispose d’un délai de quatorze jours à compter de la réception "
            "pour retourner l’article, sans avoir à justifier de motifs ni à payer de pénalités. Le "
            "remboursement intervient dans un délai maximal de 14 jours après la réception du retour.",
            "Article 4. — Litiges. À défaut d’accord amiable, tout litige relèvera de la compétence des "
            "tribunaux de Lyon, même en cas de pluralité de défendeurs ou d’appel en garantie.",
        ],
    },
    {
        "id": "dialogue-1",
        "font": "Times-Roman",
        "size": 12,
        "title": "",
        "paragraphs": [
            "— Vous êtes en retard, dit le commissaire sans lever les yeux de son dossier.",
            "— Le métro, répondit l’inspecteur Garnier en s’asseyant. Une panne à Châtelet, comme chaque "
            "semaine. J’ai fini à pied.",
            "— Peu importe. Écoutez-moi bien : la victime s’appelait Étienne Vasseur, soixante-deux ans, "
            "ancien notaire. On l’a retrouvé hier matin, vers 7 h 15, dans son bureau du boulevard "
            "Haussmann. Pas d’effraction, rien de volé, et pourtant la porte du coffre était grande ouverte.",
            "— Un proche ? s’enquit Garnier.",
            "— Une nièce, Clémence, et un associé, Maître Roux, qui prétend n’avoir rien entendu. J’ai "
            "interrogé les voisins : ils parlent d’une dispute vers 22 heures, un « éclat de voix » selon "
            "l’un d’eux. Mais personne n’a vu personne, bien entendu.",
            "L’inspecteur sourit. « Bien entendu », répéta-t-il. Il ouvrit son carnet, nota quelques mots, "
            "puis demanda : « Et l’heure du décès ? Le médecin légiste l’a-t-il précisée ? »",
            "— Entre minuit et deux heures du matin. Autrement dit, après la dispute. Voilà qui change tout, "
            "n’est-ce pas ?",
        ],
    },
    {
        "id": "histoire-1",
        "font": "Times-Roman",
        "size": 11,
        "title": "Les cathédrales gothiques",
        "paragraphs": [
            "Apparu au milieu du XIIe siècle en Île-de-France, l’art gothique se caractérise par l’emploi "
            "systématique de l’arc brisé, de la voûte sur croisée d’ogives et de l’arc-boutant. Ces "
            "innovations permettent d’élever des édifices d’une hauteur inédite tout en perçant les murs de "
            "vastes baies que l’on garnit de vitraux. La basilique de Saint-Denis, reconstruite sous "
            "l’abbé Suger vers 1140, en est généralement considérée comme le premier exemple.",
            "Notre-Dame de Paris, commencée en 1163 sous l’épiscopat de Maurice de Sully, s’élève à "
            "33 mètres sous voûte ; Amiens atteint 42,3 mètres, Beauvais, en 1272, près de 48 mètres, avant "
            "que le chœur ne s’effondre en 1284. Les chantiers durent souvent plus d’un siècle, mobilisent "
            "des centaines d’ouvriers — tailleurs de pierre, charpentiers, verriers, forgerons — et "
            "dépendent largement des dons des fidèles et de la générosité des évêques.",
            "Au XIXe siècle, Viollet-le-Duc dirige la restauration de nombreux monuments. Son travail, "
            "parfois critiqué pour ses libertés avec l’original, a toutefois sauvé de la ruine des "
            "édifices comme Vézelay ou Carcassonne. L’incendie du 15 avril 2019 à Notre-Dame a rappelé à "
            "quel point ce patrimoine demeure fragile : la flèche, ajoutée en 1859, s’est effondrée en "
            "quelques minutes.",
        ],
    },
    {
        "id": "technique-1",
        "font": "Helvetica",
        "size": 10,
        "title": "Notice d’utilisation : lave-linge LV-742",
        "paragraphs": [
            "Avant la première utilisation, retirez les quatre vis de transport situées à l’arrière de "
            "l’appareil et conservez-les pour un éventuel déménagement. Placez le lave-linge sur un sol "
            "plan et stable, puis réglez les pieds à l’aide d’une clé de 17 mm jusqu’à ce que la machine "
            "ne vacille plus.",
            "Raccordez l’arrivée d’eau froide au robinet (filetage 20/27) et vérifiez l’étanchéité du "
            "joint. La pression d’eau doit être comprise entre 0,05 et 1 MPa. Branchez enfin l’appareil sur "
            "une prise reliée à la terre, protégée par un disjoncteur de 16 A ; la tension d’alimentation "
            "est de 230 V, 50 Hz.",
            "Programmes : Coton 40 °C (2 h 45), Synthétique 30 °C (1 h 55), Délicat 30 °C (1 h 10), "
            "Rapide 15 min. La charge maximale est de 7 kg pour le coton et de 3,5 kg pour le délicat. "
            "Ne dépassez jamais ces valeurs. En cas d’anomalie, le voyant « E3 » indique un défaut "
            "d’évacuation : nettoyez le filtre de vidange, situé derrière la trappe inférieure droite.",
        ],
    },
    {
        "id": "colonnes-1",
        "font": "Times-Roman",
        "size": 13,
        "columns": 2,
        "title": "Le retour des abeilles sauvages",
        "paragraphs": [
            "Longtemps éclipsées par l’abeille domestique, les abeilles sauvages font l’objet d’un regain "
            "d’intérêt. On en dénombre près de 1 000 espèces en France, dont les bourdons, les osmies et "
            "les andrènes, qui assurent à elles seules une part essentielle de la pollinisation des "
            "cultures fruitières. Contrairement à leur célèbre cousine, la plupart vivent seules : chaque "
            "femelle creuse son nid dans le sol, dans une tige creuse ou dans un vieux mur.",
            "Pourtant, leurs effectifs déclinent. Selon une étude publiée en 2023, près d’un tiers des "
            "espèces européennes seraient menacées, victimes de la disparition des haies, de l’usage des "
            "pesticides et de l’urbanisation. « Ce n’est pas une fatalité, assure la biologiste Camille "
            "Aubry, de l’université de Rennes. Quelques mètres carrés de prairie fleurie suffisent à "
            "accueillir plusieurs dizaines d’espèces. »",
            "Dans plusieurs communes, des « hôtels à insectes » ont été installés dans les parcs, et les "
            "tontes sont désormais espacées d’avril à juillet. Résultat : à Nantes, le nombre d’espèces "
            "recensées est passé de 58 à 94 en six ans. Les habitants, eux, sont invités à semer du trèfle, "
            "de la bourrache ou de la phacélie, et à laisser quelques parcelles de terre nue au soleil, où "
            "les andrènes aiment nidifier.",
        ],
    },
]

# Pages extraites du texte de la Constitution du 4 octobre 1958 (tests/corpus/reels) : (identifiant, page PDF
# de départ, police, corps). Le texte est lu avec l'extracteur de Voxpage puis rendu comme une page scannée.
REAL_PDF_PAGES = [
    ("constitution-a", 3, "Times-Roman", 11),
    ("constitution-b", 8, "Helvetica", 10),
]
