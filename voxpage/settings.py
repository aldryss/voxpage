"""Réglages, stockés en JSON à côté de l'exécutable (repli sur le profil utilisateur)."""

import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voxpage.audio import AudioOptions
from voxpage.extract.base import ExtractOptions
from voxpage.normalize import NormalizeOptions

FILENAME = "settings.json"


@dataclass
class Settings:
    voice_id: str = ""
    speaker: int = 0
    speed: float = 1.0
    extract: ExtractOptions = field(default_factory=ExtractOptions)
    normalize: NormalizeOptions = field(default_factory=NormalizeOptions)
    audio: AudioOptions = field(default_factory=AudioOptions)


def app_dir() -> Path:
    """Dossier de l'exécutable (version gelée) ou racine du dépôt."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def fallback_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "Voxpage"
    return Path.home() / ".config" / "voxpage"


def voices_dir() -> Path:
    override = os.environ.get("VOXPAGE_VOICES")
    return Path(override) if override else app_dir() / "voices"


def _is_writable(directory: Path) -> bool:
    return directory.is_dir() and os.access(directory, os.W_OK)


def _read_path() -> Path | None:
    for directory in (app_dir(), fallback_dir()):
        candidate = directory / FILENAME
        if candidate.is_file():
            return candidate
    return None


def _build(cls: type, data: Any) -> Any:
    """Construit `cls` depuis un dict ; clés inconnues ignorées, valeurs invalides = défaut."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        current, value = getattr(obj, f.name), data[f.name]
        if dataclasses.is_dataclass(current):
            setattr(obj, f.name, _build(type(current), value))
        elif current is None:
            if value is None or isinstance(value, str):
                setattr(obj, f.name, value)
        elif isinstance(current, float) and isinstance(value, int | float) and not isinstance(value, bool):
            setattr(obj, f.name, float(value))
        elif type(value) is type(current):
            setattr(obj, f.name, value)
    return obj


def load() -> Settings:
    path = _read_path()
    if path is None:
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    return _build(Settings, data)


def save(s: Settings) -> None:
    directory = app_dir()
    if not _is_writable(directory):
        directory = fallback_dir()
        directory.mkdir(parents=True, exist_ok=True)
    path = directory / FILENAME
    path.write_text(json.dumps(dataclasses.asdict(s), indent=2, ensure_ascii=False), encoding="utf-8")
