"""Moteur de synthèse : sherpa-onnx + voix Piper (VITS), 100 % local."""

import atexit
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

import numpy as np

from voxpage import settings
from voxpage.tts.base import Voice

MIN_SPEED = 0.5
MAX_SPEED = 2.0
MAX_THREADS = 4


class TtsError(Exception):
    """Erreur de synthèse, message lisible par l'utilisateur."""


def clamp_speed(speed: float) -> float:
    return min(MAX_SPEED, max(MIN_SPEED, float(speed)))


def default_threads() -> int:
    """Environ le nombre de cœurs physiques (cpu_count / 2 : hyperthreading), de 1 à 4."""
    return max(1, min(MAX_THREADS, (os.cpu_count() or 2) // 2))


def _short_path(path: Path) -> Path | None:
    """Nom court 8.3 (ASCII) d'un chemin existant, sous Windows ; None si indisponible."""
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))  # type: ignore[attr-defined]
    return Path(buf.value) if 0 < n < len(buf) and buf.value.isascii() else None


def ascii_voice_folder(folder: Path, windows: bool | None = None) -> Path:
    """Chemin du dossier de voix utilisable par eSpeak NG et onnxruntime.

    Sous Windows ces bibliothèques lisent les chemins en codage « ANSI » : un accent dans le chemin
    (« C:\\Users\\José\\… ») les met en échec. On passe par le nom court 8.3, ou, à défaut, par une
    copie temporaire dans un dossier au nom ASCII.
    """
    if windows is None:
        windows = os.name == "nt"
    if not windows or str(folder).isascii():
        return folder
    short = _short_path(folder)
    if short is not None:
        return short
    tmp = Path(tempfile.mkdtemp(prefix="voxpage-"))
    atexit.register(shutil.rmtree, tmp, True)
    copy = tmp / "voix"
    shutil.copytree(folder, copy)
    return _short_path(copy) or copy


class SherpaEngine:
    def __init__(self, voices_dir: Path | None = None, num_threads: int | None = None) -> None:
        self._voices_dir = voices_dir
        self._num_threads = num_threads or default_threads()
        self._models: dict[str, tuple[object, int]] = {}  # voice_id -> (OfflineTts, sample_rate)
        self._lock = threading.Lock()

    @property
    def voices_dir(self) -> Path:
        return self._voices_dir if self._voices_dir is not None else settings.voices_dir()

    def list_voices(self) -> list[Voice]:
        root = self.voices_dir
        if not root.is_dir():
            return []
        voices = []
        for sub in sorted(root.iterdir()):
            meta = _read_meta(sub / "voice.json")
            if meta is None:
                continue
            speakers = meta.get("speakers")
            voices.append(
                Voice(
                    id=sub.name,
                    name=str(meta.get("name") or sub.name),
                    lang=str(meta.get("lang") or ""),
                    speakers=[str(s) for s in speakers] if isinstance(speakers, list) else [],
                )
            )
        return voices

    def synthesize(
        self, text: str, voice_id: str, speaker: int = 0, speed: float = 1.0
    ) -> tuple[np.ndarray, int]:
        tts, rate = self._load(voice_id)
        if not text.strip():
            return np.zeros(0, dtype=np.int16), rate
        n_speakers = int(getattr(tts, "num_speakers", 1) or 1)
        if not 0 <= speaker < n_speakers:
            raise TtsError(
                f"Locuteur {speaker} inexistant pour la voix « {voice_id} » ({n_speakers} disponible(s))."
            )
        with self._lock:  # un modèle sherpa n'est pas réentrant
            audio = tts.generate(text, sid=speaker, speed=clamp_speed(speed))
        samples = np.asarray(audio.samples, dtype=np.float32)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).round().astype(np.int16)
        return pcm, int(audio.sample_rate)

    def _load(self, voice_id: str) -> tuple[object, int]:
        with self._lock:
            cached = self._models.get(voice_id)
            if cached is not None:
                return cached
            folder = self.voices_dir / voice_id
            if not voice_id or "/" in voice_id or "\\" in voice_id or not folder.is_dir():
                raise TtsError(f"Voix introuvable : « {voice_id} ». Vérifiez le dossier « voices ».")
            models = sorted(folder.glob("*.onnx"))
            missing = []
            if not models:
                missing.append("modèle .onnx")
            if not (folder / "tokens.txt").is_file():
                missing.append("tokens.txt")
            if not (folder / "espeak-ng-data").is_dir():
                missing.append("espeak-ng-data")
            if missing:
                raise TtsError(f"Voix « {voice_id} » incomplète : il manque {', '.join(missing)}.")
            import sherpa_onnx

            folder = ascii_voice_folder(folder)
            models = sorted(folder.glob("*.onnx"))
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(models[0]),
                tokens=str(folder / "tokens.txt"),
                data_dir=str(folder / "espeak-ng-data"),
            )
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=self._num_threads)
            )
            try:
                tts = sherpa_onnx.OfflineTts(config)
            except Exception as exc:  # erreurs C++ diverses
                raise TtsError(f"Impossible de charger la voix « {voice_id} » : {exc}") from exc
            entry = (tts, int(tts.sample_rate))
            self._models[voice_id] = entry
            return entry


def _read_meta(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


_engine: SherpaEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> SherpaEngine:
    """Instance partagée (les modèles chargés restent en cache)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SherpaEngine()
        return _engine
