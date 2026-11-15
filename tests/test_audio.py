import os
import tracemalloc
import wave
from pathlib import Path

import numpy as np
import pytest
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from voxpage.audio import AudioError, AudioOptions, AudioWriter
from voxpage.audio._names import clean_name
from voxpage.audio._resample import LinearResampler

RATE = 22050


def sine(seconds: float, rate: int = RATE, freq: float = 440.0, amp: float = 0.4) -> np.ndarray:
    t = np.arange(int(round(seconds * rate))) / rate
    return (np.sin(2 * np.pi * freq * t) * amp * 32767).astype(np.int16)


def mp3_opts(**kw) -> AudioOptions:
    return AudioOptions(format="mp3", **kw)


def leftovers(path: Path) -> list[Path]:
    return sorted(path.rglob("*")) if path.exists() else []


# ---------------------------------------------------------------- fichier unique


def test_mp3_single_duration_and_tags(tmp_path):
    out = tmp_path / "livre.mp3"
    with AudioWriter(out, mp3_opts(), "Mon livre", "Jeanne Auteur") as w:
        w.write(sine(2.0), RATE)
        w.write_silence(500)
        w.write(sine(1.5), RATE)
        assert w.duration_s == pytest.approx(4.0, abs=0.001)
    assert out.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["livre.mp3"]
    m = MP3(out)
    assert m.info.length == pytest.approx(4.0, abs=0.05)
    assert m.info.sample_rate == RATE
    assert m.info.channels == 1
    assert m.info.bitrate == pytest.approx(64000, abs=100)
    assert str(m.tags["TIT2"]) == "Mon livre"
    assert str(m.tags["TPE1"]) == "Jeanne Auteur"
    assert str(m.tags["TCON"]) == "Audiobook"
    assert "CHAP:chp1" not in m.tags  # pas de chapitres sans start_chapter


def test_mp3_single_chapters_chap_ctoc(tmp_path):
    out = tmp_path / "livre.mp3"
    with AudioWriter(out, mp3_opts(), "Livre", None) as w:
        w.write(sine(1.0), RATE)  # chapitre implicite
        w.start_chapter("Un")
        w.write(sine(2.0), RATE)
        w.write_silence(1000)
        w.start_chapter("Vide")  # sans son : ignoré
        w.start_chapter("Deux é")
        w.write(sine(1.0), RATE)
    m = MP3(out)
    assert m.info.length == pytest.approx(5.0, abs=0.05)
    tags = ID3(out)
    chaps = sorted(tags.getall("CHAP"), key=lambda c: c.start_time)
    assert [(str(c.sub_frames["TIT2"]), c.start_time, c.end_time) for c in chaps] == [
        ("Chapitre 1", 0, 1000),
        ("Un", 1000, 4000),
        ("Deux é", 4000, 5000),
    ]
    toc = tags.getall("CTOC")[0]
    assert toc.child_element_ids == [c.element_id for c in chaps]
    assert toc.flags & 2  # top level
    assert "TPE1" not in tags


def test_wav_single(tmp_path):
    out = tmp_path / "livre.wav"
    with AudioWriter(out, AudioOptions(format="wav"), "T", "A") as w:
        w.start_chapter("ignoré en WAV")
        w.write(sine(1.0), RATE)
        w.write_silence(250)
    with wave.open(str(out)) as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, RATE)
        assert f.getnframes() == RATE + round(0.25 * RATE)
        data = np.frombuffer(f.readframes(1000), dtype="<i2")
    assert np.array_equal(data, sine(1.0)[:1000])
    assert [p.name for p in tmp_path.iterdir()] == ["livre.wav"]


def test_silence_leading_and_empty_input(tmp_path):
    out = tmp_path / "a.wav"
    w = AudioWriter(out, AudioOptions(format="wav"), "T", None)
    w.write_silence(1000)  # avant tout son : ignoré
    w.write(np.zeros(0, dtype=np.int16), RATE)
    assert w.close() == []
    assert not out.exists() and list(tmp_path.iterdir()) == []


