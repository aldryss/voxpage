import json
import sys

import pytest

from voxpage import settings


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    app, fallback = tmp_path / "app", tmp_path / "fallback"
    app.mkdir()
    monkeypatch.setattr(settings, "app_dir", lambda: app)
    monkeypatch.setattr(settings, "fallback_dir", lambda: fallback)
    monkeypatch.delenv("VOXPAGE_VOICES", raising=False)
    return app, fallback


def test_defauts_sans_fichier(dirs):
    assert settings.load() == settings.Settings()


def test_aller_retour_a_cote_de_l_exe(dirs):
    app, fallback = dirs
    s = settings.Settings(voice_id="fr_FR-x", speaker=2, speed=1.25)
    s.audio.format = "wav"
    s.extract.pages = "1-3"
    settings.save(s)
    assert (app / "settings.json").is_file() and not fallback.exists()
    assert settings.load() == s


def test_repli_si_non_inscriptible(dirs, monkeypatch):
    app, fallback = dirs
    monkeypatch.setattr(settings, "_is_writable", lambda d: d != app)
    s = settings.Settings(speed=1.5)
    settings.save(s)
    assert not (app / "settings.json").exists()
    assert (fallback / "settings.json").is_file()
    assert settings.load().speed == 1.5


def test_chargement_tolerant(dirs):
    app, _ = dirs
    (app / "settings.json").write_text(
        json.dumps(
            {
                "speed": 2,
                "voice_id": 12,
                "inconnue": True,
                "audio": {"bitrate_kbps": 128, "autre": 1},
                "normalize": "n'importe quoi",
            }
        )
    )
    s = settings.load()
    assert s.speed == 2.0 and isinstance(s.speed, float)
    assert s.voice_id == ""
    assert s.audio.bitrate_kbps == 128 and s.audio.format == "mp3"
    assert s.normalize == settings.NormalizeOptions()


def test_json_corrompu(dirs):
    app, _ = dirs
    (app / "settings.json").write_text("{pas du json")
    assert settings.load() == settings.Settings()


def test_app_dir_gele(tmp_path, monkeypatch):
    exe = tmp_path / "voxpage.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert settings.app_dir() == tmp_path.resolve()


def test_app_dir_source():
    assert (settings.app_dir() / "pyproject.toml").is_file()


def test_voices_dir(dirs, monkeypatch, tmp_path):
    app, _ = dirs
    assert settings.voices_dir() == app / "voices"
    monkeypatch.setenv("VOXPAGE_VOICES", str(tmp_path / "v"))
    assert settings.voices_dir() == tmp_path / "v"


def test_cli_version(capsys):
    from voxpage.cli import main

    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
