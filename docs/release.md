# Procédure de release

1. Mettre à jour la version dans `pyproject.toml` **et** `voxpage/__init__.py` (un test vérifie qu'elles concordent), pousser sur `main`.
2. Vérifier : lancer `gh workflow run release.yml` (workflow_dispatch : tests, build, tests de l'exécutable, zip en artefact, sans publication) et attendre le vert (`gh run watch`).
3. Télécharger l'artefact (`gh run download`), décompresser sur une machine Windows, lancer `Voxpage.exe` et passer la recette manuelle (lecteur d'écran compris).
4. Créer le tag sur le commit validé : `git tag vX.Y.Z && git push origin vX.Y.Z` (le workflow échoue si le tag diffère de la version de `pyproject.toml`).
5. Le workflow publie la release GitHub (zip, `.sha256`, notes générées) ; relire les notes et les compléter si besoin.