def test_no_click_continuous_blocks(tmp_path):
    """Des blocs successifs d'une même sinusoïde restent continus (pas de saut)."""
    out = tmp_path / "a.wav"
    full = sine(1.0)
    with AudioWriter(out, AudioOptions(format="wav"), "T", None) as w:
        for i in range(0, len(full), 777):
            w.write(full[i : i + 777], RATE)
    with wave.open(str(out)) as f:
        data = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
    assert np.array_equal(data, full)


def test_mp3_no_truncation_flush(tmp_path):
    """Le décodage de la fin n'est pas tronqué : la durée colle même pour un bloc très court."""
    out = tmp_path / "a.mp3"
    with AudioWriter(out, mp3_opts(), "T", None) as w:
        w.write(sine(0.1), RATE)
    assert MP3(out).info.length == pytest.approx(0.1, abs=0.05)


# ---------------------------------------------------------------- mode par chapitres


def test_chapters_mode_mp3(tmp_path):
    out = tmp_path / "Mon livre.mp3"
    with AudioWriter(out, mp3_opts(split="chapters"), "Mon livre", "Jeanne") as w:
        w.write(sine(0.5), RATE)  # implicite
        w.start_chapter("Intro: le début?")
        w.write(sine(1.0), RATE)
        w.write_silence(500)
        w.start_chapter("Rien")
        w.start_chapter("")
        w.write(sine(1.0), RATE)
    d = tmp_path / "Mon livre"
    names = sorted(p.name for p in d.iterdir())
    assert names == [
        "001 - Chapitre 1.mp3",
        "002 - Intro_ le début_.mp3",
        "003 - Chapitre 3.mp3",
        "Mon livre.m3u8",
    ]
    assert not out.exists()
    expected = [(0.5, "Chapitre 1"), (1.5, "Intro: le début?"), (1.0, "Chapitre 3")]
    for i, (name, (dur, title)) in enumerate(zip(names[:3], expected, strict=True), 1):
        m = MP3(d / name)
        assert m.info.length == pytest.approx(dur, abs=0.05)
        assert str(m.tags["TIT2"]) == title
        assert str(m.tags["TALB"]) == "Mon livre"
        assert str(m.tags["TPE1"]) == "Jeanne"
        assert str(m.tags["TRCK"]) == f"{i}/3"
    raw = (d / "Mon livre.m3u8").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8").splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "#EXTINF:0,Chapitre 1"  # 0,5 s arrondi à l'entier pair
    assert lines[3] == "#EXTINF:2,Intro: le début?"
    assert [ln for ln in lines if not ln.startswith("#")] == names[:3]
    assert not any(p.suffix == ".part" or ".part" in p.name for p in d.iterdir())


def test_chapters_mode_close_returns_files_and_wav(tmp_path):
    w = AudioWriter(tmp_path / "x.wav", AudioOptions(format="wav", split="chapters"), "Titre", None)
    w.start_chapter("A")
    w.write(sine(0.2), RATE)
    w.start_chapter("B")
    w.write(sine(0.2), RATE)
    files = w.close()
    assert [f.name for f in files] == ["001 - A.wav", "002 - B.wav", "Titre.m3u8"]
    assert w.close() == files  # idempotent
    with wave.open(str(files[0])) as f:
        assert f.getnframes() == round(0.2 * RATE)
    with pytest.raises(RuntimeError):
        w.write(sine(0.1), RATE)


def test_chapters_only_empty_chapters_produces_nothing(tmp_path):
    w = AudioWriter(tmp_path / "x", mp3_opts(split="chapters"), "T", None)
    w.start_chapter("A")
    assert w.close() == []
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- noms


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('a<b>c:d"e/f\\g|h?i*j', "a_b_c_d_e_f_g_h_i_j"),
        ("CON", "_CON"),
        ("con.txt", "_con.txt"),
        ("lpt1", "_lpt1"),
        ("COM9", "_COM9"),
        ("COM10", "COM10"),
        ("Fin...  ", "Fin"),
        ("  a   b  ", "a b"),
        ("", "Chapitre 4"),
        ("...", "Chapitre 4"),
        ("tab\there\n", "tab here"),
        ("é" * 200, "é" * 80),
        ("x" * 79 + " yyyy", "x" * 79),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw, "Chapitre 4") == expected


