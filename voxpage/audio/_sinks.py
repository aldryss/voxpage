"""Encodeurs en flux : chaque puits reçoit du PCM int16 mono et écrit dans un fichier ouvert."""

import wave
from typing import BinaryIO

import lameenc
import numpy as np

from ._mp3info import FrameCounter, info_frame, parse_header


class Mp3Sink:
    """MP3 CBR mono. Réserve en tête une trame « Info » complétée à la fermeture (durée, gapless)."""

    def __init__(self, fh: BinaryIO, rate: int, bitrate_kbps: int):
        self._fh = fh
        self._bitrate = bitrate_kbps
        self._enc = lameenc.Encoder()
        self._enc.set_bit_rate(bitrate_kbps)
        self._enc.set_in_sample_rate(rate)
        self._enc.set_channels(1)
        self._enc.set_quality(2)
        self._counter = FrameCounter()
        self._header: bytes | None = None
        self._info_len = 0
        self._bytes = 0  # octets d'audio écrits (hors trame Info)
        self._samples = 0

    def _put(self, data: bytes) -> None:
        if not data:
            return
        if self._header is None:
            self._header = data[:4]
            parsed = parse_header(self._header)
            if parsed is not None:
                self._info_len = len(info_frame(self._header, 0, 0, 0, self._bitrate))
                self._fh.write(bytes(self._info_len))  # réservé, complété à la fermeture
        self._counter.feed(data)
        self._fh.write(data)
        self._bytes += len(data)

    def write(self, samples: np.ndarray) -> None:
        self._samples += samples.size
        self._put(self._enc.encode(np.ascontiguousarray(samples, dtype="<i2").tobytes()))

    def close(self) -> None:
        try:
            self._put(self._enc.flush())  # vide l'encodeur : dernière trame complète
            if self._info_len and self._counter.ok and self._header is not None:
                frame = info_frame(
                    self._header,
                    self._counter.frames,
                    self._bytes + self._info_len,
                    self._samples,
                    self._bitrate,
                )
                self._fh.seek(0)
                self._fh.write(frame)
        finally:
            self._fh.close()


class WavSink:
    def __init__(self, fh: BinaryIO, rate: int):
        self._fh = fh
        self._wav = wave.open(fh, "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(rate)

    def write(self, samples: np.ndarray) -> None:
        self._wav.writeframes(np.ascontiguousarray(samples, dtype="<i2").tobytes())

    def close(self) -> None:
        try:
            self._wav.close()  # corrige l'en-tête (tailles)
        finally:
            self._fh.close()
