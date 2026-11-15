from pathlib import Path

from voxpage.gui import model as m


def test_suggest_output_single():
    assert m.suggest_output(Path("/a/b/livre.pdf"), "mp3", "single") == Path("/a/b/livre.mp3")
    assert m.suggest_output(Path("/a/b/livre.pdf"), "wav", "single") == Path("/a/b/livre.wav")


def test_suggest_output_chapters_and_collision():
    assert m.suggest_output(Path("/a/livre.pdf"), "mp3", "chapters") == Path("/a/livre")
    assert m.suggest_output(Path("/a/livre"), "mp3", "chapters") == Path("/a/livre (audio)")
    assert m.suggest_output(Path("/a/livre.pdf"), "mp3", "single", Path("/x")) == Path("/x/livre.mp3")


def test_file_filter():
    f = m.build_file_filter([".txt", ".pdf", "PDF"])
    assert f == "Documents pris en charge (*.pdf;*.txt)|*.pdf;*.txt|Tous les fichiers (*.*)|*.*"
    assert m.build_file_filter([]) == "Tous les fichiers (*.*)|*.*"


def test_speed():
    assert m.format_speed(1.2) == "1,2"
    assert m.format_speed(1.0) == "1,0"
    assert m.speed_label(0.5) == "Vitesse : 0,5"
    assert m.slider_to_speed(12) == 1.2
    assert m.slider_to_speed(99) == 2.0
    assert m.speed_to_slider(1.2) == 12
    assert m.speed_to_slider(0.1) == 5


def test_format_duration():
    assert m.format_duration(0) == "0 seconde"
    assert m.format_duration(45) == "45 secondes"
    assert m.format_duration(61) == "1 minute 1 seconde"
    assert m.format_duration(3725.4) == "1 heure 2 minutes 5 secondes"
    assert m.format_duration(7200) == "2 heures"


def test_throttle_announces_steps_and_deciles():
    t = m.ProgressThrottle()
    msgs = [t.feed("Lecture", f / 100).message for f in range(0, 31)]
    announced = [x for x in msgs if x]
    assert announced == ["Lecture : 0 %", "Lecture : 10 %", "Lecture : 20 %", "Lecture : 30 %"]
    assert t.feed("Synthèse", 0.31).message == "Synthèse : 31 %"
    assert t.feed("Synthèse", 0.35).message is None
    assert t.feed("Synthèse", 0.40).message == "Synthèse : 40 %"
    u = t.feed("Synthèse", 0.40)
    assert u.message is None and not u.percent_changed


def test_throttle_clamps():
    t = m.ProgressThrottle()
    assert t.feed("x", 5).percent == 100
    assert t.feed("x", -1).percent == 0


def test_accelerators_unique():
    assert m.duplicate_accelerators(m.LABELS.values()) == []
    assert m.duplicate_accelerators(["&Ab", "C&a"]) == ["a"]


def test_plain_label():
    assert m.plain_label("&Fichier :") == "Fichier"
    assert m.plain_label("Reconnaissance de texte (&OCR)") == "Reconnaissance de texte (OCR)"


def test_ui_flags():
    idle = m.ui_flags(m.UiState.IDLE, True, True, False, False)
    assert idle["convert"] and idle["export"] and not idle["cancel"] and not idle["speaker"]
    assert not idle["open_folder"]
    busy = m.ui_flags(m.UiState.CONVERTING, True, True, True, True)
    assert busy["cancel"] and not busy["convert"] and not busy["voice"] and not busy["input"]
    assert not busy["preview"] and not busy["open_folder"]
    assert not m.ui_flags(m.UiState.IDLE, False, True, False, False)["convert"]
    assert not m.ui_flags(m.UiState.IDLE, True, False, False, False)["convert"]
    assert m.ui_flags(m.UiState.IDLE, True, True, True, True)["open_folder"]
    assert m.ui_flags(m.UiState.CONVERTING, True, True, False, False, playing=True)["preview"]


def test_describe_error():
    assert "pas encore" in m.describe_error(NotImplementedError("x"))
    assert "introuvable" in m.describe_error(FileNotFoundError(2, "no", "a.pdf"))
    assert "Accès refusé" in m.describe_error(PermissionError(13, "no", "a"))
    assert "inattendue" in m.describe_error(ValueError("boom"))
    assert "boom" not in m.describe_error(ValueError("boom"))


def test_result_message():
    text = m.result_message([Path("/a/b.mp3")], 125, ["pages 4 à 9 : OCR"])
    assert "2 minutes 5 secondes" in text and "1 fichier produit" in text
    assert "1 avertissement" in text and "- pages 4 à 9 : OCR" in text
    assert "Aucun son" in m.result_message([], 0, [])
