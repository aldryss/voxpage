import tomllib
from pathlib import Path

import voxpage
from voxpage import cli, diagnostic, settings

ROOT = Path(__file__).resolve().parent.parent


def test_version_unique():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert voxpage.__version__ == project["version"]


def test_version_affichee(capsys):
    assert cli.main(["--version"]) == 0
    assert voxpage.__version__ in capsys.readouterr().out


def test_diagnostic_ecrit_les_reglages_a_cote(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(settings, "fallback_dir", lambda: tmp_path / "fb")
    assert cli.main(["--diagnostic"]) == 0
    out = capsys.readouterr().out
    assert f"app_dir={tmp_path}" in out and "ÉCHEC" not in out
    assert (tmp_path / "settings.json").is_file()


def test_diagnostic_signale_un_echec(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "app_dir", lambda: tmp_path)

    def boom() -> str:
        raise ImportError("absent")

    monkeypatch.setattr(diagnostic, "_checks", lambda: [("x", boom)])
    assert diagnostic.run() == 1
    assert "ÉCHEC x : ImportError : absent" in capsys.readouterr().out
