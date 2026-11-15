"""Logique du dialogue « Prononciations » (sans wx)."""

import pytest

from voxpage.gui import model as m
from voxpage.gui import pronunciations as p
from voxpage.normalize.lexicon import LexiconError


@pytest.fixture
def model(tmp_path):
    f = tmp_path / "prononciations.txt"
    f.write_text("# test\nINRIA = inria\n", encoding="utf-8")
    return p.PronunciationModel(f)


def test_libelles_dialogue_sans_accelerateur_en_double():
    assert m.duplicate_accelerators(p.LABELS.values()) == []
    assert all(m.accelerator(v) for v in p.LABELS.values())


def test_libelles_fenetre_principale_sans_accelerateur_en_double():
    assert m.duplicate_accelerators(m.LABELS.values()) == []
    assert m.accelerator(m.LABELS["pron"]) == "p"
    assert m.plain_label(m.LABELS["pron"]) == "Prononciations…"


def test_bouton_prononciations_inactif_pendant_une_conversion():
    flags = m.ui_flags(m.UiState.CONVERTING, True, True, False, False)
    assert flags["pron"] is False
    assert m.ui_flags(m.UiState.IDLE, False, False, False, False)["pron"] is True


def test_liste(model):
    (row,) = model.rows()
    assert (row.written, row.spoken, row.lang_name) == ("INRIA", "inria", "toutes")


def test_ajout_modification_suppression(model):
    assert model.add("EDF", "eu dé effe", "fr") == "« EDF » ajouté."
    rows = {r.written: r for r in model.rows()}
    assert rows["EDF"].lang_name == "français"
    assert model.update(rows["EDF"].line, "EDF", "e d f", "fr") == "« EDF » modifié."
    assert model.row_at(rows["EDF"].line).spoken == "e d f"
    assert model.remove(rows["EDF"].line) == "« EDF » supprimé."
    assert [r.written for r in model.rows()] == ["INRIA"]
    assert model.path.read_text(encoding="utf-8") == "# test\nINRIA = inria\n"


def test_erreurs_en_francais(model):
    with pytest.raises(LexiconError, match="Indiquez"):
        model.add("", "x")
    with pytest.raises(LexiconError, match="existe déjà"):
        model.add("INRIA", "autre")


def test_dit_vide_affiche_comme_annulation(model):
    model.add("EDF", "")
    row = next(r for r in model.rows() if r.written == "EDF")
    assert "annule" in row.spoken_display


def test_modification_externe_detectee(model):
    assert not model.changed_on_disk()
    model.path.write_text("Z = z\n", encoding="utf-8")
    model.path.touch()
    import os

    os.utime(model.path, (1, 1))
    assert model.changed_on_disk()
    model.reload()
    assert [r.written for r in model.rows()] == ["Z"] and not model.changed_on_disk()


def test_fichier_inexistant_cree_a_la_demande(tmp_path):
    mod = p.PronunciationModel(tmp_path / "x" / "prononciations.txt")
    assert mod.rows() == [] and not mod.path.exists()
    assert mod.summary() == "Aucune entrée."
    mod.ensure_file()
    assert mod.path.read_text(encoding="utf-8").startswith("# Dictionnaire de prononciation")


def test_resume_signale_les_lignes_ignorees(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("A1 = a\nn'importe quoi\n", encoding="utf-8")
    text = p.PronunciationModel(f).summary()
    assert text.startswith("1 entrée.") and "ligne 2 ignorée" in text


def test_texte_a_ecouter():
    assert p.PronunciationModel.listen_text("EDF", " eu dé effe ", True) == "eu dé effe"
    assert p.PronunciationModel.listen_text("EDF", "eu dé effe", False) == "E D F"
    assert p.PronunciationModel.listen_text("NASA", "x", False, "en") == "NASA"


def test_confirmation_de_suppression(model):
    assert model.confirm_delete_text(model.rows()[0]) == "Supprimer « INRIA » du dictionnaire ?"
