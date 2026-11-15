import pytest

from voxpage import settings


def pytest_configure(config):
    config.addinivalue_line("markers", "voices: nécessite au moins une voix installée dans voices/")


def pytest_collection_modifyitems(config, items):
    if any(p.is_dir() and (p / "voice.json").is_file() for p in settings.voices_dir().glob("*")):
        return
    skip = pytest.mark.skip(reason="aucune voix installée (python tools/fetch_voices.py)")
    for item in items:
        if "voices" in item.keywords:
            item.add_marker(skip)