# ---------------------------------------------------------------- rééchantillonnage


def test_resample_different_voice_rates(tmp_path):
    out = tmp_path / "a.wav"
    with AudioWriter(out, AudioOptions(format="wav"), "T", None) as w:
        w.write(sine(1.0, 22050), 22050)
        w.write(sine(1.0, 16000, freq=300), 16000)
        w.write(sine(1.0, 44100, freq=300), 44100)
        assert w.duration_s == pytest.approx(3.0, abs=0.002)
    with wave.open(str(out)) as f:
        assert f.getframerate() == 22050
        n = f.getnframes()
        data = np.frombuffer(f.readframes(n), dtype="<i2").astype(np.float64)
    assert n == pytest.approx(3 * 22050, abs=3)
    seg = data[22050 : 2 * 22050 - 5]
    ref = sine(1.0, 22050, freq=300).astype(np.float64)
    assert np.max(np.abs(seg - ref[: len(seg)])) < 100  # interpolation linéaire : petite erreur
    assert np.max(np.abs(np.diff(data))) < 4500  # pas de saut aux jonctions


def test_resampler_blocks_equal_whole():
    x = sine(0.5, 16000, freq=200)
    whole = LinearResampler(16000, 22050).process(x)
    r = LinearResampler(16000, 22050)
    parts = np.concatenate([r.process(x[i : i + 333]) for i in range(0, len(x), 333)])
    assert abs(len(whole) - len(parts)) <= 1
    n = min(len(whole), len(parts))
    assert np.max(np.abs(whole[:n].astype(int) - parts[:n])) <= 1


def test_write_validation(tmp_path):
    w = AudioWriter(tmp_path / "a.wav", AudioOptions(format="wav"), "T", None)
    with pytest.raises(TypeError):
        w.write(np.zeros(10, dtype=np.float32), RATE)
    with pytest.raises(ValueError):
        w.write(np.zeros((10, 2), dtype=np.int16), RATE)
    w.abort()


# ---------------------------------------------------------------- écriture sûre


def test_abort_leaves_nothing_single(tmp_path):
    out = tmp_path / "sous" / "dossier" / "a.mp3"
    w = AudioWriter(out, mp3_opts(), "T", None)
    w.write(sine(1.0), RATE)
    assert any(p.name.endswith(".part") for p in (tmp_path / "sous" / "dossier").iterdir())
    w.abort()
    assert leftovers(tmp_path) == []
    w.abort()  # idempotent


def test_abort_leaves_nothing_chapters(tmp_path):
    w = AudioWriter(tmp_path / "livre.mp3", mp3_opts(split="chapters"), "T", None)
    w.start_chapter("A")
    w.write(sine(0.5), RATE)
    w.start_chapter("B")
    w.write(sine(0.5), RATE)
    w.abort()
    assert leftovers(tmp_path) == []


def test_exception_in_with_aborts_and_preserves_existing(tmp_path):
    out = tmp_path / "a.mp3"
    out.write_bytes(b"ancien")
    with pytest.raises(ZeroDivisionError):
        with AudioWriter(out, mp3_opts(), "T", None) as w:
            w.write(sine(1.0), RATE)
            1 / 0  # noqa: B018
    assert out.read_bytes() == b"ancien"
    assert [p.name for p in tmp_path.iterdir()] == ["a.mp3"]


def test_existing_output_replaced_only_on_close(tmp_path):
    out = tmp_path / "a.wav"
    out.write_bytes(b"ancien")
    w = AudioWriter(out, AudioOptions(format="wav"), "T", None)
    w.write(sine(0.5), RATE)
    assert out.read_bytes() == b"ancien"
    w.close()
    with wave.open(str(out)) as f:
        assert f.getnframes() == round(0.5 * RATE)


