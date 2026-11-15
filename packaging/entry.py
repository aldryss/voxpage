"""Point d'entrée des deux exécutables PyInstaller (Voxpage.exe fenêtré, voxpage-cli.exe console).

Sans argument : interface graphique. Avec arguments : ligne de commande.
"""

import multiprocessing
import sys

from voxpage.__main__ import _run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(_run(sys.argv[1:]))
