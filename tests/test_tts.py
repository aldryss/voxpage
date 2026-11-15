import json

import numpy as np
import pytest

from voxpage.tts.sherpa import (
    MAX_SPEED,
    MIN_SPEED,
    SherpaEngine,
    TtsError,
    clamp_speed,
    default_threads,
    get_engine,
)

FR = "Bonjour, ceci est un test de synthèse vocale. Nous vérifions que la voix est claire."
EN = "Hello, this is a speech synthesis test. We check that the voice is clear."


def make_voice(root, name, complete=True, meta=None):
    d = root / name
    d.mkdir()
    (d / "voice.json").write_text(
        json.dumps(meta or {"name": "Voix de test", "lang": "fr", "speakers": ["A", "B"]}), encoding="utf-8"
    )
    if complete:
        (d / "m.onnx").write_bytes(b"")
        (d / "tokens.txt").write_text("a 0\n")
        (d / "espeak-ng-data").mkdir()
    return d


def test_list_voices_fake_dir(tmp_path):
    make_voice(tmp_path, "fr_test")
    make_voice(tmp_path, "en_test", meta={"name": "Test voice", "lang": "en"})
    (tmp_path / "sans_json").mkdir()
    bad = make_voice(tmp_path, "casse")
    (bad / "voice.json").write_text("{pas du json")
    voices = SherpaEngine(tmp_path).list_voices()
    assert [(v.id, v.name, v.lang, v.speakers) for v in voices] == [
        ("en_test", "Test voice", "en", []),
        ("fr_test", "Voix de test", "fr", ["A", "B"]),
    ]


def test_list_voices_missing_dir(tmp_path):
    assert SherpaEngine(tmp_path / "absent").list_voices() == []


def test_voice_not_found(tmp_path):
    with pytest.raises(TtsError, match="introuvable"):
        SherpaEngine(tmp_path).synthesize("Bonjour", "nope")


def test_incomplete_voice(tmp_path):
    make_voice(tmp_path, "vide", complete=False)
    with pytest.raises(TtsError, match="incomplète.*modèle .onnx.*tokens.txt.*espeak-ng-data"):
        SherpaEngine(tmp_path).synthesize("Bonjour", "vide")


def test_voice_id_cannot_escape(tmp_path):
    with pytest.raises(TtsError):
        SherpaEngine(tmp_path).synthesize("Bonjour", "../x")


def test_clamp_speed():
    assert clamp_speed(0.1) == MIN_SPEED
    assert clamp_speed(9) == MAX_SPEED
    assert clamp_speed(1.0) == 1.0


def test_default_threads_bounds():
    assert 1 <= default_threads() <= 4


def test_get_engine_shared():
    assert get_engine() is get_engine()


def _voice_ids(lang):
    return [v.id for v in get_engine().list_voices() if v.lang == lang]


@pytest.mark.voices
@pytest.mark.parametrize(("lang", "text", "max_dur"), [("fr", FR, 12.0), ("en", EN, 12.0)])
def test_synthesize_real_voice(lang, text, max_dur):
    ids = _voice_ids(lang)
    if not ids:
        pytest.skip(f"aucune voix {lang}")
    audio, rate = get_engine().synthesize(text, ids[0])
    assert audio.dtype == np.int16 and audio.ndim == 1
    assert rate >= 16000
    assert 2.0 < len(audio) / rate < max_dur
    assert np.abs(audio.astype(np.int32)).max() < 32767  # pas d'écrêtage
    assert np.sqrt((audio.astype(float) ** 2).mean()) > 300  # pas de silence


@pytest.mark.voices
def test_empty_text_gives_empty_array():
    ids = _voice_ids("fr") or _voice_ids("en")
    if not ids:
        pytest.skip("aucune voix")
    audio, rate = get_engine().synthesize("   ", ids[0])
    assert audio.dtype == np.int16 and len(audio) == 0 and rate > 0


@pytest.mark.voices
def test_speed_shortens_audio():
    # La synthèse VITS est stochastique (durée : écart type ~2,5 % d'un tirage à l'autre) : on compare des
    # médianes de 5 tirages. Mesuré sur 30 tirages : 0,8x => durée x 1,11 ; 1,5x => durée x 0,75.
    # Seuils à plus de 4 écarts types de la moyenne.
    ids = _voice_ids("fr")
    if not ids:
        pytest.skip("aucune voix fr")
    eng = get_engine()

    def median_len(speed: float) -> float:
        return float(np.median([len(eng.synthesize(FR, ids[0], speed=speed)[0]) for _ in range(5)]))

    normal, fast, slow = median_len(1.0), median_len(1.5), median_len(0.8)
    assert fast < normal * 0.85
    assert slow > normal * 1.03


def test_speed_is_clamped_before_synthesis(tmp_path):
    seen = []

    class FakeTts:
        num_speakers = 1

        def generate(self, text, sid=0, speed=1.0):
            seen.append(speed)
            return type("A", (), {"samples": [0.0, 0.5], "sample_rate": 22050})()

    eng = SherpaEngine(tmp_path)
    eng._models["v"] = (FakeTts(), 22050)
    eng.synthesize("Bonjour.", "v", speed=50)
    eng.synthesize("Bonjour.", "v", speed=0.01)
    assert seen == [MAX_SPEED, MIN_SPEED]


@pytest.mark.voices
def test_bad_speaker():
    ids = _voice_ids("fr")
    if not ids:
        pytest.skip("aucune voix fr")
    with pytest.raises(TtsError, match="Locuteur"):
        get_engine().synthesize(FR, ids[0], speaker=99)


def test_dossier_de_voix_ascii_inchange(tmp_path):
    from voxpage.tts.sherpa import ascii_voice_folder

    assert ascii_voice_folder(tmp_path, windows=True) == tmp_path
    assert ascii_voice_folder(tmp_path / "é", windows=False) == tmp_path / "é"


def test_dossier_de_voix_accentue_copie_si_pas_de_nom_court(tmp_path, monkeypatch):
    from voxpage.tts import sherpa

    src = tmp_path / "José" / "voix"
    src.mkdir(parents=True)
    (src / "tokens.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sherpa, "_short_path", lambda p: None)
    monkeypatch.setattr(sherpa.tempfile, "tempdir", str(tmp_path))
    out = sherpa.ascii_voice_folder(src, windows=True)
    assert str(out).isascii() and (out / "tokens.txt").read_text(encoding="utf-8") == "x"
