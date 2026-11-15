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
    ids = _voice_ids("fr")
    if not ids:
        pytest.skip("aucune voix fr")
    eng = get_engine()
    normal, _ = eng.synthesize(FR, ids[0], speed=1.0)
    fast, _ = eng.synthesize(FR, ids[0], speed=1.5)
    assert len(fast) < len(normal) * 0.8
    out_of_range, _ = eng.synthesize(FR, ids[0], speed=50)
    capped, _ = eng.synthesize(FR, ids[0], speed=MAX_SPEED)
    assert abs(len(out_of_range) - len(capped)) < 0.05 * len(capped)  # bruit stochastique du modèle


@pytest.mark.voices
def test_bad_speaker():
    ids = _voice_ids("fr")
    if not ids:
        pytest.skip("aucune voix fr")
    with pytest.raises(TtsError, match="Locuteur"):
        get_engine().synthesize(FR, ids[0], speaker=99)