def test_abort_keeps_preexisting_files_in_chapter_dir(tmp_path):
    d = tmp_path / "livre"
    d.mkdir()
    (d / "001 - A.mp3").write_bytes(b"ancien")
    (d / "autre.txt").write_text("x")
    w = AudioWriter(tmp_path / "livre.mp3", mp3_opts(split="chapters"), "T", None)
    w.start_chapter("A")
    w.write(sine(0.5), RATE)
    w.abort()
    assert sorted(p.name for p in d.iterdir()) == ["001 - A.mp3", "autre.txt"]
    assert (d / "001 - A.mp3").read_bytes() == b"ancien"


def test_stale_part_file_untouched(tmp_path):
    out = tmp_path / "a.wav"
    stale = tmp_path / "a.wav.part"
    stale.write_bytes(b"autre")
    w = AudioWriter(out, AudioOptions(format="wav"), "T", None)
    w.write(sine(0.2), RATE)
    w.abort()
    assert stale.read_bytes() == b"autre"
    assert [p.name for p in tmp_path.iterdir()] == ["a.wav.part"]


def test_failure_at_close_preserves_existing(tmp_path, monkeypatch):
    out = tmp_path / "a.mp3"
    out.write_bytes(b"ancien")
    w = AudioWriter(out, mp3_opts(), "T", None)
    w.write(sine(0.5), RATE)

    def boom(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("voxpage.audio.os.replace", boom)
    with pytest.raises(AudioError, match="Écriture audio impossible"):
        w.close()
    assert out.read_bytes() == b"ancien"
    assert [p.name for p in tmp_path.iterdir()] == ["a.mp3"]


def test_unwritable_destination_refused(tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("x")
    with pytest.raises(AudioError, match="n'est pas un dossier"):
        AudioWriter(blocker / "sous" / "a.mp3", mp3_opts(), "T", None)
    with pytest.raises(AudioError, match="est un dossier"):
        AudioWriter(tmp_path, mp3_opts(), "T", None)
    with pytest.raises(AudioError, match="c'est un fichier"):
        AudioWriter(tmp_path / "fichier.mp3", mp3_opts(split="chapters"), "T", None)
    assert [p.name for p in tmp_path.iterdir()] == ["fichier"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permissions POSIX requises (ni Windows ni root)")
def test_readonly_directory_refused(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        with pytest.raises(AudioError, match="accessible en écriture"):
            AudioWriter(ro / "a.mp3", mp3_opts(), "T", None)
        with pytest.raises(AudioError, match="accessible en écriture"):
            AudioWriter(ro / "x" / "a.mp3", mp3_opts(), "T", None)
    finally:
        ro.chmod(0o755)


def test_invalid_options(tmp_path):
    with pytest.raises(AudioError):
        AudioWriter(tmp_path / "a.ogg", AudioOptions(format="ogg"), "T", None)  # type: ignore[arg-type]


# ---------------------------------------------------------------- mémoire bornée


def test_memory_bounded_one_hour(tmp_path):
    out = tmp_path / "heure.mp3"
    block = sine(1.0)
    tracemalloc.start()
    try:
        with AudioWriter(out, mp3_opts(), "Longue", None) as w:
            for i in range(3600):
                if i % 600 == 0:
                    w.start_chapter(f"Partie {i // 600}")
                w.write(block, RATE)
            w.write_silence(5000)
            assert w.duration_s == pytest.approx(3605.0, abs=0.01)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, f"pic mémoire {peak / 1e6:.1f} Mo"
    assert MP3(out).info.length == pytest.approx(3605.0, abs=0.1)
    assert len(ID3(out).getall("CHAP")) == 6


def test_long_silence_is_chunked(tmp_path):
    out = tmp_path / "a.wav"
    tracemalloc.start()
    try:
        with AudioWriter(out, AudioOptions(format="wav"), "T", None) as w:
            w.write(sine(0.1), RATE)
            w.write_silence(600_000)  # 10 minutes
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024
