"""Ligne de commande (conversion : issue #6)."""

import argparse
from collections.abc import Sequence

from voxpage import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxpage", description="Convertit un document en fichier audio.")
    parser.add_argument("--version", action="version", version=f"voxpage {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
