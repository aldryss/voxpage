"""Voix par défaut (issue #12) : sans réglage enregistré, la voix française est Siwis, vitesse 1,0."""

import importlib.util
import sys
from pathlib import Path

from voxpage import pipeline
from voxpage.document import Block, Chapter, Document
from voxpage.settings import Settings
from voxpage.tts.base import Voice, default_voice

ROOT = Path(__file__).resolve().parent.parent
FR = Voice("fr_FR-siwis-medium", "Français, voix féminine (Siwis)", "fr")
UPMC = Voice(
    "fr_FR-upmc-medium", "Français, UPMC", "fr", ["Jessica (voix féminine)", "Pierre (voix masculine)"]
)
EN = Voice("en_GB-cori-medium", "English", "en")


def test_voix_par_defaut_independante_de_l_ordre():
    for order in ([EN, FR, UPMC], [UPMC, EN, FR], [UPMC, FR], [FR]):
        assert default_voice(order, "fr") is FR
    assert default_voice([UPMC, EN, FR], "en") is EN


def test_voix_par_defaut_repli():
    assert default_voice([UPMC, EN], "fr") is UPMC  # Siwis absente : première voix française
    assert default_voice([EN], "fr") is EN  # aucune voix française : la première voix
    assert default_voice([], "fr") is None


def test_reglages_par_defaut():
    s = Settings()
    assert (s.voice_id, s.speaker, s.speed) == ("", 0, 1.0)


def test_pipeline_choisit_siwis_sans_reglage():
    class Engine:
        def list_voices(self):
            return [EN, UPMC, FR]

    doc = Document("T", None, "fr", [Chapter("", [Block("paragraph", "Bonjour.")])])
    voice, warnings = pipeline._choose_voice(Engine(), Settings(), doc)
    assert voice.id == "fr_FR-siwis-medium" and warnings == []


def _fetch_voices():
    spec = importlib.util.spec_from_file_location("fetch_voices", ROOT / "tools" / "fetch_voices.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fetch_voices", mod)
    spec.loader.exec_module(mod)
    return mod


def test_locuteurs_upmc_jessica_avant_pierre():
    upmc = next(v for v in _fetch_voices().VOICES if v["id"] == "fr_FR-upmc-medium")
    names = upmc["speakers"]
    assert len(names) == 2  # Pierre n'est pas supprimé
    assert names[0].startswith("Jessica") and names[1].startswith("Pierre")


def test_siwis_listee_avant_upmc_dans_fetch_voices():
    ids = [v["id"] for v in _fetch_voices().VOICES if v["lang"] == "fr"]
    assert ids == ["fr_FR-siwis-medium", "fr_FR-upmc-medium"]
