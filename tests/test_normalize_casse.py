"""Casse des titres en capitales (issue #12)."""

import pytest

from voxpage.normalize.text import decaps

DECAPS_NOMS = [
    ("GUY DE MAUPASSANT", "Guy de Maupassant"),
    ("HORS DE FRANCE", "Hors de France"),
    ("LE ROI DES AULNES", "Le roi des Aulnes"),
    ("RAPPORT ANNUEL DU CNRS", "Rapport annuel du CNRS"),
    ("LE ROI EST MORT", "Le roi est mort"),
]


@pytest.mark.parametrize("text, expected", DECAPS_NOMS)
def test_casse_des_titres(text, expected):
    assert decaps(text, "fr") == expected
