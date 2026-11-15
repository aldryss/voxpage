"""Rééchantillonnage en flux par interpolation linéaire (continu d'un bloc à l'autre)."""

import numpy as np


class LinearResampler:
    def __init__(self, src_rate: int, dst_rate: int):
        self.step = src_rate / dst_rate
        self._prev: np.ndarray | None = None  # dernier échantillon du bloc précédent
        self._pos = 0.0  # position de la prochaine sortie, dans le repère de `ext` (0 = _prev)

    def process(self, samples: np.ndarray) -> np.ndarray:
        x = samples.astype(np.float32)
        ext = x if self._prev is None else np.concatenate([self._prev, x])
        last = len(ext) - 1
        if self._pos > last:  # ne devrait pas arriver, par sécurité
            self._pos -= len(x)
            self._prev = ext[-1:]
            return np.empty(0, dtype=np.int16)
        n = int((last - self._pos) / self.step) + 1
        positions = self._pos + np.arange(n, dtype=np.float64) * self.step
        np.minimum(positions, last, out=positions)
        i0 = positions.astype(np.int64)
        i1 = np.minimum(i0 + 1, last)
        frac = (positions - i0).astype(np.float32)
        out = ext[i0] * (1.0 - frac) + ext[i1] * frac
        self._pos = self._pos + n * self.step - last
        self._prev = ext[-1:].copy()
        return np.clip(np.rint(out), -32768, 32767).astype(np.int16)
