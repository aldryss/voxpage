Les voix se déposent ici : un dossier par voix (modèle `.onnx`, `tokens.txt`, `espeak-ng-data/`, `voice.json`).
Les dossiers de voix ne sont pas versionnés. Au build : `python tools/fetch_voices.py` (téléchargement vérifié
par SHA-256 depuis les modèles Piper convertis pour sherpa-onnx, release `tts-models`).

## Voix livrées

| Dossier | Voix | Licence | Source |
|---|---|---|---|
| `fr_FR-siwis-medium` | français, féminine | CC BY 4.0 | corpus SIWIS, University of Edinburgh — https://datashare.is.ed.ac.uk/handle/10283/2353 |
| `fr_FR-upmc-medium` | français, 2 locuteurs : 0 = Jessica (féminine), 1 = Pierre (masculine) | CC BY-SA 4.0 | https://github.com/marytts/upmc-pierre-data |
| `en_GB-cori-medium` | anglais britannique, féminine | domaine public (LibriVox) | https://librivox.org, modèle de Bryce Beattie |

Attribution à reprendre dans la documentation livrée avec le zip. CC BY-SA 4.0 (UPMC) : le partage des
adaptations du jeu de données/du modèle se fait sous la même licence ; les modèles sont redistribués tels quels.

## Réserve de licence (checkpoint « lessac »)

`fr_FR-siwis-medium` et `fr_FR-upmc-medium` sont des affinages (fine-tuning) du checkpoint Piper « U.S. English
lessac (medium) ». Le jeu de données Lessac (Blizzard 2013) est publié sous une licence de recherche
(https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html). Les MODEL_CARD de ces voix
ne déclarent que la licence de leur propre jeu de données (CC BY 4.0 / CC BY-SA 4.0). L'effet de la licence
Lessac sur les poids dérivés n'est pas tranché ici : risque juridique résiduel à faire valider par le
propriétaire du projet avant une diffusion large. `en_GB-cori-medium` est entraînée de zéro (pas de lessac).
