"""Écriture audio en flux (issue #5).

Le son est encodé et écrit sur disque au fil de l'eau : seule une petite fenêtre d'échantillons
est en mémoire, quelle que soit la durée du livre. Les fichiers sont produits sous un nom
temporaire (`.part`) et renommés à `close()` ; `abort()` supprime tout ce qui a été produit.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from mutagen.id3 import CHAP, CTOC, ID3, TALB, TCON, TIT2, TPE1, TRCK, CTOCFlags, Encoding

from ._names import clean_name
from ._resample import LinearResampler
from ._sinks import Mp3Sink, WavSink

__all__ = ["AudioError", "AudioOptions", "AudioWriter"]

_MAX_BLOCK = 1 << 20  # échantillons par appel d'encodage (silences découpés)


class AudioError(Exception):
    """Erreur d'écriture audio ; le message est destiné à l'utilisateur (en français)."""


@dataclass
class AudioOptions:
    format: Literal["mp3", "wav"] = "mp3"
    bitrate_kbps: int = 64  # voix mono : 64 kbit/s suffit
    split: Literal["single", "chapters"] = "single"


@dataclass
class _Chapter:
    title: str
    explicit: bool
    start: int = 0  # échantillons, dans le fichier unique
    end: int = 0
    samples: int = 0
    has_audio: bool = False
    number: int = 0  # rang du chapitre (1..) parmi ceux qui ont du son
    final: Path | None = None  # mode "chapters"
    part: Path | None = None
    sink: object | None = field(default=None, repr=False)


class AudioWriter:
    """Écrivain audio en flux, utilisable avec `with`.

    - `write` : bloc PCM int16 mono ; la fréquence du premier bloc fixe celle de la sortie, les blocs
      suivants à une autre fréquence sont rééchantillonnés.
    - `write_silence` : silence (ignoré en tête de chapitre, où il n'a pas d'utilité).
    - `start_chapter` : début d'un chapitre. Du son écrit avant le premier appel va dans un chapitre
      implicite. Un chapitre sans son ne produit rien.
    - `close` : finalise, renomme et renvoie les fichiers produits (liste vide si aucun son).
    - `abort` : supprime tout ce qui a été produit ; les fichiers préexistants restent intacts.
    """

    def __init__(self, output: Path, options: AudioOptions, title: str, author: str | None):
        if options.format not in ("mp3", "wav"):
            raise AudioError(f"Format audio inconnu : {options.format!r}.")
        if options.split not in ("single", "chapters"):
            raise AudioError(f"Mode de découpage inconnu : {options.split!r}.")
        if options.format == "mp3" and not 8 <= int(options.bitrate_kbps) <= 320:
            raise AudioError(f"Débit MP3 invalide : {options.bitrate_kbps} kbit/s.")
        self._output = Path(output)
        self._opt = options
        self._title = title or ""
        self._author = author or None
        self._ext = "." + options.format
        self._chapters_mode = options.split == "chapters"
        # dossier où seront écrits les fichiers
        self._dir = self._output.with_suffix("") if self._chapters_mode else self._output.parent
        self._check_destination()

        self._rate: int | None = None
        self._resampler: LinearResampler | None = None
        self._resampler_src = 0
        self._total = 0  # échantillons écrits (à la fréquence de sortie)
        self._cur: _Chapter | None = None
        self._chapters: list[_Chapter] = []  # chapitres ayant du son
        self._explicit = False
        self._single_sink: object | None = None
        self._single_part: Path | None = None
        self._parts: list[Path] = []  # tous les .part créés
        self._made_dirs: list[Path] = []
        self._placed: list[tuple[Path, bool]] = []  # (fichier, existait avant)
        self._closed = False
        self._aborted = False
        self._result: list[Path] = []

    # ------------------------------------------------------------------ contrôles

    def _check_destination(self) -> None:
        if self._chapters_mode:
            if self._dir.exists() and not self._dir.is_dir():
                raise AudioError(f"Impossible de créer le dossier « {self._dir} » : c'est un fichier.")
        elif self._output.is_dir():
            raise AudioError(f"La destination « {self._output} » est un dossier, pas un fichier.")
        probe = self._dir
        while not probe.exists():
            if probe.parent == probe:
                break
            probe = probe.parent
        if not probe.is_dir():
            raise AudioError(f"Destination inutilisable : « {probe} » n'est pas un dossier.")
        if not os.access(probe, os.W_OK | os.X_OK):
            raise AudioError(f"Le dossier « {probe} » n'est pas accessible en écriture.")
        if not self._chapters_mode and self._output.exists() and not os.access(self._output, os.W_OK):
            raise AudioError(f"Le fichier « {self._output} » existe et n'est pas accessible en écriture.")

    def _ensure_dir(self) -> None:
        missing = []
        d = self._dir
        while not d.exists():
            missing.append(d)
            d = d.parent
        for m in reversed(missing):
            try:
                m.mkdir()
            except FileExistsError:
                continue
            except OSError as e:
                raise AudioError(f"Impossible de créer le dossier « {m} » : {e.strerror or e}.") from e
            self._made_dirs.append(m)

    def _open_part(self, final: Path) -> tuple[Path, BinaryIO]:
        self._ensure_dir()
        n = 0
        while True:
            part = final.with_name(final.name + (".part" if n == 0 else f".{n}.part"))
            try:
                fh = open(part, "xb")  # noqa: SIM115 - fermé par le puits
            except FileExistsError:
                n += 1
                continue
            except OSError as e:
                raise AudioError(f"Impossible d'écrire « {part} » : {e.strerror or e}.") from e
            self._parts.append(part)
            return part, fh

    def _check_open(self) -> None:
        if self._closed or self._aborted:
            raise RuntimeError("Le writer audio est déjà fermé.")

    # ------------------------------------------------------------------ API

    def __enter__(self) -> "AudioWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        else:
            self.close()

    @property
    def duration_s(self) -> float:
        """Durée totale écrite, en secondes."""
        return self._total / self._rate if self._rate else 0.0

    def start_chapter(self, title: str) -> None:
        self._check_open()
        self._finish_chapter()
        self._cur = _Chapter(title=(title or "").strip(), explicit=True)
        self._explicit = True

    def write(self, samples: np.ndarray, sample_rate: int) -> None:
        self._check_open()
        samples = np.asarray(samples)
        if samples.dtype != np.int16:
            raise TypeError(f"Échantillons int16 attendus, reçu {samples.dtype}.")
        if samples.ndim != 1:
            raise ValueError("Les échantillons doivent être mono (tableau à une dimension).")
        if sample_rate <= 0:
            raise ValueError(f"Fréquence d'échantillonnage invalide : {sample_rate}.")
        if samples.size == 0:
            return
        if self._rate is None:
            self._rate = int(sample_rate)
        if sample_rate != self._rate:
            if self._resampler is None or self._resampler_src != sample_rate:
                self._resampler = LinearResampler(int(sample_rate), self._rate)
                self._resampler_src = int(sample_rate)
            samples = self._resampler.process(samples)
        else:
            self._resampler = None
        self._emit(samples)

    def write_silence(self, ms: int) -> None:
        self._check_open()
        if ms <= 0 or self._rate is None or self._cur is None or not self._cur.has_audio:
            return  # pas de silence en tête de chapitre (ni avant tout son)
        remaining = round(ms * self._rate / 1000)
        while remaining > 0:
            n = min(remaining, _MAX_BLOCK)
            self._emit(np.zeros(n, dtype=np.int16))
            remaining -= n

    def close(self) -> list[Path]:
        if self._closed:
            return list(self._result)
        if self._aborted:
            raise RuntimeError("Le writer audio a été abandonné.")
        try:
            self._finalize()
        except BaseException as e:
            self.abort()
            if isinstance(e, OSError):
                raise AudioError(f"Écriture audio impossible : {e.strerror or e}.") from e
            raise
        self._closed = True
        return list(self._result)

    def abort(self) -> None:
        """Abandonne : supprime fichiers temporaires et produits, sans toucher aux fichiers préexistants."""
        if self._aborted or self._closed:
            return
        self._aborted = True
        sinks = [self._single_sink, *(c.sink for c in self._chapters)]
        for sink in sinks:
            if sink is not None:
                try:
                    sink.close()
                except Exception:  # noqa: BLE001, S110 - on nettoie, peu importe l'état
                    pass
        for path, existed in self._placed:
            if not existed:
                _unlink(path)
        for part in self._parts:
            _unlink(part)
        for d in reversed(self._made_dirs):
            try:
                d.rmdir()
            except OSError:
                pass

    # ------------------------------------------------------------------ interne

    def _emit(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        try:
            chapter = self._chapter_for_audio()
            for i in range(0, samples.size, _MAX_BLOCK):
                block = samples[i : i + _MAX_BLOCK]
                sink = self._single_sink if not self._chapters_mode else chapter.sink
                sink.write(block)  # type: ignore[union-attr]
                chapter.samples += block.size
                self._total += block.size
            chapter.end = self._total
        except OSError as e:
            raise AudioError(f"Écriture audio impossible : {e.strerror or e}.") from e

    def _chapter_for_audio(self) -> _Chapter:
        """Chapitre courant, prêt à recevoir du son (ouvre le fichier au besoin)."""
        ch = self._cur
        if ch is None:
            ch = self._cur = _Chapter(title="", explicit=False)
        if not ch.has_audio:
            ch.has_audio = True
            ch.start = self._total
            self._chapters.append(ch)
            ch.number = len(self._chapters)
            if self._chapters_mode:
                name = clean_name(ch.title, f"Chapitre {ch.number}")
                ch.final = self._dir / f"{ch.number:03d} - {name}{self._ext}"
                ch.part, fh = self._open_part(ch.final)
                ch.sink = self._make_sink(fh)
            elif self._single_sink is None:
                self._single_part, fh = self._open_part(self._output)
                self._single_sink = self._make_sink(fh)
        return ch

    def _make_sink(self, fh: BinaryIO):
        assert self._rate is not None
        try:
            if self._opt.format == "mp3":
                return Mp3Sink(fh, self._rate, int(self._opt.bitrate_kbps))
            return WavSink(fh, self._rate)
        except BaseException:
            fh.close()
            raise

    def _finish_chapter(self) -> None:
        """Termine le chapitre courant ; en mode "chapters", ferme son fichier."""
        ch = self._cur
        self._cur = None
        if ch is not None and ch.has_audio and ch.sink is not None:
            sink, ch.sink = ch.sink, None
            sink.close()  # type: ignore[attr-defined]

    def _finalize(self) -> None:
        self._finish_chapter()
        if self._single_sink is not None:
            sink, self._single_sink = self._single_sink, None
            sink.close()  # type: ignore[attr-defined]
        if not self._chapters:
            self._result = []
            return
        mp3 = self._opt.format == "mp3"
        jobs: list[tuple[Path, Path]] = []  # (part, final)
        if self._chapters_mode:
            total = len(self._chapters)
            for ch in self._chapters:
                assert ch.part is not None and ch.final is not None
                if mp3:
                    tags = ID3()
                    tags.add(TIT2(encoding=Encoding.UTF16, text=ch.title or f"Chapitre {ch.number}"))
                    if self._title:
                        tags.add(TALB(encoding=Encoding.UTF16, text=self._title))
                    self._common_tags(tags)
                    tags.add(TRCK(encoding=Encoding.UTF16, text=f"{ch.number}/{total}"))
                    tags.save(ch.part, v2_version=3)
                jobs.append((ch.part, ch.final))
            playlist = self._write_playlist()
            if playlist is not None:
                jobs.append(playlist)
        else:
            assert self._single_part is not None
            if mp3:
                self._tag_single(self._single_part)
            jobs.append((self._single_part, self._output))
        for part, final in jobs:
            existed = final.exists()
            os.replace(part, final)
            self._placed.append((final, existed))
        self._result = [final for _, final in jobs]  # fichiers audio, puis la liste de lecture

    def _common_tags(self, tags: ID3) -> None:
        if self._author:
            tags.add(TPE1(encoding=Encoding.UTF16, text=self._author))
        tags.add(TCON(encoding=Encoding.UTF16, text="Audiobook"))

    def _tag_single(self, path: Path) -> None:
        assert self._rate is not None
        tags = ID3()
        tags.add(TIT2(encoding=Encoding.UTF16, text=self._title or self._output.stem))
        self._common_tags(tags)
        if self._explicit:
            ids = []
            for ch in self._chapters:
                cid = f"chp{ch.number}"
                ids.append(cid)
                start = round(ch.start * 1000 / self._rate)
                end = round(ch.end * 1000 / self._rate)
                tags.add(
                    CHAP(
                        element_id=cid,
                        start_time=start,
                        end_time=end,
                        start_offset=0xFFFFFFFF,
                        end_offset=0xFFFFFFFF,
                        sub_frames=[TIT2(encoding=Encoding.UTF16, text=ch.title or f"Chapitre {ch.number}")],
                    )
                )
            tags.add(
                CTOC(
                    element_id="toc",
                    flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
                    child_element_ids=ids,
                    sub_frames=[TIT2(encoding=Encoding.UTF16, text=self._title or self._output.stem)],
                )
            )
        tags.save(path, v2_version=3)

    def _write_playlist(self) -> tuple[Path, Path] | None:
        assert self._rate is not None
        final = self._dir / (clean_name(self._title, "Playlist") + ".m3u8")
        part, fh = self._open_part(final)
        lines = ["#EXTM3U"]
        for ch in self._chapters:
            assert ch.final is not None
            label = ch.title or f"Chapitre {ch.number}"
            lines.append(f"#EXTINF:{round(ch.samples / self._rate)},{label}")
            lines.append(ch.final.name)
        with fh:
            fh.write(("\n".join(lines) + "\n").encode("utf-8"))
        return part, final


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
