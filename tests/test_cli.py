import pytest

from voxpage import cli, pipeline, settings
from voxpage.pipeline import ConversionError, ConvertResult
from voxpage.progress import Cancelled


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path / "app")
    monkeypatch.setattr(settings, "fallback_dir", lambda: tmp_path / "fb")


@pytest.fixture
def calls(monkeypatch):
    seen = {}

    def fake(input, output, s, progress=None, cancel=None, pronunciations=None):
        seen.update(input=input, output=output, s=s, pronunciations=pronunciations)
        if progress:
            progress("Synthèse vocale", 0.5)
        return ConvertResult([output], 61.0, ["attention"])

    monkeypatch.setattr(cli, "convert", fake)
    return seen


def test_sortie_par_defaut(calls, tmp_path, capsys):
    assert cli.main([str(tmp_path / "a.pdf")]) == 0
    assert calls["output"] == tmp_path / "a.mp3"
    err = capsys.readouterr().err
    assert "attention" in err and "Synthèse vocale" in err


def test_options(calls, tmp_path):
    argv = [
        str(tmp_path / "a.txt"),
        "-o",
        str(tmp_path / "b"),
        "--voix",
        "v",
        "--locuteur",
        "2",
        "--vitesse",
        "1.5",
        "--format",
        "wav",
        "--debit",
        "96",
        "--decoupage",
        "chapitres",
        "--pages",
        "1-3",
        "--notes",
        "fin",
        "--ocr",
        "jamais",
        "--sans-titres",
        "--silencieux",
    ]
    assert cli.main(argv) == 0
    s = calls["s"]
    assert (s.voice_id, s.speaker, s.speed, s.audio.format, s.audio.bitrate_kbps, s.audio.split) == (
        "v",
        2,
        1.5,
        "wav",
        96,
        "chapters",
    )
    assert (s.extract.pages, s.extract.footnotes, s.extract.ocr, s.normalize.announce_headings) == (
        "1-3",
        "end_of_chapter",
        "never",
        False,
    )
    assert calls["output"] == tmp_path / "b"
    assert not (tmp_path / "app").exists()  # réglages non modifiés sur disque


def test_reprend_reglages_enregistres(calls, tmp_path):
    s = settings.Settings(voice_id="enregistree", speed=1.2)
    s.audio.format = "wav"
    (tmp_path / "app").mkdir()
    settings.save(s)
    cli.main([str(tmp_path / "a.txt"), "--silencieux"])
    assert calls["s"].voice_id == "enregistree" and calls["output"] == tmp_path / "a.wav"


@pytest.mark.parametrize(
    "argv", [[], ["a.txt", "--vitesse", "9"], ["a.txt", "--format", "ogg"], ["a.txt", "--debit", "1"]]
)
def test_mauvais_arguments(argv, calls):
    assert cli.main(argv) == 2


def test_version_et_aide(capsys):
    assert cli.main(["--version"]) == 0
    assert cli.main(["--help"]) == 0
    assert "--liste-voix" in capsys.readouterr().out


def test_codes_de_retour(monkeypatch):
    def boom(exc):
        def f(*a, **k):
            raise exc

        return f

    monkeypatch.setattr(cli, "convert", boom(ConversionError("raté")))
    assert cli.main(["a.txt"]) == 1
    monkeypatch.setattr(cli, "convert", boom(Cancelled()))
    assert cli.main(["a.txt"]) == 130
    monkeypatch.setattr(cli, "convert", boom(RuntimeError("x")))
    assert cli.main(["a.txt"]) == 1


def test_liste_voix(monkeypatch, capsys):
    from voxpage.tts import sherpa
    from voxpage.tts.base import Voice

    class E:
        def list_voices(self):
            return [Voice("fr_x", "Français X", "fr")]

    monkeypatch.setattr(sherpa, "get_engine", lambda: E())
    assert cli.main(["--liste-voix"]) == 0
    assert "fr_x" in capsys.readouterr().out


def test_texte(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("Bonjour le monde. Voici un texte.", encoding="utf-8")
    dest = tmp_path / "t.txt"
    assert cli.main([str(src), "--texte", str(dest), "--silencieux"]) == 0
    assert "Bonjour le monde." in dest.read_text(encoding="utf-8")
    assert pipeline  # import utilisé


def test_sans_flux_standard(calls, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    assert cli.main([str(tmp_path / "a.txt")]) == 0


def test_prononciations_par_defaut(calls, tmp_path):
    assert cli.main([str(tmp_path / "a.pdf")]) == 0
    src = calls["pronunciations"]
    assert src.shipped and src.user and src.user_path is None


def test_option_prononciations(calls, tmp_path):
    dico = tmp_path / "mon dico.txt"
    dico.write_text("EDF = eu dé effe\n", encoding="utf-8")
    assert cli.main([str(tmp_path / "a.pdf"), "--prononciations", str(dico)]) == 0
    assert calls["pronunciations"].user_path == dico and calls["pronunciations"].shipped


def test_option_prononciations_fichier_absent(calls, tmp_path, capsys):
    argv = [str(tmp_path / "a.pdf"), "--prononciations", str(tmp_path / "absent.txt")]
    assert cli.main(argv) == cli.EXIT_USAGE
    assert "introuvable" in capsys.readouterr().err


def test_option_sans_prononciations(calls, tmp_path):
    assert cli.main([str(tmp_path / "a.pdf"), "--sans-prononciations"]) == 0
    src = calls["pronunciations"]
    assert not src.shipped and not src.user


def test_options_prononciations_incompatibles(calls, tmp_path, capsys):
    dico = tmp_path / "d.txt"
    dico.write_text("", encoding="utf-8")
    argv = [str(tmp_path / "a.pdf"), "--prononciations", str(dico), "--sans-prononciations"]
    assert cli.main(argv) == cli.EXIT_USAGE
    assert "s'excluent" in capsys.readouterr().err


def test_diagnostic_indique_le_dictionnaire(tmp_path, capsys):
    (tmp_path / "app").mkdir()
    dico = tmp_path / "app" / "prononciations.txt"
    dico.write_text("EDF = eu dé effe\nligne cassée\nUE = u eu\n", encoding="utf-8")
    cli.main(["--diagnostic"])
    out = capsys.readouterr().out
    assert f"prononciations={tmp_path / 'app' / 'prononciations.txt'}" in out
    assert "prononciations_utilisateur=2 entrée(s)" in out
    assert "prononciations_livrees=fr " in out
    assert "ligne 2 ignorée" in out
