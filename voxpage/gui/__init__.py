"""Interface graphique (wxPython). `wx` n'est importé qu'ici, jamais par le reste du paquet."""

from __future__ import annotations


def run() -> int:
    from voxpage.gui.main_window import run_app

    return run_app()


def self_test() -> int:
    from voxpage.gui.selftest import run_self_test

    return run_self_test()
